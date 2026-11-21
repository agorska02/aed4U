"""Tests for the standalone demo server. Run: python -m unittest discover -s standalone"""

import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server import make_server  # noqa: E402

PROVIDER_A = ("dostawca@demo.local", "Demo123!")
PROVIDER_B = ("dostawca2@demo.local", "Demo123!")
ADMIN = ("admin@demo.local", "Admin123!")


class DemoServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server("127.0.0.1", 0, Path(self.tmp.name) / "test.sqlite3", quiet=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.RequestHandlerClass.store.conn.close()
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

    def create(self, token, **attributes):
        attributes.setdefault("location_name", "Dworzec – hala")
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
        status, body = self.create(token, notes="Przy kasach", data_date="2026-11-01")
        self.assertEqual(status, 201, body)
        attrs = body["data"]["attributes"]
        self.assertEqual(attrs["status"], "submitted")
        self.assertEqual(attrs["data_date"], "2026-11-01")
        self.assertIn("instytucja A", attrs["organization_title"])

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
        status, body = self.create(token, location_name="  ")
        self.assertEqual(status, 422)
        self.assertEqual(body["errors"][0]["source"]["pointer"], "/data/attributes/location_name")
        status, body = self.create(token, data_date="21.11.2026")
        self.assertEqual(status, 422)
        self.assertEqual(body["errors"][0]["source"]["pointer"], "/data/attributes/data_date")

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


if __name__ == "__main__":
    unittest.main()
