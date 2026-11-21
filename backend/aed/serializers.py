from mcod.aed.validation import fields as schema_fields
from mcod.core.api import fields
from mcod.core.api.jsonapi.serializers import ObjectAttrs, TopLevel

# AED attributes come from the reference data scope (schema/aed.schema.json), same names as in the dataset.
SCHEMA_TYPES = {"integer": fields.Int, "number": fields.Float, "boolean": fields.Bool, "date": fields.Date}

_attrs = {
    field["name"]: SCHEMA_TYPES.get(field["type"], fields.Str)(required=False, description=field["title"])
    for field in schema_fields(provider_only=True)
}
_attrs.update(
    uuid=fields.Str(required=True),
    source=fields.Str(required=True, example="form"),
    organization_title=fields.Str(attribute="organization.title", example="Urząd Miasta"),
    status=fields.Str(required=True, example="submitted"),
    verification_comment=fields.Str(required=False),
    verified_at=fields.DateTime(required=False),
    created=fields.DateTime(required=True),
    modified=fields.DateTime(required=True),
    possible_duplicate=fields.Method("get_possible_duplicate"),
)


def get_possible_duplicate(self, obj):
    duplicate = obj.possible_duplicate_of
    if duplicate is None:
        return None
    return {
        "id": str(duplicate.pk),
        "uuid": str(duplicate.uuid),
        "location_name": duplicate.location_name,
        "distance_m": obj.possible_duplicate_distance_m,
    }


class _Meta:
    object_type = "aed_report"
    path = "aed-reports"
    url_template = "{api_url}/aed-reports/{ident}"


AedReportAttrs = type("AedReportAttrs", (ObjectAttrs,), dict(_attrs, Meta=_Meta, get_possible_duplicate=get_possible_duplicate))


class AedReportApiResponse(TopLevel):
    class Meta:
        attrs_schema = AedReportAttrs


class AedReportImportAttrs(ObjectAttrs):
    """Result of a file import (dry run or real); not stored — returned as a namedtuple (like schedules)."""

    status = fields.Str(required=True, example="dry_run", description="dry_run | imported | rejected")
    format = fields.Str(required=True, example="csv")
    file_error = fields.Str(required=False, description="Problem with the whole file (format, header, size)")
    summary = fields.Raw(required=False, description="Counts: rows, valid, invalid, create, update, unchanged, duplicates")
    errors = fields.Raw(required=False, description="[{row, field, message}] — row = line number in a CSV file")
    actions = fields.Raw(required=False, description="[{row, action, location_name, duplicate_of, duplicate_of_row, ...}]")

    class Meta:
        object_type = "aed_report_import"


class AedReportImportApiResponse(TopLevel):
    class Meta:
        attrs_schema = AedReportImportAttrs
