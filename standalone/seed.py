"""Demo accounts and sample reports for the standalone AED prototype.

Usage: python standalone/seed.py [--db PATH] [--reset]
"""

import argparse
import datetime
import hashlib
import secrets
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DB = HERE / "aed_demo.sqlite3"
SCHEMA = HERE / "schema.sql"

PBKDF2_ITERATIONS = 100_000

# Test data only — passwords are shown on the demo login page.
ORGANIZATIONS = ["Urząd Miasta Demo (instytucja A)", "Szpital Demo (instytucja B)"]
USERS = [
    # email, fullname, password, is_staff, is_superuser, organization indexes
    ("dostawca@demo.local", "Dostawca A", "Demo123!", True, False, [0]),
    ("dostawca2@demo.local", "Dostawca B", "Demo123!", True, False, [1]),
    ("admin@demo.local", "Administrator portalu", "Admin123!", True, True, []),
]
REPORTS = [
    # organization index, location_name, notes, status, verification_comment
    (0, "Dworzec Centralny – hala główna", "Przy kasach biletowych", "submitted", ""),
    (0, "Urząd Miasta – parter", "", "verified", ""),
    (1, "Szpital Demo – izba przyjęć", "Wejście od ul. Szpitalnej", "rejected", "Uzupełnij godziny dostępności."),
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
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))


def seed(conn: sqlite3.Connection) -> None:
    """Insert demo data if the database is empty."""
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    org_ids = [conn.execute("INSERT INTO organizations (title) VALUES (?)", (title,)).lastrowid for title in ORGANIZATIONS]
    user_ids = {}
    for email, fullname, password, is_staff, is_superuser, orgs in USERS:
        user_id = conn.execute(
            "INSERT INTO users (email, fullname, password_hash, is_staff, is_superuser) VALUES (?, ?, ?, ?, ?)",
            (email, fullname, hash_password(password), int(is_staff), int(is_superuser)),
        ).lastrowid
        user_ids[email] = user_id
        for index in orgs:
            conn.execute("INSERT INTO user_organizations (user_id, organization_id) VALUES (?, ?)", (user_id, org_ids[index]))
    admin_id = user_ids["admin@demo.local"]
    providers = {0: user_ids["dostawca@demo.local"], 1: user_ids["dostawca2@demo.local"]}
    today = datetime.date.today().isoformat()
    for org_index, location_name, notes, status, comment in REPORTS:
        verified = status in ("verified", "rejected")
        timestamp = now_iso()
        conn.execute(
            "INSERT INTO aed_aedreport (organization_id, location_name, notes, data_date, status, verification_comment,"
            " verified_by_id, verified_at, created, created_by_id, modified, modified_by_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                org_ids[org_index],
                location_name,
                notes,
                today,
                status,
                comment,
                admin_id if verified else None,
                timestamp if verified else None,
                timestamp,
                providers[org_index],
                timestamp,
                providers[org_index],
            ),
        )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--reset", action="store_true", help="delete the database and create it from scratch")
    args = parser.parse_args()
    if args.reset and args.db.exists():
        args.db.unlink()
    conn = sqlite3.connect(str(args.db))
    init_db(conn)
    seed(conn)
    conn.close()
    print(f"Demo database ready: {args.db}")


if __name__ == "__main__":
    main()
