import pytest
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from falcon import HTTP_200, HTTP_201, HTTP_401, HTTP_403, HTTP_422, testing

from mcod.aed.models import AedReport
from mcod.lib.jwt import get_auth_token
from mcod.lib.triggers import session_store as session_store_create
from mcod.organizations.factories import OrganizationFactory

# All tests in this module depend on component
pytestmark = [pytest.mark.depends_on_component, pytest.mark.component_api, pytest.mark.django_db]

PAYLOAD = {"data": {"type": "aed_report", "attributes": {"location_name": "Dworzec Centralny", "notes": "Przy kasach"}}}


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
    assert resp.json["data"]["attributes"]["status"] == "submitted"


def test_editor_cannot_create_report_for_foreign_institution(active_editor, test_api_instance):
    foreign = OrganizationFactory.create()
    payload = {"data": {"type": "aed_report", "attributes": {"location_name": "X", "organization": foreign.pk}}}
    resp = _logged_client(active_editor, test_api_instance).simulate_post("/aed-reports", json=payload)
    assert resp.status == HTTP_422
    assert not AedReport.objects.exists()


def test_create_report_requires_location_name(active_editor, test_api_instance):
    payload = {"data": {"type": "aed_report", "attributes": {"notes": "Brak lokalizacji"}}}
    resp = _logged_client(active_editor, test_api_instance).simulate_post("/aed-reports", json=payload)
    assert resp.status == HTTP_422


def test_editor_lists_only_own_institution_reports(active_editor, test_api_instance):
    own = AedReport.objects.create(organization=active_editor.organizations.get(), location_name="Własny")
    AedReport.objects.create(organization=OrganizationFactory.create(), location_name="Obcy")
    resp = _logged_client(active_editor, test_api_instance).simulate_get("/aed-reports")
    assert resp.status == HTTP_200
    assert [item["id"] for item in resp.json["data"]] == [str(own.pk)]
