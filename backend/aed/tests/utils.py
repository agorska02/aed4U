import datetime
from decimal import Decimal

# A complete, valid AED report — schema/aed-example.csv, first record.
VALID_ATTRIBUTES = {
    "operator_name": "Urząd Miasta Testowego",
    "location_name": "Urząd Miasta – budynek A",
    "location_description": "hol główny, przy punkcie informacji",
    "indoor": True,
    "floor": 0,
    "commune": "Kraków",
    "city": "Kraków",
    "street_type": "ul.",
    "street": "Przykładowa",
    "street_number": "1",
    "postal_code": "31-004",
    "latitude": 50.059,
    "longitude": 19.937,
    "access": "customers",
    "opening_hours": "Mo-Fr 07:30-15:30",
    "device_status": "operational",
    "data_date": "2026-11-15",
}


def report_kwargs(**overrides):
    """Model kwargs for AedReport.objects.create()."""
    kwargs = dict(VALID_ATTRIBUTES, latitude=Decimal("50.059"), longitude=Decimal("19.937"))
    kwargs["data_date"] = datetime.date(2026, 11, 15)
    kwargs.update(overrides)
    return kwargs
