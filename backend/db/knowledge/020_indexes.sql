BEGIN;

CREATE INDEX IF NOT EXISTS idx_tnved_catalog_updated_at ON tnved_catalog (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tnved_catalog_meta_updated_at ON tnved_catalog_meta (updated_at DESC);

COMMIT;
