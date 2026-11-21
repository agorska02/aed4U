from marshmallow import validate

from mcod.core.api import fields as core_fields
from mcod.core.api.jsonapi.deserializers import ObjectAttrs, TopLevel


class CreateAedReportAttrs(ObjectAttrs):
    organization = core_fields.Int(
        description="Institution ID — required only if the user is assigned to more than one institution",
        example=1,
        required=False,
    )
    location_name = core_fields.String(
        description="Location name", example="Dworzec Centralny", required=True, validate=validate.Length(min=1, max=300)
    )
    notes = core_fields.String(description="Notes", example="Lorem Ipsum", required=False, validate=validate.Length(max=3000))
    data_date = core_fields.Date(description="Data date (ISO 8601)", example="2026-11-21", required=False)

    class Meta:
        strict = True
        ordered = True
        object_type = "aed_report"


class CreateAedReportRequest(TopLevel):
    class Meta:
        attrs_schema = CreateAedReportAttrs
        attrs_schema_required = True
