from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _, ngettext

from mcod.aed.models import AedReport
from mcod.organizations.models import Organization

PROVIDER_FIELDS = ("organization", "location_name", "notes", "data_date")
VERIFICATION_FIELDS = ("status", "verification_comment", "verified_by", "verified_at")
AUDIT_FIELDS = ("created", "created_by", "modified", "modified_by")


@admin.register(AedReport)
class AedReportAdmin(admin.ModelAdmin):
    """Providers (editors) manage reports of their institutions; superusers verify all reports."""

    list_display = ("location_name", "organization", "status", "data_date", "created", "verified_at")
    search_fields = ("location_name", "notes", "organization__title")
    actions = ["submit_for_verification", "mark_verified", "mark_rejected"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("organization", "verified_by")
        if request.user.is_superuser:
            return queryset
        return queryset.filter(organization__in=request.user.organizations.all())

    def get_list_filter(self, request):
        return ("status", "organization") if request.user.is_superuser else ("status",)

    def get_fieldsets(self, request, obj=None):
        fieldsets = [(_("AED availability report"), {"fields": PROVIDER_FIELDS})]
        if obj:
            fieldsets.append((_("Verification"), {"fields": VERIFICATION_FIELDS}))
            fieldsets.append((_("History"), {"fields": AUDIT_FIELDS}))
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = AUDIT_FIELDS + ("verified_by", "verified_at")
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
