"""Demo accounts and sample reports for the standalone AED prototype.

Sample reports are the records from schema/aed-example.csv, validated with the shared validator.
Usage: python standalone/seed.py [--db PATH_OR_POSTGRES_URL] [--reset]
"""

import argparse
import csv
import datetime
import hashlib
import os
import secrets
import sys
import uuid
from pathlib import Path

from db import connect

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# SQLite file by default; AED_DATABASE_URL=postgresql://… (or --db) switches to PostgreSQL.
DEFAULT_DB = os.environ.get("AED_DATABASE_URL") or str(HERE / "aed_demo.sqlite3")
EXAMPLES = ROOT / "schema" / "aed-example.csv"
SCHEMA_VERSION = 7  # an older demo database is recreated automatically

sys.path.insert(0, str(ROOT / "backend"))
from aed import importing  # noqa: E402
from aed.validation import (  # noqa: E402
    institution_field_names,
    record_field_names,
    to_json_value,
    validate_record,
)

# server.py imports the shared modules through this file (it puts backend/ on sys.path first).
__all__ = [
    "AED_COLUMNS",
    "DEFAULT_DB",
    "connect",
    "db_values",
    "importing",
    "institution_values",
    "init_db",
    "insert_report",
    "now_iso",
    "seed",
    "validate_record",
    "verify_password",
]

PBKDF2_ITERATIONS = 100_000
NULLABLE_COLUMNS = ("floor", "last_inspection_date", "electrodes_expiry_date", "battery_expiry_date")
AED_COLUMNS = record_field_names()  # stored AED columns: provider + institution + internal fields

# Test data only — passwords are shown on the demo login page.
ORGANIZATIONS = [
    # title, REGON, public phone, public e-mail (institution profile; fictional)
    ("Urząd Miasta Demo (instytucja A)", "123456785", "120000000", "sekretariat@urzad-demo.example"),
    ("Szpital Demo (instytucja B)", "987654325", "580000000", "kontakt@szpital-demo.example"),
]
USERS = [
    # email, fullname, password, is_staff, is_superuser, organization indexes
    ("dostawca@demo.local", "Dostawca A", "Demo123!", True, False, [0]),
    ("dostawca2@demo.local", "Dostawca B", "Demo123!", True, False, [1]),
    ("admin@demo.local", "Administrator portalu", "Admin123!", True, True, []),
]
# For each row of aed-example.csv: organization index, verification status, verification comment.
REPORTS = [
    (0, "verified", ""),
    (0, "submitted", ""),
    (1, "verified", ""),
    (1, "rejected", "Po wymianie elektrod uzupełnij nowy termin ważności."),
    (0, "submitted", ""),
]


def hash_password(password: str, salt: str = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _algorithm, iterations, salt, digest = encoded.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return secrets.compare_digest(candidate, digest)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def institution_values(organization):
    """x-from-institution fields of a report, taken from the institution profile (a row of `organizations`)."""
    values = {
        "operator_name": organization["title"],
        "operator_regon": organization["regon"],
        "contact_phone": organization["phone"],
        "contact_email": organization["email"],
    }
    assert set(values) == set(institution_field_names()), "schema and institution profile out of sync"
    return values


def init_db(db, reset=False) -> None:
    db.init_schema(SCHEMA_VERSION, reset=reset)


def db_values(cleaned):
    """Cleaned validator output -> column values (same conventions as the Django model: '' for empty text)."""
    values = {}
    for name in AED_COLUMNS:
        value = to_json_value(cleaned.get(name))
        if value is None and name not in NULLABLE_COLUMNS:
            value = ""
        values[name] = value
    values["device_key"] = importing.device_key(cleaned)  # unique: one device cannot be in two places
    return values


def insert_report(
    db,
    values,
    *,
    organization_id,
    user_id,
    status,
    source,
    report_uuid=None,
    verified_by_id=None,
    verified_at=None,
    verification_comment="",
    timestamp=None,
    possible_duplicate_of_id=None,
    possible_duplicate_distance_m=None,
):
    timestamp = timestamp or now_iso()
    row = dict(values)
    row.update(
        uuid=report_uuid or str(uuid.uuid4()),
        organization_id=organization_id,
        source=source,
        status=status,
        verification_comment=verification_comment,
        verified_by_id=verified_by_id,
        verified_at=verified_at,
        created=timestamp,
        created_by_id=user_id,
        modified=timestamp,
        modified_by_id=verified_by_id or user_id,
        possible_duplicate_of_id=possible_duplicate_of_id,
        possible_duplicate_distance_m=possible_duplicate_distance_m,
    )
    return db.insert("aed_aedreport", row)


def example_records():
    with open(str(EXAMPLES), encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def seed(db) -> None:
    """Insert demo data if the database is empty."""
    if db.query("SELECT COUNT(*) AS n FROM users")[0]["n"]:
        return
    with db.transaction():
        organizations = [dict(zip(("title", "regon", "phone", "email"), org)) for org in ORGANIZATIONS]
        org_ids = [db.insert("organizations", org) for org in organizations]
        user_ids = {}
        for email, fullname, password, is_staff, is_superuser, orgs in USERS:
            user_ids[email] = db.insert(
                "users",
                {
                    "email": email,
                    "fullname": fullname,
                    "password_hash": hash_password(password),
                    "is_staff": is_staff,
                    "is_superuser": is_superuser,
                },
            )
            for index in orgs:
                db.execute(
                    "INSERT INTO user_organizations (user_id, organization_id) VALUES (?, ?)", (user_ids[email], org_ids[index])
                )
        admin_id = user_ids["admin@demo.local"]
        providers = {0: user_ids["dostawca@demo.local"], 1: user_ids["dostawca2@demo.local"]}
        for index, (record, (org_index, status, comment)) in enumerate(zip(example_records(), REPORTS), 1):
            # serial numbers are internal (not in the published example file) — demo values
            cleaned, errors = validate_record(dict(record, serial_number="DEMO-{0:04d}".format(index)))
            if errors:
                raise ValueError(f"Invalid example record {record['id']}: {errors}")
            cleaned.update(institution_values(organizations[org_index]))
            verified = status in ("verified", "rejected")
            insert_report(
                db,
                db_values(cleaned),
                organization_id=org_ids[org_index],
                user_id=providers[org_index],
                status=status,
                source=record["source"],
                report_uuid=record["id"],
                verified_by_id=admin_id if verified else None,
                verified_at=record["verified_at"] if verified else None,
                verification_comment=comment,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite file path or postgresql:// URL")
    parser.add_argument("--reset", action="store_true", help="drop the demo tables and create them from scratch")
    args = parser.parse_args()
    db = connect(args.db)
    init_db(db, reset=args.reset)
    seed(db)
    db.close()
    print(f"Demo database ready ({db.label})")


if __name__ == "__main__":
    main()
