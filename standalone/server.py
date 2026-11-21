"""Standalone demo server for the AED prototype — Python standard library only, no portal code.

Serves hackathon/frontend and an API with the same contract as the portal module (hackathon/backend/aed):
JSON:API, JWT-like bearer token from POST /api/auth/login, GET/POST /api/aed-reports.
Demo-only extension: PATCH /api/aed-reports/{id} (administrator verifies a report; in the portal this is
done in the Administration Panel).

Usage: python standalone/server.py [--port 8090] [--db PATH] [--reset]
NOT for production: demo accounts, no rate limiting, no HTTPS.
"""

import argparse
import datetime
import json
import re
import secrets
import sqlite3
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from seed import DEFAULT_DB, init_db, now_iso, seed, verify_password

HERE = Path(__file__).resolve().parent
FRONTEND_DIR = HERE.parent / "frontend"
JSONAPI = "application/vnd.api+json"
STATUSES = ("draft", "submitted", "verified", "rejected")
REPORT_DETAIL = re.compile(r"^/api/(?:\d+\.\d+/)?aed-reports/(\d+)$")
REPORT_LIST = re.compile(r"^/api/(?:\d+\.\d+/)?aed-reports$")
CONFIG_JS = 'window.AED_CONFIG = {mode: "api", apiBase: "/api", demo: true, adminPanelUrl: null};\n'


class ApiError(Exception):
    def __init__(self, status, title, detail=None, field=None):
        super().__init__(detail or title)
        self.status, self.title, self.detail, self.field = status, title, detail or title, field

    def to_body(self):
        error = {"status": str(self.status.value), "title": self.title, "detail": self.detail, "code": self.status.phrase}
        if self.field:
            error["source"] = {"pointer": f"/data/attributes/{self.field}"}
        return {"errors": [error]}


class Store:
    """Thread-safe access to the SQLite demo database."""

    def __init__(self, path):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        seed(self.conn)

    def query(self, sql, params=()):
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def execute(self, sql, params=()):
        with self.lock:
            cursor = self.conn.execute(sql, params)
            self.conn.commit()
            return cursor.lastrowid

    # --- domain ---
    def user_by_token(self, token):
        rows = self.query("SELECT u.* FROM users u JOIN sessions s ON s.user_id = u.id WHERE s.token = ?", (token,))
        return rows[0] if rows else None

    def organization_ids(self, user):
        if user["is_superuser"]:
            return [row["id"] for row in self.query("SELECT id FROM organizations")]
        return [
            row["organization_id"]
            for row in self.query("SELECT organization_id FROM user_organizations WHERE user_id = ?", (user["id"],))
        ]

    def reports(self, user, report_id=None):
        sql = "SELECT r.*, o.title AS organization_title FROM aed_aedreport r JOIN organizations o ON o.id = r.organization_id"
        clauses, params = [], []
        if not user["is_superuser"]:
            clauses.append("r.organization_id IN (SELECT organization_id FROM user_organizations WHERE user_id = ?)")
            params.append(user["id"])
        if report_id is not None:
            clauses.append("r.id = ?")
            params.append(report_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self.query(sql + " ORDER BY r.created DESC, r.id DESC", params)


def serialize_report(row, api_url):
    return {
        "type": "aed_report",
        "id": str(row["id"]),
        "attributes": {
            "organization_title": row["organization_title"],
            "location_name": row["location_name"],
            "notes": row["notes"],
            "data_date": row["data_date"],
            "status": row["status"],
            "verification_comment": row["verification_comment"],
            "verified_at": row["verified_at"],
            "created": row["created"],
            "modified": row["modified"],
        },
        "links": {"self": f"{api_url}/aed-reports/{row['id']}"},
    }


def roles(user):
    result = []
    if user["is_superuser"]:
        result.append("admin")
    if user["is_staff"]:
        result.append("editor")
    return result


def attributes_of(payload, object_type):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or data.get("type") != object_type or not isinstance(data.get("attributes"), dict):
        raise ApiError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Field error",
            f'Expected {{"data": {{"type": "{object_type}", "attributes": {{...}}}}}}',
        )
    return data["attributes"]


def validate_report(attrs):
    location_name = attrs.get("location_name")
    if not isinstance(location_name, str) or not location_name.strip():
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Pole wymagane.", "location_name")
    if len(location_name) > 300:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Maksymalnie 300 znaków.", "location_name")
    notes = attrs.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 3000:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Maksymalnie 3000 znaków.", "notes")
    data_date = attrs.get("data_date") or datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(data_date)
    except (TypeError, ValueError):
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Data w formacie rrrr-mm-dd.", "data_date")
    organization = attrs.get("organization")
    if organization is not None and not isinstance(organization, int):
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Nieprawidłowy identyfikator instytucji.", "organization")
    return {"location_name": location_name.strip(), "notes": notes.strip(), "data_date": data_date, "organization": organization}


class Handler(SimpleHTTPRequestHandler):
    store = None  # set in make_server()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def log_message(self, format, *args):  # noqa: A002 - keep stdlib signature
        if not getattr(self.server, "quiet", False):
            super().log_message(format, *args)

    # --- routing ---
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/config.js":
            return self._send_raw(HTTPStatus.OK, CONFIG_JS.encode(), "application/javascript; charset=utf-8")
        if path.startswith("/api/"):
            return self._api("GET", path)
        return super().do_GET()

    def do_POST(self):
        self._api("POST", urlsplit(self.path).path)

    def do_PATCH(self):
        self._api("PATCH", urlsplit(self.path).path)

    def _api(self, method, path):
        try:
            status, body = self._dispatch(method, path)
        except ApiError as exc:
            status, body = exc.status, exc.to_body()
        self._send_raw(status, json.dumps(body, ensure_ascii=False).encode(), JSONAPI)

    def _dispatch(self, method, path):
        if path == "/api/auth/login" and method == "POST":
            return self._login()
        if path == "/api/auth/logout" and method == "POST":
            return self._logout()
        if REPORT_LIST.match(path):
            if method == "GET":
                return self._list_reports()
            if method == "POST":
                return self._create_report()
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")
        match = REPORT_DETAIL.match(path)
        if match and method == "PATCH":
            return self._verify_report(int(match.group(1)))
        raise ApiError(HTTPStatus.NOT_FOUND, "Not found")

    # --- helpers ---
    def _send_raw(self, status, payload, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 100_000:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Payload too large")
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Malformed JSON")

    def _api_url(self):
        return f"http://{self.headers.get('Host', 'localhost')}/api"

    def _user(self, require_roles=("editor", "admin")):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise ApiError(HTTPStatus.UNAUTHORIZED, "401 Unauthorized", "Missing authorization header")
        user = self.store.user_by_token(header[len("Bearer ") :])
        if not user:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "401 Unauthorized", "Invalid authorization header")
        if not set(require_roles) & set(roles(user)):
            raise ApiError(HTTPStatus.FORBIDDEN, "403 Forbidden", "Additional permissions are required!")
        return user

    # --- endpoints ---
    def _login(self):
        attrs = attributes_of(self._json(), "user")
        email = str(attrs.get("email") or "").strip().lower()
        rows = self.store.query("SELECT * FROM users WHERE email = ?", (email,))
        if not rows or not verify_password(str(attrs.get("password") or ""), rows[0]["password_hash"]):
            raise ApiError(HTTPStatus.UNAUTHORIZED, "401 Unauthorized", "Nieprawidłowy e-mail lub hasło.")
        user = rows[0]
        token = secrets.token_urlsafe(32)
        self.store.execute("INSERT INTO sessions (token, user_id, created) VALUES (?, ?, ?)", (token, user["id"], now_iso()))
        attributes = {"email": user["email"], "fullname": user["fullname"], "token": token, "roles": roles(user)}
        return HTTPStatus.CREATED, {"data": {"type": "user", "id": str(user["id"]), "attributes": attributes}}

    def _logout(self):
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            self.store.execute("DELETE FROM sessions WHERE token = ?", (header[len("Bearer ") :],))
        return HTTPStatus.CREATED, {"data": {"type": "logout", "attributes": {"is_logged_out": True}}}

    def _list_reports(self):
        user = self._user()
        data = [serialize_report(row, self._api_url()) for row in self.store.reports(user)]
        return HTTPStatus.OK, {"data": data, "meta": {"count": len(data)}}

    def _create_report(self):
        user = self._user()
        attrs = validate_report(attributes_of(self._json(), "aed_report"))
        allowed = self.store.organization_ids(user)
        organization = attrs.pop("organization")
        if organization is not None:
            if organization not in allowed:
                raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Nie należysz do tej instytucji.", "organization")
        elif not user["is_superuser"] and len(allowed) == 1:
            organization = allowed[0]
        else:
            raise ApiError(
                HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Wybierz instytucję, której dotyczy zgłoszenie.", "organization"
            )
        timestamp = now_iso()
        report_id = self.store.execute(
            "INSERT INTO aed_aedreport (organization_id, location_name, notes, data_date, status, created, created_by_id,"
            " modified, modified_by_id) VALUES (?, ?, ?, ?, 'submitted', ?, ?, ?, ?)",
            (
                organization,
                attrs["location_name"],
                attrs["notes"],
                attrs["data_date"],
                timestamp,
                user["id"],
                timestamp,
                user["id"],
            ),
        )
        return HTTPStatus.CREATED, {"data": serialize_report(self.store.reports(user, report_id)[0], self._api_url())}

    def _verify_report(self, report_id):
        user = self._user(require_roles=("admin",))
        attrs = attributes_of(self._json(), "aed_report")
        status = attrs.get("status")
        if status not in ("verified", "rejected"):
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Dozwolone: verified, rejected.", "status")
        comment = attrs.get("verification_comment", "")
        if not isinstance(comment, str) or len(comment) > 3000:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Maksymalnie 3000 znaków.", "verification_comment")
        if status == "rejected" and not comment.strip():
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", "Podaj powód odrzucenia.", "verification_comment")
        rows = self.store.reports(user, report_id)
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Not found")
        if rows[0]["status"] != "submitted":
            raise ApiError(HTTPStatus.CONFLICT, "409 Conflict", "Można weryfikować tylko zgłoszenia przesłane do weryfikacji.")
        timestamp = now_iso()
        self.store.execute(
            "UPDATE aed_aedreport SET status = ?, verification_comment = ?, verified_by_id = ?, verified_at = ?,"
            " modified = ?, modified_by_id = ? WHERE id = ?",
            (status, comment.strip(), user["id"], timestamp, timestamp, user["id"], report_id),
        )
        return HTTPStatus.ACCEPTED, {"data": serialize_report(self.store.reports(user, report_id)[0], self._api_url())}


def make_server(host, port, db_path, quiet=False):
    handler = type("BoundHandler", (Handler,), {"store": Store(db_path)})
    server = ThreadingHTTPServer((host, port), handler)
    server.quiet = quiet
    return server


def main():
    parser = argparse.ArgumentParser(description="AED prototype — standalone demo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--reset", action="store_true", help="recreate the demo database")
    args = parser.parse_args()
    if args.reset and args.db.exists():
        args.db.unlink()
    server = make_server(args.host, args.port, args.db)
    print(f"AED demo: http://{args.host}:{args.port}  (database: {args.db})  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
