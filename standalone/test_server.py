"""Tests for the standalone demo server. Run: python -m unittest discover -s standalone

The same tests run on SQLite and — when AED_TEST_DATABASE_URL is set — on PostgreSQL (its demo tables are
dropped and recreated for every test), e.g. AED_TEST_DATABASE_URL=postgresql://aed:aed@127.0.0.1:5433/aed_test
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed import AED_COLUMNS, example_records  # noqa: E402
from server import make_server  # noqa: E402

PROVIDER_A = ("dostawca@demo.local", "Demo123!")
PROVIDER_B = ("dostawca2@demo.local", "Demo123!")
ADMIN = ("admin@demo.local", "Admin123!")

# A valid form submission: provider fields of the first example record, operator_name left to the default.
VALID_ATTRIBUTES = {name: value for name, value in example_records()[0].items() if name in AED_COLUMNS and value}
del VALID_ATTRIBUTES["operator_name"]


POSTGRES_URL = os.environ.get("AED_TEST_DATABASE_URL")


class DemoServerTest(unittest.TestCase):
    def database(self):
        return str(Path(self.tmp.name) / "test.sqlite3")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server("127.0.0.1", 0, self.database(), quiet=True, reset=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.RequestHandlerClass.store.db.close()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, token=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        headers = {"Content-Type": "application/vnd.api+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        conn.request(method, path, body=json.dumps(payload) if payload is not None else None, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        content_type = resp.getheader("Content-Type", "")
        return resp.status, (json.loads(raw) if "json" in content_type else raw.decode())

    def login(self, credentials):
        email, password = credentials
        payload = {"data": {"type": "user", "attributes": {"email": email, "password": password}}}
        status, body = self.request("POST", "/api/auth/login", payload)
        self.assertEqual(status, 201, body)
        return body["data"]["attributes"]["token"]

    def create(self, token, **changes):
        attributes = dict(VALID_ATTRIBUTES, **changes)
        return self.request("POST", "/api/aed-reports", {"data": {"type": "aed_report", "attributes": attributes}}, token)

    def verify(self, token, report_id, **attributes):
        payload = {"data": {"type": "aed_report", "id": str(report_id), "attributes": attributes}}
        return self.request("PATCH", f"/api/aed-reports/{report_id}", payload, token)

    # --- auth ---
    def test_login_with_wrong_password_fails(self):
        payload = {"data": {"type": "user", "attributes": {"email": PROVIDER_A[0], "password": "zle"}}}
        status, body = self.request("POST", "/api/auth/login", payload)
        self.assertEqual(status, 401)
        self.assertIn("errors", body)

    def test_login_returns_roles(self):
        payload = {"data": {"type": "user", "attributes": {"email": ADMIN[0], "password": ADMIN[1]}}}
        _status, body = self.request("POST", "/api/auth/login", payload)
        self.assertEqual(set(body["data"]["attributes"]["roles"]), {"admin", "editor"})

    def test_anonymous_cannot_list_or_create(self):
        self.assertEqual(self.request("GET", "/api/aed-reports")[0], 401)
        self.assertEqual(self.create(None)[0], 401)

    def test_logout_invalidates_token(self):
        token = self.login(PROVIDER_A)
        self.request("POST", "/api/auth/logout", token=token)
        self.assertEqual(self.request("GET", "/api/aed-reports", token=token)[0], 401)

    # --- provider ---
    def test_provider_creates_submitted_report_for_own_institution(self):
        token = self.login(PROVIDER_A)
        status, body = self.create(token, notes="Przy kasach", data_date="2026-11-01", indoor=False, latitude=50.1)
        self.assertEqual(status, 201, body)
        attrs = body["data"]["attributes"]
        self.assertEqual(attrs["status"], "submitted")
        self.assertEqual(attrs["source"], "form")
        self.assertEqual(attrs["data_date"], "2026-11-01")
        self.assertIs(attrs["indoor"], False)
        self.assertEqual(attrs["latitude"], 50.1)
        self.assertEqual(attrs["opening_hours"], VALID_ATTRIBUTES["opening_hours"])
        self.assertEqual(len(attrs["uuid"]), 36)
        self.assertIn("instytucja A", attrs["organization_title"])
        self.assertEqual(attrs["operator_name"], attrs["organization_title"])  # default

    def test_operator_name_can_differ_from_institution(self):
        token = self.login(PROVIDER_A)
        _status, body = self.create(token, operator_name="Ochotnicza Straż Pożarna Demo")
        self.assertEqual(body["data"]["attributes"]["operator_name"], "Ochotnicza Straż Pożarna Demo")

    def test_provider_sees_only_own_institution(self):
        token_b = self.login(PROVIDER_B)
        _status, body = self.request("GET", "/api/aed-reports", token=token_b)
        titles = {item["attributes"]["organization_title"] for item in body["data"]}
        self.assertTrue(titles)
        self.assertTrue(all("instytucja B" in title for title in titles))

    def test_provider_cannot_report_for_foreign_institution(self):
        token = self.login(PROVIDER_A)
        status, body = self.create(token, organization=2)
        self.assertEqual(status, 422)
        self.assertEqual(body["errors"][0]["source"]["pointer"], "/data/attributes/organization")

    def test_validation_errors_point_to_field(self):
        token = self.login(PROVIDER_A)
        status, body = self.create(token, location_name="  ", postal_code="31004", latitude="50,06", organization=99)
        self.assertEqual(status, 422)
        pointers = {error["source"]["pointer"].split("/")[-1]: error["detail"] for error in body["errors"]}
        self.assertEqual(set(pointers), {"location_name", "postal_code", "latitude", "organization"})
        self.assertEqual(pointers["postal_code"], "Kod pocztowy w formacie NN-NNN, np. 31-004.")

    def test_unknown_attribute_is_rejected(self):
        token = self.login(PROVIDER_A)
        status, body = self.create(token, cabinet_code="1234")
        self.assertEqual(status, 422)
        self.assertEqual(body["errors"][0]["source"]["pointer"], "/data/attributes/cabinet_code")

    def test_provider_cannot_verify(self):
        token = self.login(PROVIDER_A)
        report_id = self.create(token)[1]["data"]["id"]
        self.assertEqual(self.verify(token, report_id, status="verified")[0], 403)

    # --- admin ---
    def test_admin_lists_all_reports(self):
        token = self.login(ADMIN)
        _status, body = self.request("GET", "/api/aed-reports", token=token)
        titles = {item["attributes"]["organization_title"] for item in body["data"]}
        self.assertEqual(len(titles), 2)

    def test_admin_verifies_and_rejects(self):
        provider = self.login(PROVIDER_A)
        admin = self.login(ADMIN)
        first = self.create(provider)[1]["data"]["id"]
        second = self.create(provider)[1]["data"]["id"]

        status, body = self.verify(admin, first, status="verified")
        self.assertEqual(status, 202, body)
        self.assertEqual(body["data"]["attributes"]["status"], "verified")
        self.assertIsNotNone(body["data"]["attributes"]["verified_at"])

        self.assertEqual(self.verify(admin, second, status="rejected")[0], 422)  # comment required
        status, body = self.verify(admin, second, status="rejected", verification_comment="Brak godzin dostępności")
        self.assertEqual(status, 202, body)

        _status, body = self.request("GET", "/api/aed-reports", token=provider)
        comments = {item["id"]: item["attributes"]["verification_comment"] for item in body["data"]}
        self.assertEqual(comments[second], "Brak godzin dostępności")

    def test_already_verified_report_cannot_be_verified_again(self):
        provider = self.login(PROVIDER_A)
        admin = self.login(ADMIN)
        report_id = self.create(provider)[1]["data"]["id"]
        self.verify(admin, report_id, status="verified")
        self.assertEqual(self.verify(admin, report_id, status="rejected", verification_comment="x")[0], 409)

    # --- import from files ---
    def import_file(self, token, content, file_format="csv", dry_run=True):
        payload = {
            "data": {"type": "aed_report_import", "attributes": {"format": file_format, "content": content, "dry_run": dry_run}}
        }
        return self.request("POST", "/api/aed-report-imports", payload, token)

    def csv_file(self, *rows):
        header = "source_id,location_name,location_description,indoor,commune,city,street_number,postal_code,latitude,longitude,access,opening_hours,device_status,data_date"
        return "\n".join([header] + list(rows)) + "\n"

    @staticmethod
    def csv_row(source_id, name="Basen miejski", lat="50.080000", lon="19.950000", postal="31-004", hours="24/7"):
        return f"{source_id},{name},hol,true,Kraków,Kraków,3,{postal},{lat},{lon},public,{hours},operational,2026-11-20"

    def test_import_requires_editor(self):
        self.assertEqual(self.import_file(None, self.csv_file(self.csv_row("B1")))[0], 401)

    def test_dry_run_does_not_write(self):
        token = self.login(PROVIDER_A)
        before = len(self.request("GET", "/api/aed-reports", token=token)[1]["data"])
        status, body = self.import_file(
            token, self.csv_file(self.csv_row("B1"), self.csv_row("B2", name="Szkoła", lat="50.090000"))
        )
        self.assertEqual(status, 201, body)
        attrs = body["data"]["attributes"]
        self.assertEqual(attrs["status"], "dry_run")
        self.assertEqual(attrs["summary"]["create"], 2)
        self.assertEqual(len(self.request("GET", "/api/aed-reports", token=token)[1]["data"]), before)

    def test_import_creates_then_updates_by_source_id(self):
        token = self.login(PROVIDER_A)
        status, body = self.import_file(token, self.csv_file(self.csv_row("B1")), dry_run=False)
        self.assertEqual(body["data"]["attributes"]["status"], "imported", body)
        reports = self.request("GET", "/api/aed-reports", token=token)[1]["data"]
        imported = [r for r in reports if r["attributes"]["source_id"] == "B1"]
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["attributes"]["source"], "import")
        self.assertEqual(imported[0]["attributes"]["operator_name"], imported[0]["attributes"]["organization_title"])

        # same file again: nothing changes; changed opening hours: the record is updated, not duplicated
        _status, body = self.import_file(token, self.csv_file(self.csv_row("B1")), dry_run=False)
        self.assertEqual(body["data"]["attributes"]["summary"]["unchanged"], 1)
        _status, body = self.import_file(token, self.csv_file(self.csv_row("B1", hours="Mo-Fr 08:00-16:00")), dry_run=False)
        self.assertEqual(body["data"]["attributes"]["summary"]["update"], 1)
        reports = self.request("GET", "/api/aed-reports", token=token)[1]["data"]
        imported = [r for r in reports if r["attributes"]["source_id"] == "B1"]
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["attributes"]["opening_hours"], "Mo-Fr 08:00-16:00")
        self.assertEqual(imported[0]["attributes"]["status"], "submitted")

    def test_file_with_errors_is_rejected_as_a_whole(self):
        token = self.login(PROVIDER_A)
        before = len(self.request("GET", "/api/aed-reports", token=token)[1]["data"])
        content = self.csv_file(self.csv_row("B1"), self.csv_row("B2", name="Szkoła", postal="31004"))
        _status, body = self.import_file(token, content, dry_run=False)
        attrs = body["data"]["attributes"]
        self.assertEqual(attrs["status"], "rejected")
        self.assertEqual(
            attrs["errors"], [{"row": 3, "field": "postal_code", "message": "Kod pocztowy w formacie NN-NNN, np. 31-004."}]
        )
        self.assertEqual(len(self.request("GET", "/api/aed-reports", token=token)[1]["data"]), before)

    def test_unreadable_file_is_rejected(self):
        token = self.login(PROVIDER_A)
        _status, body = self.import_file(token, "a;b\n1;2\n")
        self.assertEqual(body["data"]["attributes"]["status"], "rejected")
        self.assertIn("Nieznane kolumny", body["data"]["attributes"]["file_error"])

    def test_invalid_import_request(self):
        token = self.login(PROVIDER_A)
        status, body = self.import_file(token, "", file_format="xlsx")
        self.assertEqual(status, 422)
        pointers = {e["source"]["pointer"].split("/")[-1] for e in body["errors"]}
        self.assertEqual(pointers, {"format", "content"})

    def test_duplicate_of_other_institution_is_flagged(self):
        # example record 3 (institution B): Dworzec Główny, 54.355600, 18.643400
        token = self.login(PROVIDER_A)
        row = self.csv_row("D1", name="Dworzec Główny Gdańsk", lat="54.355630", lon="18.643420", postal="80-803")
        _status, body = self.import_file(token, self.csv_file(row.replace("Kraków,Kraków", "Gdańsk,Gdańsk")), dry_run=False)
        action = body["data"]["attributes"]["actions"][0]
        self.assertIsNotNone(action["duplicate_of"])
        self.assertLessEqual(action["duplicate_distance_m"], 15)
        reports = self.request("GET", "/api/aed-reports", token=self.login(ADMIN))[1]["data"]
        flagged = next(r for r in reports if r["attributes"]["source_id"] == "D1")
        self.assertIn("Dworzec", flagged["attributes"]["possible_duplicate"]["location_name"])

    def test_form_submission_is_checked_for_duplicates(self):
        token = self.login(PROVIDER_A)
        # VALID_ATTRIBUTES = example record 1 itself -> duplicate of the seeded record
        _status, body = self.create(token)
        self.assertEqual(body["data"]["attributes"]["possible_duplicate"]["distance_m"], 0)

    # --- public dataset ---
    def test_export_contains_only_verified_records(self):
        status, body = self.request("GET", "/api/aed-devices")
        self.assertEqual(status, 200)
        self.assertEqual(body["meta"]["count"], 2)  # seed: 2 verified examples
        self.assertEqual({d["type"] for d in body["data"]}, {"aed_device"})

    def test_export_formats(self):
        status, text = self.request("GET", "/api/aed-devices?format=csv")
        self.assertEqual(status, 200)
        self.assertTrue(text.startswith("id,source_id,operator_name"))
        self.assertEqual(len(text.strip().splitlines()), 3)
        _status, geojson = self.request("GET", "/api/aed-devices?format=geojson")
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(len(geojson["features"]), 2)
        self.assertEqual(self.request("GET", "/api/aed-devices?format=pdf")[0], 400)

    def test_export_can_be_imported_again(self):
        _status, text = self.request("GET", "/api/aed-devices?format=csv")
        _status, body = self.import_file(self.login(PROVIDER_A), text)
        self.assertEqual(body["data"]["attributes"]["errors"], [])

    def test_serves_schema_files(self):
        status, text = self.request("GET", "/schema/aed-template.csv")
        self.assertEqual(status, 200)
        self.assertTrue(text.startswith("source_id,"))
        self.assertEqual(self.request("GET", "/schema/../standalone/seed.py")[0], 404)

    # --- static & config ---
    def test_serves_frontend_and_api_config(self):
        status, body = self.request("GET", "/index.html")
        self.assertEqual(status, 200)
        self.assertIn("Zgłoś dostępność urządzenia AED", body)
        status, body = self.request("GET", "/config.js")
        self.assertEqual(status, 200)
        self.assertIn('mode: "api"', body)

    def test_path_traversal_is_blocked(self):
        status, _body = self.request("GET", "/../standalone/seed.py")
        self.assertEqual(status, 404)


@unittest.skipUnless(POSTGRES_URL, "set AED_TEST_DATABASE_URL to run the tests on PostgreSQL")
class PostgresDemoServerTest(DemoServerTest):
    def database(self):
        return POSTGRES_URL


if __name__ == "__main__":
    unittest.main()
