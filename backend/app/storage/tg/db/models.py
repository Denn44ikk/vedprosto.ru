from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TgChat(Base):
    __tablename__ = "tg_chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TgTopic(Base):
    __tablename__ = "tg_topics"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    topic_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    topic_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TgMessage(Base):
    __tablename__ = "tg_messages"
    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_tg_messages_chat_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_mime: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TgAnalysisRun(Base):
    __tablename__ = "tg_analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    flow_name: Mapped[str] = mapped_column(String(100), nullable=False, default="tg_flow")
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="queued")
    stage_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    case_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TgAnalysisResult(Base):
    __tablename__ = "tg_analysis_results"

    run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tg_analysis_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tnved: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tnved_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    report_short_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TgBotReply(Base):
    __tablename__ = "tg_bot_replies"
    __table_args__ = (UniqueConstraint("chat_id", "bot_message_id", name="uq_tg_bot_replies_chat_bot_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    bot_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bot_topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    old_tnved: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correction_prompt_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_message_ids_json: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TgCorrection(Base):
    __tablename__ = "tg_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    request_topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    comment_topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bot_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    operator_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_tnved: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_tnved: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_text: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    forward_source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forward_bot_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forward_note_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TgRuntimeSetting(Base):
    __tablename__ = "tg_runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    target_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    allowed_topic_ids_json: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    request_comment_topic_map_json: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    price_topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    settings_topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    supplier_topic_map_json: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    settings_admin_ids_json: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    its_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    its_config_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    its_session_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    its_bot_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    its_timeout_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    its_delay_sec: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    its_max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ServiceCacheIts(Base):
    __tablename__ = "service_cache_its"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    its_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    its_bracket_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reply_variant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_code_match_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reply_code_candidates_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ServiceCacheSigma(Base):
    __tablename__ = "service_cache_sigma"

    cache_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = [
    "Base",
    "ServiceCacheIts",
    "ServiceCacheSigma",
    "TgRuntimeSetting",
    "TgAnalysisResult",
    "TgAnalysisRun",
    "TgBotReply",
    "TgChat",
    "TgCorrection",
    "TgMessage",
    "TgTopic",
]
