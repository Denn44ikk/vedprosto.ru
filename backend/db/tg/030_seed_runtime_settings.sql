INSERT INTO tg_runtime_settings (
    id,
    target_chat_id,
    allowed_topic_ids_json,
    request_comment_topic_map_json,
    price_topic_id,
    settings_topic_id,
    supplier_topic_map_json,
    settings_admin_ids_json,
    its_enabled,
    its_config_path,
    its_session_path,
    its_bot_username,
    its_timeout_sec,
    its_delay_sec,
    its_max_retries
)
VALUES (
    1,
    0,
    '[]'::jsonb,
    '{}'::jsonb,
    NULL,
    NULL,
    '{}'::jsonb,
    '[]'::jsonb,
    FALSE,
    NULL,
    NULL,
    NULL,
    30,
    3.0,
    3
)
ON CONFLICT (id) DO NOTHING;
