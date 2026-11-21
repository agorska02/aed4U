from mcod.core.api import fields
from mcod.core.api.jsonapi.serializers import ObjectAttrs, TopLevel


class AedReportAttrs(ObjectAttrs):
    organization_title = fields.Str(attribute="organization.title", example="Urząd Miasta")
    location_name = fields.Str(required=True, example="Dworzec Centralny")
    notes = fields.Str(required=False, example="Lorem Ipsum")
    data_date = fields.Date(required=True)
    status = fields.Str(required=True, example="submitted")
    verification_comment = fields.Str(required=False)
    verified_at = fields.DateTime(required=False)
    created = fields.DateTime(required=True)
    modified = fields.DateTime(required=True)

    class Meta:
        object_type = "aed_report"
        path = "aed-reports"
        url_template = "{api_url}/aed-reports/{ident}"


class AedReportApiResponse(TopLevel):
    class Meta:
        attrs_schema = AedReportAttrs
