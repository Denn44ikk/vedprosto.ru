BEGIN;

CREATE INDEX IF NOT EXISTS ix_tg_messages_chat_id ON tg_messages (chat_id);
CREATE INDEX IF NOT EXISTS ix_tg_messages_topic_id ON tg_messages (topic_id);
CREATE INDEX IF NOT EXISTS ix_tg_analysis_runs_chat_id ON tg_analysis_runs (chat_id);
CREATE INDEX IF NOT EXISTS ix_tg_analysis_runs_topic_id ON tg_analysis_runs (topic_id);
CREATE INDEX IF NOT EXISTS ix_tg_analysis_runs_source_message_id ON tg_analysis_runs (source_message_id);
CREATE INDEX IF NOT EXISTS ix_tg_bot_replies_chat_id ON tg_bot_replies (chat_id);
CREATE INDEX IF NOT EXISTS ix_tg_bot_replies_source_message_id ON tg_bot_replies (source_message_id);
CREATE INDEX IF NOT EXISTS ix_tg_bot_replies_bot_message_id ON tg_bot_replies (bot_message_id);
CREATE INDEX IF NOT EXISTS ix_tg_corrections_chat_id ON tg_corrections (chat_id);
CREATE INDEX IF NOT EXISTS ix_tg_corrections_request_topic_id ON tg_corrections (request_topic_id);
CREATE INDEX IF NOT EXISTS ix_tg_corrections_comment_topic_id ON tg_corrections (comment_topic_id);
CREATE INDEX IF NOT EXISTS ix_tg_corrections_ref_text ON tg_corrections (ref_text);

COMMIT;
