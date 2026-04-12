BEGIN;

CREATE TABLE IF NOT EXISTS service_cache_sigma (
    cache_key VARCHAR(255) PRIMARY KEY,
    payload_json JSONB NULL,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
