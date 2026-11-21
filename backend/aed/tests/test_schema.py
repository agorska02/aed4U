import pytest

from mcod.aed.models import AedReport
from mcod.aed.validation import enum_choices, field_names

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "field, choices",
    [
        ("access", AedReport.ACCESS),
        ("device_status", AedReport.DEVICE_STATUS),
        ("pediatric", AedReport.PEDIATRIC),
    ],
)
def test_model_choices_match_schema_enums(field, choices):
    assert [code for code, _label in choices] == [code for code, _label in enum_choices(field)]


def test_model_has_every_provider_field_of_the_schema():
    model_fields = {field.name for field in AedReport._meta.get_fields()}
    assert set(field_names(provider_only=True)) <= model_fields
