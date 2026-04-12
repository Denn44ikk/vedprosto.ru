BEGIN;

CREATE INDEX IF NOT EXISTS ix_service_cache_sigma_updated_at
    ON service_cache_sigma (updated_at);

COMMIT;
