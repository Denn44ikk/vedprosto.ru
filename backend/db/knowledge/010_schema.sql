BEGIN;

CREATE TABLE IF NOT EXISTS tnved_catalog (
    tnved_code VARCHAR(32) PRIMARY KEY,
    description TEXT NOT NULL,
    duty_rate TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tnved_catalog_meta (
    id INTEGER PRIMARY KEY,
    source_url TEXT NULL,
    workbook_path TEXT NULL,
    sheet_name TEXT NULL,
    active_rows INTEGER NOT NULL DEFAULT 0,
    scanned_rows INTEGER NOT NULL DEFAULT 0,
    imported_rows INTEGER NOT NULL DEFAULT 0,
    notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_tnved_catalog_meta_singleton CHECK (id = 1)
);

COMMIT;
