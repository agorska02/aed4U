from mcod.aed.validation import fields as schema_fields
from mcod.core.api import fields as core_fields
from mcod.core.api.jsonapi.deserializers import ObjectAttrs, TopLevel

# Attributes are generated from the reference data scope (schema/aed.schema.json). They accept raw JSON values;
# types and constraints are checked by mcod.aed.validation in the view, so the API, file imports and the
# demo use exactly the same rules and messages.
_attrs = {
    field["name"]: core_fields.Raw(
        description=field["title"] + (" — " + field["description"] if field.get("description") else ""),
        required=False,
        allow_none=True,
    )
    for field in schema_fields(provider_only=True)
}
_attrs["organization"] = core_fields.Int(
    description="Institution ID — required only if the user is assigned to more than one institution",
    example=1,
    required=False,
)


class _Meta:
    strict = True
    ordered = True
    object_type = "aed_report"


CreateAedReportAttrs = type("CreateAedReportAttrs", (ObjectAttrs,), dict(_attrs, Meta=_Meta))


class CreateAedReportRequest(TopLevel):
    class Meta:
        attrs_schema = CreateAedReportAttrs
        attrs_schema_required = True


class CreateAedReportImportAttrs(ObjectAttrs):
    format = core_fields.Str(
        description="File format: csv (UTF-8, comma or semicolon), json or geojson",
        example="csv",
        required=False,
        allow_none=True,
    )
    content = core_fields.Str(description="File content (text, max 2 MB)", required=False, allow_none=True)
    dry_run = core_fields.Raw(
        description="true (default) — only check the file and report; false — import if the file has no errors",
        required=False,
        allow_none=True,
    )
    organization = core_fields.Int(
        description="Institution ID — required only if the user is assigned to more than one institution",
        required=False,
    )

    class Meta:
        strict = True
        ordered = True
        object_type = "aed_report_import"


class CreateAedReportImportRequest(TopLevel):
    class Meta:
        attrs_schema = CreateAedReportImportAttrs
        attrs_schema_required = True
