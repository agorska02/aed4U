-- Demo database for the standalone AED prototype — PostgreSQL variant (native types).
-- `aed_aedreport` mirrors the portal module's table (hackathon/backend/aed/migrations/0001_initial.py);
-- AED columns follow the reference data scope (hackathon/schema/aed.schema.json).
-- `organizations` and `users` are minimal stand-ins for the portal's Organization and User models.
-- SQLite variant: schema.sql (keep both in sync).

CREATE TABLE IF NOT EXISTS aed_meta (
    schema_version integer NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
    id serial PRIMARY KEY,
    title text NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id serial PRIMARY KEY,
    email text NOT NULL UNIQUE,
    fullname text NOT NULL DEFAULT '',
    password_hash text NOT NULL,
    is_staff boolean NOT NULL DEFAULT false,      -- editor (data provider)
    is_superuser boolean NOT NULL DEFAULT false   -- portal administrator
);

CREATE TABLE IF NOT EXISTS user_organizations (
    user_id integer NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    organization_id integer NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, organization_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    token text PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS aed_aedreport (
    id serial PRIMARY KEY,
    uuid uuid NOT NULL UNIQUE,                        -- published as `id` in the dataset
    organization_id integer NOT NULL REFERENCES organizations (id) ON DELETE RESTRICT,
    source varchar(10) NOT NULL DEFAULT 'form' CHECK (source IN ('form', 'import', 'api')),
    source_id varchar(100) NOT NULL DEFAULT '',
    -- operator
    operator_name varchar(300) NOT NULL,
    operator_regon varchar(14) NOT NULL DEFAULT '',
    -- place
    location_name varchar(300) NOT NULL,
    location_description varchar(300) NOT NULL,
    indoor boolean NOT NULL,
    floor smallint,
    -- address
    voivodeship varchar(30) NOT NULL DEFAULT '',
    county varchar(100) NOT NULL DEFAULT '',
    commune varchar(100) NOT NULL,
    teryt_terc varchar(7) NOT NULL DEFAULT '',
    city varchar(200) NOT NULL,
    teryt_simc varchar(7) NOT NULL DEFAULT '',
    street_type varchar(10) NOT NULL DEFAULT '',
    street varchar(200) NOT NULL DEFAULT '',
    street_number varchar(20) NOT NULL,
    postal_code varchar(6) NOT NULL,
    -- position (WGS84)
    latitude numeric(8, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude numeric(9, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    -- access
    access varchar(10) NOT NULL CHECK (access IN ('public', 'customers', 'private')),
    opening_hours varchar(255) NOT NULL,
    access_notes varchar(500) NOT NULL DEFAULT '',
    -- device
    device_status varchar(15) NOT NULL CHECK (device_status IN ('operational', 'out_of_service', 'removed')),
    pediatric varchar(7) NOT NULL DEFAULT '' CHECK (pediatric IN ('', 'yes', 'no', 'unknown')),
    manufacturer varchar(100) NOT NULL DEFAULT '',
    model varchar(100) NOT NULL DEFAULT '',
    last_inspection_date date,
    electrodes_expiry_date date,
    battery_expiry_date date,
    -- contact (institutional only)
    contact_phone varchar(9) NOT NULL DEFAULT '',
    contact_email varchar(254) NOT NULL DEFAULT '',
    -- currency
    data_date date NOT NULL,
    notes text NOT NULL DEFAULT '',
    -- duplicate detection across sources (set on create/import, decided by the administrator)
    possible_duplicate_of_id integer REFERENCES aed_aedreport (id) ON DELETE SET NULL,
    possible_duplicate_distance_m integer CHECK (possible_duplicate_distance_m >= 0),
    -- verification workflow
    status varchar(10) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'verified', 'rejected')),
    verification_comment text NOT NULL DEFAULT '',
    verified_by_id integer REFERENCES users (id) ON DELETE SET NULL,
    verified_at timestamptz,
    created timestamptz NOT NULL,
    created_by_id integer REFERENCES users (id) ON DELETE SET NULL,
    modified timestamptz NOT NULL,
    modified_by_id integer REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS aed_aedreport_organization_idx ON aed_aedreport (organization_id);
CREATE INDEX IF NOT EXISTS aed_aedreport_status_idx ON aed_aedreport (status);
CREATE INDEX IF NOT EXISTS aed_aedreport_source_id_idx ON aed_aedreport (organization_id, source_id);
