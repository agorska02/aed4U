import pytest
from django.test import Client
from django.urls import reverse

from mcod.aed.models import AedReport
from mcod.organizations.factories import OrganizationFactory

pytestmark = pytest.mark.django_db

CHANGELIST_URL = "admin:aed_aedreport_changelist"


@pytest.fixture
def editor_admin_client(active_editor) -> Client:
    client = Client()
    client.force_login(active_editor)
    return client


def test_editor_sees_only_own_institution_reports(active_editor, editor_admin_client):
    AedReport.objects.create(organization=active_editor.organizations.get(), location_name="Własny AED")
    AedReport.objects.create(organization=OrganizationFactory.create(), location_name="Obcy AED")
    resp = editor_admin_client.get(reverse(CHANGELIST_URL))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Własny AED" in content
    assert "Obcy AED" not in content


def test_editor_cannot_verify_report(active_editor, editor_admin_client):
    report = AedReport.objects.create(
        organization=active_editor.organizations.get(), location_name="AED", status=AedReport.STATUS.submitted
    )
    editor_admin_client.post(reverse(CHANGELIST_URL), {"action": "mark_verified", "_selected_action": [report.pk]}, follow=True)
    report.refresh_from_db()
    assert report.status == AedReport.STATUS.submitted


def test_admin_verifies_submitted_report(admin, django_admin_client):
    report = AedReport.objects.create(
        organization=OrganizationFactory.create(), location_name="AED", status=AedReport.STATUS.submitted
    )
    resp = django_admin_client.post(
        reverse(CHANGELIST_URL), {"action": "mark_verified", "_selected_action": [report.pk]}, follow=True
    )
    assert resp.status_code == 200
    report.refresh_from_db()
    assert report.status == AedReport.STATUS.verified
    assert report.verified_by == admin
    assert report.verified_at is not None
