"""Small database adapter for the demo server: SQLite (standard library, default) or PostgreSQL (psycopg2).

SQL is written once with "?" placeholders and portable syntax; the adapter converts placeholders for
PostgreSQL, returns rows as dicts with JSON-friendly values (dates as ISO strings, numerics as floats,
UUIDs as strings) and serialises access with a lock (one connection shared by the server threads).

    db = connect("demo.sqlite3")                                  # SQLite file
    db = connect("postgresql://aed:aed@127.0.0.1:5433/aed_demo")  # PostgreSQL
"""

import datetime
import threading
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_FILES = {"sqlite": HERE / "schema.sql", "postgresql": HERE / "schema.postgres.sql"}
TABLES = ("sessions", "user_organizations", "aed_aedreport", "users", "organizations", "aed_meta")


def is_postgres_url(target):
    return str(target).startswith(("postgres://", "postgresql://"))


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime.datetime):
        return value.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


class Database:
    vendor = None

    def __init__(self):
        self.lock = threading.RLock()
        self._in_transaction = False

    # --- to implement per vendor ---
    def _cursor(self):
        raise NotImplementedError

    def _sql(self, sql):
        return sql

    def schema_version(self):
        raise NotImplementedError

    def set_schema_version(self, version):
        raise NotImplementedError

    def table_names(self):
        raise NotImplementedError

    # --- common API ---
    def query(self, sql, params=()):
        with self.lock:
            cursor = self._cursor()
            cursor.execute(self._sql(sql), tuple(params))
            columns = [c[0] for c in cursor.description]
            rows = [{name: _json_value(value) for name, value in zip(columns, row)} for row in cursor.fetchall()]
            if not self._in_transaction:
                self.conn.commit()
            return rows

    def execute(self, sql, params=()):
        with self.lock:
            cursor = self._cursor()
            cursor.execute(self._sql(sql), tuple(params))
            if not self._in_transaction:
                self.conn.commit()
            return cursor

    def insert(self, table, row):
        """INSERT a dict and return the new id."""
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        with self.lock:
            if self.vendor == "postgresql":
                cursor = self.execute(sql + " RETURNING id", list(row.values()))
                return cursor.fetchone()[0]
            return self.execute(sql, list(row.values())).lastrowid

    @contextmanager
    def transaction(self):
        """All statements inside are committed together or rolled back."""
        with self.lock:
            self._in_transaction = True
            try:
                yield self
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                self._in_transaction = False

    def init_schema(self, version, reset=False):
        """Create tables; reset=True or another schema version (demo data only) recreates them."""
        with self.lock:
            if reset or self.schema_version() != version:
                existing = set(self.table_names())
                for table in TABLES:
                    if table in existing:
                        self.execute(f"DROP TABLE {table}" + (" CASCADE" if self.vendor == "postgresql" else ""))
            self._executescript(SCHEMA_FILES[self.vendor].read_text(encoding="utf-8"))
            self.set_schema_version(version)

    def close(self):
        self.conn.close()


class SQLiteDatabase(Database):
    vendor = "sqlite"

    def __init__(self, path):
        import sqlite3

        super().__init__()
        self.label = "SQLite"
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _cursor(self):
        return self.conn.cursor()

    def _executescript(self, script):
        self.conn.executescript(script)

    def schema_version(self):
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def set_schema_version(self, version):
        self.conn.execute(f"PRAGMA user_version = {int(version)}")

    def table_names(self):
        return [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]


class PostgresDatabase(Database):
    vendor = "postgresql"

    def __init__(self, url):
        try:
            import psycopg2
        except ImportError:
            raise SystemExit("PostgreSQL needs psycopg2: pip install psycopg2-binary")
        super().__init__()
        self.label = "PostgreSQL"
        self.conn = psycopg2.connect(url)

    def _cursor(self):
        return self.conn.cursor()

    def _sql(self, sql):
        # Our SQL never contains literal "?" or "%", so a plain replacement is safe here.
        return sql.replace("%", "%%").replace("?", "%s")

    def _executescript(self, script):
        self.execute(script)

    def schema_version(self):
        rows = self.query("SELECT to_regclass('aed_meta') IS NOT NULL AS present")
        if not rows[0]["present"]:
            return 0
        rows = self.query("SELECT schema_version FROM aed_meta")
        return rows[0]["schema_version"] if rows else 0

    def set_schema_version(self, version):
        self.execute("DELETE FROM aed_meta")
        self.execute("INSERT INTO aed_meta (schema_version) VALUES (?)", (int(version),))

    def table_names(self):
        return [r["tablename"] for r in self.query("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")]


def connect(target):
    if is_postgres_url(target):
        return PostgresDatabase(str(target))
    return SQLiteDatabase(target)
