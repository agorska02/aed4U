"""Standalone demo server for the AED prototype — Python standard library only, no portal code.

Serves hackathon/frontend (and hackathon/schema under /schema/) and an API with the same contract as the
portal module (hackathon/backend/aed):
- POST /api/auth/login, /api/auth/logout — JWT-like bearer token
- GET /api/auth/user — the logged-in user with the profiles of their institutions
- GET/POST /api/aed-reports — provider's reports / new report from the form
- POST /api/aed-report-imports — CSV/JSON/GeoJSON file from a data provider (dry run or import)
- GET /api/aed-devices?format=csv|json|geojson — public unified dataset (verified records only)
AED attributes, validation, import and export rules come from the shared, Django-independent modules
backend/aed/validation.py and backend/aed/importing.py (reference data scope: schema/aed.schema.json).
Demo-only extension: PATCH /api/aed-reports/{id} (administrator verifies a report; in the portal this is
done in the Administration Panel).

Database: SQLite file (default, standard library only) or PostgreSQL (`--db postgresql://…` or the
AED_DATABASE_URL environment variable; needs psycopg2) — see db.py and docker-compose.yml.

Usage: python standalone/server.py [--port 8090] [--db PATH_OR_POSTGRES_URL] [--reset]
NOT for production: demo accounts, no rate limiting, no HTTPS.
"""

import argparse
import datetime
import json
import re
import secrets
import traceback
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from seed import (
    AED_COLUMNS,
    DEFAULT_DB,
    connect,
    db_values,
    importing,
    init_db,
    insert_report,
    institution_values,
    now_iso,
    seed,
    validate_record,
    verify_password,
)

HERE = Path(__file__).resolve().parent
FRONTEND_DIR = HERE.parent / "frontend"
SCHEMA_DIR = HERE.parent / "schema"
JSONAPI = "application/vnd.api+json"
MAX_BODY = 2_500_000  # bytes; imports carry the file content (max 2 MB of text)
VERSION = r"(?:\d+\.\d+/)?"
REPORT_DETAIL = re.compile(rf"^/api/{VERSION}aed-reports/(\d+)$")
REPORT_LIST = re.compile(rf"^/api/{VERSION}aed-reports$")
IMPORTS = re.compile(rf"^/api/{VERSION}aed-report-imports$")
DEVICES = re.compile(rf"^/api/{VERSION}aed-devices$")
CONFIG_JS = 'window.AED_CONFIG = {{mode: "api", apiBase: "/api", demo: true, adminPanelUrl: null, database: "{0}"}};\n'
EXPORT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "geojson": "application/geo+json; charset=utf-8",
}
REPORTED_ACTIONS = 500  # at most this many planned actions are returned in an import response


class ApiError(Exception):
    def __init__(self, status, title, detail=None, field=None, field_errors=None):
        super().__init__(detail or title)
        self.status, self.title, self.detail = status, title, detail or title
        # {field: message}; one JSON:API error per field, like mcod's 422 responses
        self.field_errors = field_errors or ({field: self.detail} if field else {})

    def to_body(self):
        base = {"status": str(self.status.value), "title": self.title, "code": self.status.phrase}
        if not self.field_errors:
            return {"errors": [dict(base, detail=self.detail)]}
        return {
            "errors": [
                dict(base, detail=message, source={"pointer": f"/data/attributes/{field}"})
                for field, message in self.field_errors.items()
            ]
        }


class Store:
    """Thread-safe access to the demo database (SQLite or PostgreSQL, see db.py)."""

    def __init__(self, target, reset=False):
        self.db = connect(target)
        self.lock = self.db.lock
        init_db(self.db, reset=reset)
        seed(self.db)

    def query(self, sql, params=()):
        return self.db.query(sql, params)

    def execute(self, sql, params=()):
        self.db.execute(sql, params)

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

    def organization(self, organization_id):
        return self.query("SELECT * FROM organizations WHERE id = ?", (organization_id,))[0]

    def organizations_of(self, user):
        ids = self.organization_ids(user)
        return [org for org in self.query("SELECT * FROM organizations ORDER BY id") if org["id"] in ids]

    def reports(self, user, report_id=None):
        sql = (
            "SELECT r.*, o.title AS organization_title, d.uuid AS duplicate_uuid, d.location_name AS duplicate_name"
            " FROM aed_aedreport r JOIN organizations o ON o.id = r.organization_id"
            " LEFT JOIN aed_aedreport d ON d.id = r.possible_duplicate_of_id"
        )
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

    def planning_records(self, organization_id=None):
        """Records as dicts (schema fields + id) for importing.plan_import / find_duplicate."""
        sql = "SELECT * FROM aed_aedreport"
        params = ()
        if organization_id is not None:
            sql += " WHERE organization_id = ?"
            params = (organization_id,)
        return self.query(sql, params)

    def verified_records(self):
        return self.query("SELECT * FROM aed_aedreport WHERE status = 'verified' ORDER BY id")


# Collected for the portal administrator only — never sent to providers nor published.
ADMIN_ONLY_COLUMNS = ("internal_contact_phone", "serial_number")


def serialize_report(row, api_url, user):
    attributes = {name: row[name] for name in AED_COLUMNS if user["is_superuser"] or name not in ADMIN_ONLY_COLUMNS}
    attributes["indoor"] = bool(row["indoor"])
    for name in ("uuid", "source", "organization_title", "status", "verification_comment", "verified_at", "created", "modified"):
        attributes[name] = row[name]
    attributes["possible_duplicate"] = (
        {
            "id": str(row["possible_duplicate_of_id"]),
            "uuid": row["duplicate_uuid"],
            "location_name": row["duplicate_name"],
            "distance_m": row["possible_duplicate_distance_m"],
        }
        if row["possible_duplicate_of_id"]
        else None
    )
    return {
        "type": "aed_report",
        "id": str(row["id"]),
        "attributes": attributes,
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


def import_response(import_id, status, file_format, plan=None, file_error=None):
    plan = plan or {"errors": [], "actions": [], "summary": None}
    actions = [
        {
            "row": a["row"],
            "action": a["action"],
            "location_name": a["values"].get("location_name"),
            "duplicate_of": None if a["duplicate_of"] is None else str(a["duplicate_of"]),
            "duplicate_of_row": a["duplicate_of_row"],
            "duplicate_distance_m": a["duplicate_distance_m"],
        }
        for a in plan["actions"][:REPORTED_ACTIONS]
    ]
    attributes = {
        "status": status,
        "format": file_format,
        "file_error": file_error,
        "summary": plan["summary"],
        "errors": plan["errors"],
        "actions": actions,
    }
    return {"data": {"type": "aed_report_import", "id": import_id, "attributes": attributes}}


class Handler(SimpleHTTPRequestHandler):
    store = None  # set in make_server()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def log_message(self, format, *args):  # noqa: A002 - keep stdlib signature
        if not getattr(self.server, "quiet", False):
            super().log_message(format, *args)

    def translate_path(self, path):
        # /schema/* is served from hackathon/schema (templates and dictionaries for data providers).
        clean = urlsplit(path).path
        if clean.startswith("/schema/"):
            name = clean[len("/schema/") :]
            target = (SCHEMA_DIR / name).resolve()
            if SCHEMA_DIR.resolve() in target.parents:
                return str(target)
            return str(SCHEMA_DIR / "__not_found__")
        return super().translate_path(path)

    def guess_type(self, path):
        if str(path).endswith(".csv"):
            return "text/csv; charset=utf-8"
        if str(path).endswith(".md"):
            return "text/markdown; charset=utf-8"
        if str(path).endswith(".json"):
            return "application/json; charset=utf-8"
        return super().guess_type(path)

    # --- routing ---
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/config.js":
            config = CONFIG_JS.format(self.store.db.label).encode()
            return self._send_raw(HTTPStatus.OK, config, "application/javascript; charset=utf-8")
        if path.startswith("/api/"):
            return self._api("GET", path)
        return super().do_GET()

    def do_POST(self):
        self._api("POST", urlsplit(self.path).path)

    def do_PATCH(self):
        self._api("PATCH", urlsplit(self.path).path)

    def _api(self, method, path):
        try:
            self._read_body()
            result = self._dispatch(method, path)
        except ApiError as exc:
            result = (exc.status, exc.to_body())
        except Exception:  # keep the JSON:API contract and log the traceback
            self.log_error("Unhandled error in %s %s", method, path)
            traceback.print_exc()
            result = (HTTPStatus.INTERNAL_SERVER_ERROR, ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "Server error").to_body())
        if len(result) == 3:  # (status, raw bytes, headers) — file downloads
            status, payload, headers = result
            return self._send_raw(status, payload, headers.pop("Content-Type"), headers)
        status, body = result
        self._send_raw(status, json.dumps(body, ensure_ascii=False).encode(), JSONAPI)

    def _dispatch(self, method, path):
        if path == "/api/auth/login" and method == "POST":
            return self._login()
        if path == "/api/auth/user" and method == "GET":
            return self._current_user()
        if path == "/api/auth/logout" and method == "POST":
            return self._logout()
        if REPORT_LIST.match(path):
            if method == "GET":
                return self._list_reports()
            if method == "POST":
                return self._create_report()
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")
        if IMPORTS.match(path):
            if method == "POST":
                return self._import_reports()
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")
        if DEVICES.match(path):
            if method == "GET":
                return self._export_devices()
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")
        match = REPORT_DETAIL.match(path)
        if match and method == "PATCH":
            return self._verify_report(int(match.group(1)))
        raise ApiError(HTTPStatus.NOT_FOUND, "Not found")

    # --- helpers ---
    def _send_raw(self, status, payload, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self):
        # Read the whole body up front, also for requests rejected early (401/403): an unread body makes
        # some clients (Windows) see a reset connection instead of the error response.
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.close_connection = True
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Payload too large")
        self._body = self.rfile.read(length) if length else b""

    def _json(self):
        try:
            return json.loads(self._body or b"{}")
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

    def _resolve_organization(self, user, requested):
        """(organization_id, error message) — same rules as the portal view."""
        allowed = self.store.organization_ids(user)
        if requested is not None:
            if isinstance(requested, bool) or not isinstance(requested, int) or requested not in allowed:
                return None, "Nie należysz do tej instytucji."
            return requested, None
        if not user["is_superuser"] and len(allowed) == 1:
            return allowed[0], None
        return None, "Wybierz instytucję, której dotyczy zgłoszenie."

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

    def _current_user(self):
        user = self._user()
        institutions = [
            {"id": org["id"], "title": org["title"], "regon": org["regon"], "phone": org["phone"], "email": org["email"]}
            for org in self.store.organizations_of(user)
        ]
        attributes = {"email": user["email"], "fullname": user["fullname"], "roles": roles(user), "institutions": institutions}
        return HTTPStatus.OK, {"data": {"type": "user", "id": str(user["id"]), "attributes": attributes}}

    def _logout(self):
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            self.store.execute("DELETE FROM sessions WHERE token = ?", (header[len("Bearer ") :],))
        return HTTPStatus.CREATED, {"data": {"type": "logout", "attributes": {"is_logged_out": True}}}

    def _list_reports(self):
        user = self._user()
        data = [serialize_report(row, self._api_url(), user) for row in self.store.reports(user)]
        return HTTPStatus.OK, {"data": data, "meta": {"count": len(data)}}

    def _create_report(self):
        user = self._user()
        attrs = dict(attributes_of(self._json(), "aed_report"))
        requested_org = attrs.pop("organization", None)
        organization, org_error = self._resolve_organization(user, requested_org)
        if org_error:  # validate the record too, so the form shows every problem at once
            errors = dict(validate_record(attrs)[1])
            errors["organization"] = org_error
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", field_errors=errors)
        # The form is a one-row import: same rules (institution profile, device identity, duplicates).
        with self.store.lock:
            plan = importing.plan_import(
                [(1, attrs)],
                self.store.planning_records(organization),
                self.store.planning_records(),
                institution_values(self.store.organization(organization)),
            )
            if plan["errors"]:
                errors = {e["field"]: e["message"] for e in plan["errors"]}
                raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", field_errors=errors)
            report_id = self._apply_import(plan, organization, user, source="form")[0]
        return HTTPStatus.CREATED, {"data": serialize_report(self.store.reports(user, report_id)[0], self._api_url(), user)}

    def _import_reports(self):
        user = self._user()
        attrs = attributes_of(self._json(), "aed_report_import")
        file_format = attrs.get("format")
        content = attrs.get("content")
        dry_run = attrs.get("dry_run", True)
        errors = {}
        if file_format not in importing.FORMATS:
            errors["format"] = "Dozwolone: " + ", ".join(importing.FORMATS) + "."
        if not isinstance(content, str) or not content.strip():
            errors["content"] = "Dołącz zawartość pliku."
        if not isinstance(dry_run, bool):
            errors["dry_run"] = "Dozwolone wartości: true, false."
        organization, org_error = self._resolve_organization(user, attrs.get("organization"))
        if org_error:
            errors["organization"] = org_error
        if errors:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "Field error", field_errors=errors)

        import_id = str(uuid.uuid4())
        try:
            rows = importing.parse_file(content, file_format)
        except importing.ImportFileError as exc:
            return HTTPStatus.CREATED, import_response(import_id, "rejected", file_format, file_error=str(exc))
        with self.store.lock:
            plan = importing.plan_import(
                rows,
                self.store.planning_records(organization),
                self.store.planning_records(),
                institution_values(self.store.organization(organization)),
            )
            if plan["errors"]:
                status = "rejected"
            elif dry_run:
                status = "dry_run"
            else:
                status = "imported"
                self._apply_import(plan, organization, user)
        return HTTPStatus.CREATED, import_response(import_id, status, file_format, plan)

    def _apply_import(self, plan, organization, user, source="import"):
        """Apply planned actions in one transaction; in-file duplicates point to the record created for that row.

        Returns the ids of the records the rows were applied to (created, updated or unchanged), in row order.
        """
        db = self.store.db
        created_for_row = {}
        record_ids = []
        timestamp = now_iso()
        with db.transaction():
            for action in plan["actions"]:
                if action["action"] == "unchanged":
                    record_ids.append(action["record_id"])
                    continue
                duplicate_id = action["duplicate_of"]
                if action["duplicate_of_row"] is not None:
                    duplicate_id = created_for_row.get(action["duplicate_of_row"])
                values = db_values(action["values"])
                if action["action"] == "create":
                    created_for_row[action["row"]] = insert_report(
                        db,
                        values,
                        organization_id=organization,
                        user_id=user["id"],
                        status="submitted",
                        source=source,
                        timestamp=timestamp,
                        possible_duplicate_of_id=duplicate_id,
                        possible_duplicate_distance_m=action["duplicate_distance_m"],
                    )
                    record_ids.append(created_for_row[action["row"]])
                else:  # update: changed data goes back to verification
                    record_ids.append(action["record_id"])
                    assignments = ", ".join(f"{name} = ?" for name in values)
                    db.execute(
                        f"UPDATE aed_aedreport SET {assignments}, source = ?, status = 'submitted',"
                        " verification_comment = '', verified_by_id = NULL, verified_at = NULL,"
                        " possible_duplicate_of_id = ?, possible_duplicate_distance_m = ?, modified = ?, modified_by_id = ?"
                        " WHERE id = ?",
                        list(values.values())
                        + [source, duplicate_id, action["duplicate_distance_m"], timestamp, user["id"], action["record_id"]],
                    )
        return record_ids

    def _export_devices(self):
        """Public unified dataset: verified records only, columns of the reference data scope."""
        query = parse_qs(urlsplit(self.path).query)
        file_format = (query.get("format") or [""])[0]
        if file_format and file_format not in EXPORT_TYPES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "400 Bad Request", "Dozwolone formaty: csv, json, geojson.")
        rows = [importing.export_record(record) for record in self.store.verified_records()]
        data_date = datetime.date.today().isoformat()
        if not file_format:  # JSON:API for API clients
            body = {
                "data": [{"type": "aed_device", "id": row["id"], "attributes": row} for row in importing.to_json(rows)],
                "meta": {"count": len(rows), "data_date": data_date},
            }
            return HTTPStatus.OK, body
        if file_format == "csv":
            payload = importing.to_csv(rows).encode("utf-8")
        elif file_format == "geojson":
            payload = json.dumps(importing.to_geojson(rows, data_date), ensure_ascii=False, indent=1).encode("utf-8")
        else:
            payload = json.dumps(importing.to_json(rows), ensure_ascii=False, indent=1).encode("utf-8")
        headers = {
            "Content-Type": EXPORT_TYPES[file_format],
            "Content-Disposition": f'attachment; filename="aed-{data_date}.{file_format}"',
            "Access-Control-Allow-Origin": "*",  # open data
        }
        return HTTPStatus.OK, payload, headers

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
        return HTTPStatus.ACCEPTED, {"data": serialize_report(self.store.reports(user, report_id)[0], self._api_url(), user)}


def make_server(host, port, db_target, quiet=False, reset=False):
    handler = type("BoundHandler", (Handler,), {"store": Store(db_target, reset=reset)})
    server = ThreadingHTTPServer((host, port), handler)
    server.quiet = quiet
    return server


def main():
    parser = argparse.ArgumentParser(description="AED prototype — standalone demo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite file path or postgresql:// URL (default: AED_DATABASE_URL)")
    parser.add_argument("--reset", action="store_true", help="recreate the demo tables and data")
    args = parser.parse_args()
    server = make_server(args.host, args.port, args.db, reset=args.reset)
    where = args.db.split("@")[-1] if "://" in args.db else args.db  # never print the password
    label = server.RequestHandlerClass.store.db.label
    print(f"AED demo: http://{args.host}:{args.port}  (database: {label}, {where})  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
