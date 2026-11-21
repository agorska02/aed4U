-- Demo database for the standalone AED prototype.
-- `aed_aedreport` mirrors the portal module's table (hackathon/backend/aed/migrations/0001_initial.py);
-- `organizations` and `users` are minimal stand-ins for the portal's Organization and User models.

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    fullname TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    is_staff INTEGER NOT NULL DEFAULT 0,      -- editor (data provider)
    is_superuser INTEGER NOT NULL DEFAULT 0   -- portal administrator
);

CREATE TABLE IF NOT EXISTS user_organizations (
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, organization_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aed_aedreport (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations (id) ON DELETE RESTRICT,
    location_name VARCHAR(300) NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    data_date TEXT NOT NULL,                          -- ISO 8601 date (yyyy-mm-dd)
    status VARCHAR(10) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'verified', 'rejected')),
    verification_comment TEXT NOT NULL DEFAULT '',
    verified_by_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    verified_at TEXT,                                 -- ISO 8601 datetime
    created TEXT NOT NULL,
    created_by_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    modified TEXT NOT NULL,
    modified_by_id INTEGER REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS aed_aedreport_organization_idx ON aed_aedreport (organization_id);
CREATE INDEX IF NOT EXISTS aed_aedreport_status_idx ON aed_aedreport (status);
