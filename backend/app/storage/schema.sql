-- Records DB schema (PostgreSQL). Bump SCHEMA_VERSION in db.py on any change.
-- One record per commitment number (docs/GUIDELINES-V2-CHANGES.md, D2).
-- Every ID is TEXT, so leading zeros survive.
-- Owner: B

CREATE TABLE schema_meta (
    version INTEGER NOT NULL
);

-- A form's pages (A1 in #15): its first page has no first_page_id, and each
-- continuation page points at the first one. Deleting the first page deletes them.
CREATE TABLE page (
    id              TEXT PRIMARY KEY,
    file_id         TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    page_number     INTEGER NOT NULL CHECK (page_number >= 1),
    rotation        INTEGER NOT NULL DEFAULT 0,  -- for information: the image is already upright
    first_page_id   TEXT REFERENCES page(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (file_id, page_number)
);

-- The page as saved for the preview (D4): upright and compressed.
CREATE TABLE page_image (
    page_id TEXT PRIMARY KEY REFERENCES page(id) ON DELETE CASCADE,
    mime    TEXT NOT NULL,
    sha256  TEXT NOT NULL,
    bytes   BYTEA NOT NULL
);

CREATE TABLE record (
    id                TEXT PRIMARY KEY,
    page_id           TEXT NOT NULL REFERENCES page(id) ON DELETE CASCADE,  -- the form's first page
    commitment_idx    INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved')),
    needs_review      BOOLEAN NOT NULL,
    version           INTEGER NOT NULL DEFAULT 1,
    form_type         TEXT NOT NULL,
    -- The record as the contract shows it (schemas/api.py, SPEC 7.4): every field
    -- with raw, value, issues and flags. raw never changes; edits go to value.
    fields            JSONB NOT NULL,
    central_numbers   JSONB NOT NULL,
    issues            JSONB NOT NULL,
    -- Effective values, copied from the JSONB above, for search, filters and the list:
    national_id       TEXT,
    commitment_number TEXT,
    central_values    TEXT[] NOT NULL DEFAULT '{}',
    first_name        TEXT,
    last_name         TEXT,
    sender            TEXT,
    received_date     DATE,  -- NULL while the date is missing or invalid
    search_text       TEXT NOT NULL DEFAULT '',  -- normalized Hebrew, built in Python
    created_at        TIMESTAMPTZ NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL,
    approved_at       TIMESTAMPTZ,
    UNIQUE (page_id, commitment_idx)
);

-- What was done to which field, and when. Never the values themselves (D13).
-- No user: the site has no sign-in (removed 21.10).
CREATE TABLE record_event (
    id        BIGSERIAL PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES record(id) ON DELETE CASCADE,
    at        TIMESTAMPTZ NOT NULL,
    action    TEXT NOT NULL CHECK (action IN ('created', 'corrected', 'confirmed', 'approved')),
    field     TEXT
);

-- When and how many were exported. No filters and no content (D19).
CREATE TABLE export_log (
    id           BIGSERIAL PRIMARY KEY,
    at           TIMESTAMPTZ NOT NULL,
    format       TEXT NOT NULL CHECK (format IN ('csv', 'json')),
    record_count INTEGER NOT NULL
);

CREATE INDEX record_status_date ON record (status, received_date);
CREATE INDEX record_national_id ON record (national_id);
CREATE INDEX record_commitment ON record (commitment_number);
CREATE INDEX record_page ON record (page_id);
CREATE INDEX page_first_page ON page (first_page_id);
CREATE INDEX record_event_record ON record_event (record_id);
