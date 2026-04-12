BEGIN;

CREATE TABLE IF NOT EXISTS tg_chats (
    chat_id BIGINT PRIMARY KEY,
    chat_title TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tg_topics (
    chat_id BIGINT NOT NULL,
    topic_id BIGINT NOT NULL,
    topic_name TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chat_id, topic_id)
);

CREATE TABLE IF NOT EXISTS tg_messages (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    topic_id BIGINT NULL,
    message_id BIGINT NOT NULL,
    sender_id BIGINT NULL,
    text TEXT NULL,
    image_base64 TEXT NULL,
    image_mime VARCHAR(255) NULL,
    message_date TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tg_messages_chat_message UNIQUE (chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS tg_analysis_runs (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    topic_id BIGINT NULL,
    source_message_id BIGINT NOT NULL,
    flow_name VARCHAR(100) NOT NULL DEFAULT 'tg_flow',
    status VARCHAR(100) NOT NULL DEFAULT 'queued',
    stage_name VARCHAR(100) NULL,
    case_key VARCHAR(255) NULL,
    error_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS tg_analysis_results (
    run_id BIGINT PRIMARY KEY REFERENCES tg_analysis_runs(id) ON DELETE CASCADE,
    tnved VARCHAR(32) NULL,
    tnved_status VARCHAR(100) NULL,
    report_short_text TEXT NULL,
    report_full_text TEXT NULL,
    payload_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tg_bot_replies (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    bot_message_id BIGINT NOT NULL,
    source_topic_id BIGINT NULL,
    bot_topic_id BIGINT NULL,
    old_tnved VARCHAR(32) NULL,
    correction_prompt_message_id BIGINT NULL,
    source_message_ids_json JSONB NULL,
    status VARCHAR(100) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tg_bot_replies_chat_bot_message UNIQUE (chat_id, bot_message_id)
);

CREATE TABLE IF NOT EXISTS tg_corrections (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    request_topic_id BIGINT NULL,
    comment_topic_id BIGINT NULL,
    source_message_id BIGINT NOT NULL,
    bot_message_id BIGINT NOT NULL,
    operator_user_id BIGINT NULL,
    operator_name TEXT NULL,
    old_tnved VARCHAR(32) NULL,
    new_tnved VARCHAR(32) NULL,
    reason_text TEXT NULL,
    rule_text TEXT NULL,
    raw_text TEXT NULL,
    ref_text VARCHAR(255) NULL,
    forward_source_message_id BIGINT NULL,
    forward_bot_message_id BIGINT NULL,
    forward_note_message_id BIGINT NULL,
    status VARCHAR(100) NULL,
    error_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tg_runtime_settings (
    id INTEGER PRIMARY KEY,
    target_chat_id BIGINT NOT NULL DEFAULT 0,
    allowed_topic_ids_json JSONB NULL,
    request_comment_topic_map_json JSONB NULL,
    price_topic_id BIGINT NULL,
    settings_topic_id BIGINT NULL,
    supplier_topic_map_json JSONB NULL,
    settings_admin_ids_json JSONB NULL,
    its_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    its_config_path TEXT NULL,
    its_session_path TEXT NULL,
    its_bot_username VARCHAR(255) NULL,
    its_timeout_sec INTEGER NOT NULL DEFAULT 30,
    its_delay_sec DOUBLE PRECISION NOT NULL DEFAULT 3.0,
    its_max_retries INTEGER NOT NULL DEFAULT 3,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_tg_runtime_settings_singleton CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS service_cache_its (
    code VARCHAR(32) PRIMARY KEY,
    status VARCHAR(100) NULL,
    its_value DOUBLE PRECISION NULL,
    its_bracket_value DOUBLE PRECISION NULL,
    reply_variant INTEGER NULL,
    date_text VARCHAR(100) NULL,
    error_text TEXT NULL,
    reply_code_match_status VARCHAR(100) NULL,
    reply_code_candidates_json JSONB NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS service_cache_sigma (
    cache_key VARCHAR(255) PRIMARY KEY,
    payload_json JSONB NULL,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
