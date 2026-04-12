DELETE FROM service_cache_sigma
WHERE updated_at < NOW() - INTERVAL '7 days';
