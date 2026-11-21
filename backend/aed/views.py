import datetime
import json
import uuid
from collections import namedtuple
from functools import partial

import falcon
from django.apps import apps
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from mcod.aed import importing
from mcod.aed.deserializers import CreateAedReportImportRequest, CreateAedReportRequest
from mcod.aed.serializers import AedReportApiResponse, AedReportImportApiResponse
from mcod.aed.validation import field_names, validate_record
from mcod.core.api.handlers import CreateOneHdlr, RetrieveManyHdlr
from mcod.core.api.hooks import login_required
from mcod.core.api.views import JsonAPIView
from mcod.core.versioning import versioned
from mcod.organizations.models import Organization

PROVIDER_ROLES = ["editor", "admin"]
AED_FIELDS = field_names(provider_only=True)
REPORTED_ACTIONS = 500  # at most this many planned actions are returned in an import response
EXPORT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "geojson": "application/geo+json; charset=utf-8",
}
ImportResult = namedtuple("ImportResult", "id status format file_error summary errors actions")


def _field_errors(errors):
    exc = falcon.HTTPUnprocessableEntity()
    exc.errors = {field: [str(message)] for field, message in errors.items()}
    return exc


def model_values(model, cleaned):
    """Validator output -> model kwargs ("" instead of None for text fields, like Django forms)."""
    values = {}
    for name, value in cleaned.items():
        field = model._meta.get_field(name)
        values[name] = "" if value is None and not field.null else value
    return values


def get_organization(user, organization_id):
    """(organization, error message) for the institution a report or an import concerns."""
    organizations = Organization.objects.all() if user.is_superuser else user.organizations.all()
    if organization_id is not None:
        try:
            return organizations.get(pk=organization_id), None
        except Organization.DoesNotExist:
            return None, _("You are not assigned to this institution.")
    if not user.is_superuser and organizations.count() == 1:
        return organizations.get(), None
    return None, _("Select the institution the report concerns.")


def planning_records(queryset):
    """Records as dicts (schema fields + id) for importing.plan_import / find_duplicate."""
    return list(queryset.values("id", *AED_FIELDS))


class AedReportView(JsonAPIView):
    @falcon.before(login_required, roles=PROVIDER_ROLES)
    @versioned
    def on_get(self, request, response, *args, **kwargs):
        self.handle(request, response, self.GET, *args, **kwargs)

    @falcon.before(login_required, roles=PROVIDER_ROLES)
    @versioned
    def on_post(self, request, response, *args, **kwargs):
        self.handle_post(request, response, self.POST, *args, **kwargs)

    class GET(RetrieveManyHdlr):
        """Reports of the institutions the user is assigned to (all reports for superusers)."""

        database_model = apps.get_model("aed", "AedReport")
        serializer_schema = partial(AedReportApiResponse, many=True)

        def _get_queryset(self, cleaned, *args, **kwargs):
            queryset = self.database_model.objects.select_related("organization", "possible_duplicate_of")
            user = self.request.user
            if user.is_superuser:
                return queryset
            return queryset.filter(organization__in=user.organizations.all())

    class POST(CreateOneHdlr):
        deserializer_schema = CreateAedReportRequest
        database_model = apps.get_model("aed", "AedReport")
        serializer_schema = partial(AedReportApiResponse, many=False)

        def _get_data(self, cleaned, *args, **kwargs):
            attributes = dict(cleaned["data"]["attributes"])
            user = self.request.user
            requested_org = attributes.pop("organization", None)
            # operator_name defaults to the institution's name, so the form does not require it
            values, errors = validate_record(attributes, optional=("operator_name",))
            organization, org_error = get_organization(user, requested_org)
            if org_error:
                errors["organization"] = org_error
            if errors:
                raise _field_errors(errors)
            values["operator_name"] = values["operator_name"] or organization.title
            model = self.database_model
            duplicate, distance = importing.find_duplicate(values, planning_records(model.objects.all()))
            self.response.context.data = model.objects.create(
                organization=organization,
                source=model.SOURCE.form,
                status=model.STATUS.submitted,
                created_by=user,
                modified_by=user,
                possible_duplicate_of_id=duplicate["id"] if duplicate else None,
                possible_duplicate_distance_m=distance,
                **model_values(model, values),
            )


class AedReportImportView(JsonAPIView):
    """POST /aed-report-imports — a data provider's file (CSV/JSON/GeoJSON), checked against the reference scope.

    dry_run=true (default) only reports what would happen; dry_run=false imports a file without errors in one
    transaction. Rows with a known source_id update the institution's record (which goes back to verification).
    """

    @falcon.before(login_required, roles=PROVIDER_ROLES)
    @versioned
    def on_post(self, request, response, *args, **kwargs):
        self.handle_post(request, response, self.POST, *args, **kwargs)

    class POST(CreateOneHdlr):
        deserializer_schema = CreateAedReportImportRequest
        database_model = apps.get_model("aed", "AedReport")
        serializer_schema = partial(AedReportImportApiResponse, many=False)

        def _get_data(self, cleaned, *args, **kwargs):
            attributes = cleaned["data"]["attributes"]
            user = self.request.user
            file_format, content = attributes.get("format"), attributes.get("content")
            dry_run = attributes.get("dry_run", True)
            dry_run = True if dry_run is None else dry_run
            errors = {}
            if file_format not in importing.FORMATS:
                errors["format"] = _("Allowed values: csv, json, geojson.")
            if not isinstance(content, str) or not content.strip():
                errors["content"] = _("Attach the file content.")
            if not isinstance(dry_run, bool):
                errors["dry_run"] = _("Allowed values: true, false.")
            organization, org_error = get_organization(user, attributes.get("organization"))
            if org_error:
                errors["organization"] = org_error
            if errors:
                raise _field_errors(errors)

            import_id = str(uuid.uuid4())
            try:
                rows = importing.parse_file(content, file_format)
            except importing.ImportFileError as exc:
                self.response.context.data = ImportResult(import_id, "rejected", file_format, str(exc), None, [], [])
                return
            model = self.database_model
            with transaction.atomic():
                plan = importing.plan_import(
                    rows,
                    planning_records(model.objects.filter(organization=organization).exclude(source_id="")),
                    planning_records(model.objects.all()),
                    organization.title,
                )
                if plan["errors"]:
                    status = "rejected"
                elif dry_run:
                    status = "dry_run"
                else:
                    status = "imported"
                    self._apply(plan, organization, user)
            actions = [
                {
                    "row": a["row"],
                    "action": a["action"],
                    "location_name": a["values"].get("location_name"),
                    "duplicate_of": None if a["duplicate_of"] is None else str(a["duplicate_of"]),
                    "duplicate_of_row": a["duplicate_of_row"],
                    "duplicate_distance_m": a["duplicate_distance_m"],
                }
                for a in plan["actions"][:REPORTED_ACTIONS]
            ]
            self.response.context.data = ImportResult(
                import_id, status, file_format, None, plan["summary"], plan["errors"], actions
            )

        def _apply(self, plan, organization, user):
            model = self.database_model
            created_for_row = {}
            for action in plan["actions"]:
                if action["action"] == "unchanged":
                    continue
                duplicate_id = action["duplicate_of"]
                if action["duplicate_of_row"] is not None:
                    duplicate_id = created_for_row.get(action["duplicate_of_row"])
                values = model_values(model, action["values"])
                common = dict(
                    source="import",  # model.SOURCE has no attribute for the keyword
                    status=model.STATUS.submitted,
                    modified_by=user,
                    possible_duplicate_of_id=duplicate_id,
                    possible_duplicate_distance_m=action["duplicate_distance_m"],
                )
                if action["action"] == "create":
                    report = model.objects.create(organization=organization, created_by=user, **common, **values)
                    created_for_row[action["row"]] = report.pk
                else:  # update: changed data goes back to verification
                    model.objects.filter(pk=action["record_id"]).update(
                        verification_comment="", verified_by=None, verified_at=None, modified=timezone.now(), **common, **values
                    )


class AedDeviceView:
    """GET /aed-devices[?format=csv|json|geojson] — public unified dataset (verified records only).

    Columns follow the reference data scope. Without `format` the response is JSON:API (aed_device objects).
    In production the files would rather be generated periodically (Celery) as resources of a dane.gov.pl dataset.
    """

    def on_get(self, request, response, *args, **kwargs):
        file_format = request.get_param("format") or ""
        if file_format and file_format not in EXPORT_TYPES:
            raise falcon.HTTPBadRequest(description=_("Allowed formats: csv, json, geojson."))
        model = apps.get_model("aed", "AedReport")
        records = (
            model.objects.filter(status=model.STATUS.verified).order_by("pk").values("uuid", "source", "verified_at", *AED_FIELDS)
        )
        rows = [importing.export_record(record) for record in records]
        data_date = datetime.date.today().isoformat()
        response.status = falcon.HTTP_200
        response.set_header("Access-Control-Allow-Origin", "*")  # open data
        if not file_format:
            data = [{"type": "aed_device", "id": row["id"], "attributes": row} for row in importing.to_json(rows)]
            response.content_type = "application/vnd.api+json"
            response.text = json.dumps({"data": data, "meta": {"count": len(rows), "data_date": data_date}}, ensure_ascii=False)
            return
        if file_format == "csv":
            response.text = importing.to_csv(rows)
        elif file_format == "geojson":
            response.text = json.dumps(importing.to_geojson(rows, data_date), ensure_ascii=False)
        else:
            response.text = json.dumps(importing.to_json(rows), ensure_ascii=False)
        response.content_type = EXPORT_TYPES[file_format]
        response.downloadable_as = "aed-{0}.{1}".format(data_date, file_format)
