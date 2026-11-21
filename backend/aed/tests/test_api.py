import pytest
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from falcon import HTTP_200, HTTP_201, HTTP_401, HTTP_403, HTTP_422, testing

from mcod.aed.models import AedReport
from mcod.aed.tests.utils import VALID_ATTRIBUTES, report_kwargs
from mcod.lib.jwt import get_auth_token
from mcod.lib.triggers import session_store as session_store_create
from mcod.organizations.factories import OrganizationFactory

# All tests in this module depend on component
pytestmark = [pytest.mark.depends_on_component, pytest.mark.component_api, pytest.mark.django_db]

PAYLOAD = {"data": {"type": "aed_report", "attributes": VALID_ATTRIBUTES}}


def _payload(**changes):
    attributes = dict(VALID_ATTRIBUTES, **changes)
    return {"data": {"type": "aed_report", "attributes": {k: v for k, v in attributes.items() if v is not None}}}


def _logged_client(user, test_api_instance) -> testing.TestClient:
    """Same session + JWT setup as the `client14_logged_admin` fixture, for any user."""
    session = session_store_create()
    session[SESSION_KEY] = str(user.id)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    token = get_auth_token(user, session_key=session.session_key)
    headers = {"X-API-VERSION": "1.4", "Accept-Language": "pl", "Authorization": f"Bearer {token}"}
    return testing.TestClient(test_api_instance, headers=headers)


def test_anonymous_user_cannot_create_report(client14):
    resp = client14.simulate_post("/aed-reports", json=PAYLOAD)
    assert resp.status == HTTP_401
    assert not AedReport.objects.exists()


def test_regular_user_cannot_create_report(active_user, test_api_instance):
    resp = _logged_client(active_user, test_api_instance).simulate_post("/aed-reports", json=PAYLOAD)
    assert resp.status == HTTP_403


def test_editor_creates_report_for_own_institution(active_editor, test_api_instance):
    # WHEN
    resp = _logged_client(active_editor, test_api_instance).simulate_post("/aed-reports", json=PAYLOAD)
    # THEN
    assert resp.status == HTTP_201
    report = AedReport.objects.get()
    assert report.organization == active_editor.organizations.get()
    assert report.status == AedReport.STATUS.submitted
    assert report.created_by == active_editor
    assert report.source == AedReport.SOURCE.form
    assert report.indoor is True
    assert str(report.latitude) == "50.059000"
    attributes = resp.json["data"]["attributes"]
    assert attributes["status"] == "submitted"
    assert attributes["opening_hours"] == "Mo-Fr 07:30-15:30"
    assert attributes["uuid"] == str(report.uuid)


def test_operator_name_defaults_to_institution(active_editor, test_api_instance):
    resp = _logged_client(active_editor, test_api_instance).simulate_post("/aed-reports", json=_payload(operator_name=None))
    assert resp.status == HTTP_201
    assert AedReport.objects.get().operator_name == active_editor.organizations.get().title


def test_editor_cannot_create_report_for_foreign_institution(active_editor, test_api_instance):
    foreign = OrganizationFactory.create()
    resp = _logged_client(active_editor, test_api_instance).simulate_post("/aed-reports", json=_payload(organization=foreign.pk))
    assert resp.status == HTTP_422
    assert not AedReport.objects.exists()


def test_schema_rules_are_applied_per_field(active_editor, test_api_instance):
    payload = _payload(location_name=None, postal_code="31004", latitude="50,06")
    resp = _logged_client(active_editor, test_api_instance).simulate_post("/aed-reports", json=payload)
    assert resp.status == HTTP_422
    pointers = {error["source"]["pointer"].split("/")[-1] for error in resp.json["errors"]}
    assert {"location_name", "postal_code", "latitude"} <= pointers
    assert not AedReport.objects.exists()


def test_editor_lists_only_own_institution_reports(active_editor, test_api_instance):
    own = AedReport.objects.create(**report_kwargs(organization=active_editor.organizations.get(), location_name="Własny"))
    AedReport.objects.create(**report_kwargs(organization=OrganizationFactory.create(), location_name="Obcy"))
    resp = _logged_client(active_editor, test_api_instance).simulate_get("/aed-reports")
    assert resp.status == HTTP_200
    assert [item["id"] for item in resp.json["data"]] == [str(own.pk)]


CSV_HEADER = (
    "source_id,location_name,location_description,indoor,commune,city,street_number,postal_code,"
    "latitude,longitude,access,opening_hours,device_status,data_date"
)


def _csv(*rows):
    return "\n".join((CSV_HEADER,) + rows) + "\n"


def _csv_row(source_id, name="Basen miejski", lat="50.080000", postal="31-004", hours="24/7"):
    return f"{source_id},{name},hol,true,Kraków,Kraków,3,{postal},{lat},19.950000,public,{hours},operational,2026-11-20"


def _import(client, content, dry_run=True, file_format="csv"):
    payload = {
        "data": {"type": "aed_report_import", "attributes": {"format": file_format, "content": content, "dry_run": dry_run}}
    }
    return client.simulate_post("/aed-report-imports", json=payload)


def test_import_dry_run_does_not_write(active_editor, test_api_instance):
    resp = _import(_logged_client(active_editor, test_api_instance), _csv(_csv_row("B1"), _csv_row("B2", lat="50.09")))
    assert resp.status == HTTP_201
    attributes = resp.json["data"]["attributes"]
    assert attributes["status"] == "dry_run"
    assert attributes["summary"]["create"] == 2
    assert not AedReport.objects.exists()


def test_import_creates_and_then_updates_by_source_id(active_editor, test_api_instance):
    client = _logged_client(active_editor, test_api_instance)
    assert _import(client, _csv(_csv_row("B1")), dry_run=False).json["data"]["attributes"]["status"] == "imported"
    report = AedReport.objects.get()
    assert report.source == "import"
    assert report.operator_name == active_editor.organizations.get().title

    report.status = AedReport.STATUS.verified
    report.save()
    resp = _import(client, _csv(_csv_row("B1", hours="Mo-Fr 08:00-16:00")), dry_run=False)
    assert resp.json["data"]["attributes"]["summary"]["update"] == 1
    report.refresh_from_db()
    assert AedReport.objects.count() == 1
    assert report.opening_hours == "Mo-Fr 08:00-16:00"
    assert report.status == AedReport.STATUS.submitted  # changed data goes back to verification


def test_import_with_errors_is_rejected_as_a_whole(active_editor, test_api_instance):
    content = _csv(_csv_row("B1"), _csv_row("B2", postal="31004"))
    resp = _import(_logged_client(active_editor, test_api_instance), content, dry_run=False)
    attributes = resp.json["data"]["attributes"]
    assert attributes["status"] == "rejected"
    assert [(e["row"], e["field"]) for e in attributes["errors"]] == [(3, "postal_code")]
    assert not AedReport.objects.exists()


def test_import_flags_duplicate_of_another_institution(active_editor, test_api_instance):
    other = AedReport.objects.create(**report_kwargs(organization=OrganizationFactory.create(), location_name="Basen miejski"))
    other.latitude, other.longitude = 50.08, 19.95
    other.save()
    resp = _import(_logged_client(active_editor, test_api_instance), _csv(_csv_row("B1", lat="50.080020")), dry_run=False)
    assert resp.json["data"]["attributes"]["actions"][0]["duplicate_of"] == str(other.pk)
    assert AedReport.objects.get(source_id="B1").possible_duplicate_of == other


def test_anonymous_user_cannot_import(client14):
    assert _import(client14, _csv(_csv_row("B1"))).status == HTTP_401


def test_public_export_contains_only_verified_records(client14):
    organization = OrganizationFactory.create()
    verified = AedReport.objects.create(**report_kwargs(organization=organization, status=AedReport.STATUS.verified))
    AedReport.objects.create(**report_kwargs(organization=organization, status=AedReport.STATUS.submitted, latitude=51))
    resp = client14.simulate_get("/aed-devices")
    assert resp.status == HTTP_200
    assert [item["id"] for item in resp.json["data"]] == [str(verified.uuid)]
    resp = client14.simulate_get("/aed-devices", params={"format": "csv"})
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.text.splitlines()[0].startswith("id,source_id,operator_name")
    assert len(resp.text.strip().splitlines()) == 2
