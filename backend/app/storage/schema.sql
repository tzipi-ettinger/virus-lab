-- Records DB schema. Bump SCHEMA_VERSION in db.py on any change.
-- One record per commitment number (docs/GUIDELINES-V2-CHANGES.md, D2).
-- All IDs are TEXT so leading zeros survive; STRICT makes SQLite enforce it.
-- Owner: B

CREATE TABLE IF NOT EXISTS page (
    id              TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    page_number     INTEGER NOT NULL,
    rotation        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
) STRICT;

-- Only the page the fields came from, rotated and compressed (D4).
CREATE TABLE IF NOT EXISTS page_image (
    page_id TEXT PRIMARY KEY REFERENCES page(id) ON DELETE CASCADE,
    mime    TEXT NOT NULL,
    sha256  TEXT NOT NULL,
    bytes   BLOB NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS record (
    id                TEXT PRIMARY KEY,
    page_id           TEXT NOT NULL REFERENCES page(id) ON DELETE CASCADE,
    commitment_idx    INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved')),
    needs_review      INTEGER NOT NULL CHECK (needs_review IN (0, 1)),
    version           INTEGER NOT NULL DEFAULT 1,
    -- Effective values (after rules and corrections), kept for search and filter:
    national_id       TEXT,
    commitment_number TEXT,
    central_numbers   TEXT,  -- ' 948062 123456 ' so LIKE '% 948062 %' matches one number
    first_name        TEXT,
    last_name         TEXT,
    sender            TEXT,
    received_date     TEXT,  -- ISO YYYY-MM-DD
    search_text       TEXT NOT NULL DEFAULT '',  -- normalized Hebrew, built in Python
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    approved_at       TEXT,
    UNIQUE (page_id, commitment_idx)
) STRICT;

-- Field shape follows SPEC v0.2 section 7.4: raw never changes, edits go to value + corrected.
CREATE TABLE IF NOT EXISTS record_field (
    record_id    TEXT NOT NULL REFERENCES record(id) ON DELETE CASCADE,
    field        TEXT NOT NULL,
    idx          INTEGER NOT NULL DEFAULT 0,  -- position in a list (central numbers)
    raw          TEXT,
    value        TEXT,
    model_status TEXT NOT NULL CHECK (model_status IN ('found', 'unclear', 'not_found')),
    evidence     TEXT,
    issues_json  TEXT NOT NULL DEFAULT '[]',
    needs_review INTEGER NOT NULL CHECK (needs_review IN (0, 1)),
    corrected    INTEGER NOT NULL DEFAULT 0 CHECK (corrected IN (0, 1)),
    confirmed    INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    updated_at   TEXT,
    PRIMARY KEY (record_id, field, idx)
) STRICT;

CREATE TABLE IF NOT EXISTS record_event (
    id        INTEGER PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES record(id) ON DELETE CASCADE,
    at        TEXT NOT NULL,
    action    TEXT NOT NULL,  -- created / corrected / confirmed / approved
    field     TEXT,
    old       TEXT,
    new       TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS record_status_date ON record (status, received_date);
CREATE INDEX IF NOT EXISTS record_national_id ON record (national_id);
CREATE INDEX IF NOT EXISTS record_commitment ON record (commitment_number);
CREATE INDEX IF NOT EXISTS record_page ON record (page_id);
CREATE INDEX IF NOT EXISTS record_event_record ON record_event (record_id);
