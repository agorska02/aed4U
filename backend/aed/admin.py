from django import forms
from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _, ngettext

from mcod.aed.models import AedReport
from mcod.aed.validation import fields as schema_fields, load_schema, validate_record
from mcod.organizations.models import Organization

AED_FIELDS = tuple(f["name"] for f in schema_fields(provider_only=True))
PROVIDER_FIELDS = ("organization",) + AED_FIELDS
VERIFICATION_FIELDS = (
    "status",
    "verification_comment",
    "verified_by",
    "verified_at",
    "possible_duplicate_of",
    "possible_duplicate_distance_m",
)
AUDIT_FIELDS = ("uuid", "source", "created", "created_by", "modified", "modified_by")


def aed_fieldsets():
    """One fieldset per section of the reference data scope (x-groups), in schema order."""
    schema = load_schema()
    return [
        (
            group["title"],
            {"fields": tuple(f["name"] for f in schema_fields(provider_only=True) if f.get("x-group") == group["name"])},
        )
        for group in schema["x-groups"]
    ]


class PossibleDuplicateFilter(admin.SimpleListFilter):
    title = _("Possible duplicate")
    parameter_name = "possible_duplicate"

    def lookups(self, request, model_admin):
        return (("yes", _("Yes")), ("no", _("No")))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(possible_duplicate_of__isnull=False)
        if self.value() == "no":
            return queryset.filter(possible_duplicate_of__isnull=True)
        return queryset


class AedReportForm(forms.ModelForm):
    """Applies the shared schema rules (mcod.aed.validation) on top of the model validation."""

    class Meta:
        model = AedReport
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        editable = [name for name in AED_FIELDS if name in self.fields]
        if editable:
            record = {name: cleaned_data.get(name) for name in editable}
            _values, errors = validate_record(record)
            for name, message in errors.items():
                if name in self.fields and name not in self.errors:
                    self.add_error(name, message)
        return cleaned_data


@admin.register(AedReport)
class AedReportAdmin(admin.ModelAdmin):
    """Providers (editors) manage reports of their institutions; superusers verify all reports."""

    form = AedReportForm
    list_display = (
        "location_name",
        "city",
        "organization",
        "source",
        "device_status",
        "status",
        "possible_duplicate_of",
        "data_date",
    )
    search_fields = ("location_name", "city", "operator_name", "notes", "organization__title")
    actions = ["submit_for_verification", "mark_verified", "mark_rejected"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("organization", "verified_by")
        if request.user.is_superuser:
            return queryset
        return queryset.filter(organization__in=request.user.organizations.all())

    def get_list_filter(self, request):
        if request.user.is_superuser:
            return ("status", "device_status", "access", "source", PossibleDuplicateFilter, "organization")
        return ("status", "device_status")

    def get_fieldsets(self, request, obj=None):
        fieldsets = [(_("Institution"), {"fields": ("organization",)})] + aed_fieldsets()
        if obj:
            fieldsets.append((_("Verification"), {"fields": VERIFICATION_FIELDS}))
            fieldsets.append((_("History"), {"fields": AUDIT_FIELDS}))
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = AUDIT_FIELDS + ("verified_by", "verified_at", "possible_duplicate_of", "possible_duplicate_distance_m")
        if request.user.is_superuser:
            return readonly
        readonly += ("status", "verification_comment")
        if obj and not obj.is_editable_by_provider:
            readonly += PROVIDER_FIELDS
        return readonly

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "organization" and not request.user.is_superuser:
            kwargs["queryset"] = Organization.objects.filter(pk__in=request.user.organizations.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj) and (obj is None or obj.status == AedReport.STATUS.draft)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("mark_verified", None)
            actions.pop("mark_rejected", None)
        return actions

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.modified_by = request.user
        is_verification_change = "status" in form.changed_data and obj.status in (
            AedReport.STATUS.verified,
            AedReport.STATUS.rejected,
        )
        if request.user.is_superuser and is_verification_change:
            obj.set_verification(obj.status, request.user)
        super().save_model(request, obj, form, change)

    def submit_for_verification(self, request, queryset):
        count = 0
        for report in queryset.filter(status__in=AedReport.PROVIDER_EDITABLE_STATUSES):
            report.submit(request.user)
            report.save()
            count += 1
        self.message_user(
            request,
            ngettext("%d report submitted for verification.", "%d reports submitted for verification.", count) % count,
            messages.SUCCESS,
        )

    submit_for_verification.short_description = _("Submit for verification")

    def _set_verification(self, request, queryset, status):
        count = 0
        for report in queryset.filter(status=AedReport.STATUS.submitted):
            report.set_verification(status, request.user)
            report.modified_by = request.user
            report.save()
            count += 1
        self.message_user(request, ngettext("%d report updated.", "%d reports updated.", count) % count, messages.SUCCESS)

    def mark_verified(self, request, queryset):
        self._set_verification(request, queryset, AedReport.STATUS.verified)

    mark_verified.short_description = _("Mark as verified")

    def mark_rejected(self, request, queryset):
        self._set_verification(request, queryset, AedReport.STATUS.rejected)

    mark_rejected.short_description = _("Mark as rejected (add a comment in the report form)")
