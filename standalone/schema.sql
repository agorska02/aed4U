-- Demo database for the standalone AED prototype.
-- `aed_aedreport` mirrors the portal module's table (hackathon/backend/aed/migrations/0001_initial.py);
-- AED columns follow the reference data scope (hackathon/schema/aed.schema.json).
-- `organizations` and `users` are minimal stand-ins for the portal's Organization and User models.

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    regon VARCHAR(14) NOT NULL DEFAULT '',            -- institution profile (portal: Organization.regon/tel/email)
    phone VARCHAR(9) NOT NULL DEFAULT '',
    email VARCHAR(254) NOT NULL DEFAULT ''
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
    uuid CHAR(36) NOT NULL UNIQUE,                    -- published as `id` in the dataset
    organization_id INTEGER NOT NULL REFERENCES organizations (id) ON DELETE RESTRICT,
    source VARCHAR(10) NOT NULL DEFAULT 'form' CHECK (source IN ('form', 'import', 'api')),
    -- operator
    operator_name VARCHAR(300) NOT NULL,
    operator_regon VARCHAR(14) NOT NULL DEFAULT '',
    -- place
    location_name VARCHAR(300) NOT NULL,
    location_description VARCHAR(300) NOT NULL,
    indoor INTEGER NOT NULL CHECK (indoor IN (0, 1)),
    floor INTEGER,
    -- address
    voivodeship VARCHAR(30) NOT NULL DEFAULT '',
    county VARCHAR(100) NOT NULL DEFAULT '',
    commune VARCHAR(100) NOT NULL,
    city VARCHAR(200) NOT NULL,
    street_type VARCHAR(10) NOT NULL DEFAULT '',
    street VARCHAR(200) NOT NULL DEFAULT '',
    street_number VARCHAR(20) NOT NULL,
    postal_code VARCHAR(6) NOT NULL,
    -- position (WGS84)
    latitude DECIMAL(8, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    -- access
    access VARCHAR(10) NOT NULL CHECK (access IN ('public', 'customers', 'private')),
    opening_hours VARCHAR(255) NOT NULL,
    access_notes VARCHAR(500) NOT NULL DEFAULT '',
    -- device
    device_status VARCHAR(15) NOT NULL CHECK (device_status IN ('operational', 'out_of_service', 'removed')),
    pediatric VARCHAR(7) NOT NULL DEFAULT '' CHECK (pediatric IN ('', 'yes', 'no', 'unknown')),
    manufacturer VARCHAR(20) NOT NULL,                -- code from schema/dictionaries/manufacturers.csv
    manufacturer_other VARCHAR(100) NOT NULL DEFAULT '', -- name when manufacturer = 'other'
    model VARCHAR(100) NOT NULL DEFAULT '',
    serial_number VARCHAR(50) NOT NULL,               -- administrator only, never published
    -- manufacturer + normalised serial number: one device cannot be reported in two places
    device_key VARCHAR(160) NOT NULL UNIQUE,
    last_inspection_date TEXT,                        -- ISO 8601 dates (yyyy-mm-dd)
    electrodes_expiry_date TEXT,
    battery_expiry_date TEXT,
    -- contact: operator_* and contact_* always come from the institution profile
    contact_phone VARCHAR(9) NOT NULL DEFAULT '',
    contact_email VARCHAR(254) NOT NULL DEFAULT '',
    internal_contact_phone VARCHAR(9) NOT NULL DEFAULT '',  -- administrator only, never published
    -- currency
    data_date TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    -- duplicate detection across sources (set on create/import, decided by the administrator)
    possible_duplicate_of_id INTEGER REFERENCES aed_aedreport (id) ON DELETE SET NULL,
    possible_duplicate_distance_m INTEGER,
    -- verification workflow
    status VARCHAR(10) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'verified', 'rejected')),
    verification_comment TEXT NOT NULL DEFAULT '',
    verified_by_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    verified_at TEXT,                                 -- ISO 8601 datetime (UTC)
    created TEXT NOT NULL,
    created_by_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    modified TEXT NOT NULL,
    modified_by_id INTEGER REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS aed_aedreport_organization_idx ON aed_aedreport (organization_id);
CREATE INDEX IF NOT EXISTS aed_aedreport_status_idx ON aed_aedreport (status);
