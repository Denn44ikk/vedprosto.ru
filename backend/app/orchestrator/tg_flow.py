from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from ..integrations.its import ITSService
from ..integrations.telegram import TelegramBotClient
from ..reporting.telegram.service import TelegramReplyPayload, build_tg_analysis_reply
from ..storage.tg.db import TgAnalysisRepo, TgDbConnection, TgMessagesRepo, TgRepliesRepo
from .shared_flow import SHARED_FLOW_NAME, SharedFlowInput, describe_shared_flow, run_shared_flow


TG_FLOW_NAME = "tg_flow"


@dataclass(frozen=True)
class QueuedTgRun:
    run_id: int
    chat_id: int
    topic_id: int | None
    message_id: int
    stored_message_pk: int
    deduplicated: bool = False


@dataclass(frozen=True)
class ProcessedTgRun:
    run_id: int
    reply_message_id: int | None
    tnved: str | None
    tnved_status: str


def describe_tg_flow() -> dict[str, object]:
    return {
        "name": TG_FLOW_NAME,
        "base_flow": SHARED_FLOW_NAME,
        "stages": describe_shared_flow(),
        "channel_specific": ("routing", "replies", "retry_queue"),
    }


async def queue_tg_analysis_message(
    db_connection: TgDbConnection,
    *,
    chat_id: int,
    message_id: int,
    topic_id: int | None,
    sender_id: int | None,
    text: str | None,
    chat_title: str | None,
    topic_name: str | None,
    message_date: datetime | None,
) -> QueuedTgRun:
    async with db_connection.session() as session:
        messages_repo = TgMessagesRepo(session)
        analysis_repo = TgAnalysisRepo(session)

        await messages_repo.upsert_chat(chat_id=chat_id, chat_title=chat_title)
        if topic_id is not None:
            await messages_repo.upsert_topic(chat_id=chat_id, topic_id=topic_id, topic_name=topic_name)

        stored_message = await messages_repo.insert_message(
            chat_id=chat_id,
            message_id=message_id,
            topic_id=topic_id,
            sender_id=sender_id,
            text=text,
            message_date=message_date,
        )

        existing_run = await analysis_repo.get_latest_run_for_message(
            chat_id=chat_id,
            source_message_id=message_id,
        )
        if existing_run is not None and existing_run.status in {"queued", "running", "done"}:
            await session.commit()
            return QueuedTgRun(
                run_id=existing_run.id,
                chat_id=chat_id,
                topic_id=topic_id,
                message_id=message_id,
                stored_message_pk=stored_message.id,
                deduplicated=True,
            )

        run = await analysis_repo.create_run(
            chat_id=chat_id,
            source_message_id=message_id,
            topic_id=topic_id,
            flow_name=TG_FLOW_NAME,
            status="queued",
            stage_name="queued",
        )
        await session.commit()
        return QueuedTgRun(
            run_id=run.id,
            chat_id=chat_id,
            topic_id=topic_id,
            message_id=message_id,
            stored_message_pk=stored_message.id,
            deduplicated=False,
        )


async def process_tg_analysis_run(
    db_connection: TgDbConnection,
    *,
    run_id: int,
    bot_client: TelegramBotClient,
    its_service: ITSService | None = None,
    logger: logging.Logger | None = None,
) -> ProcessedTgRun:
    flow_logger = logger or logging.getLogger("agent_ui.orchestrator.tg_flow")
    async with db_connection.session() as session:
        analysis_repo = TgAnalysisRepo(session)
        messages_repo = TgMessagesRepo(session)
        run = await analysis_repo.get_run(run_id=run_id)
        if run is None:
            raise RuntimeError(f"TG run not found: {run_id}")
        message = await messages_repo.get_message(chat_id=run.chat_id, message_id=run.source_message_id)
        if message is None:
            raise RuntimeError(f"TG source message not found chat_id={run.chat_id} message_id={run.source_message_id}")
        await analysis_repo.update_run_status(run_id=run_id, status="running", stage_name="prepare_input")
        await session.commit()

    shared_result = run_shared_flow(SharedFlowInput(source_text=message.text))
    its_result = None
    if shared_result.primary_code and its_service is not None:
        async with db_connection.session() as session:
            analysis_repo = TgAnalysisRepo(session)
            await analysis_repo.update_run_status(run_id=run_id, status="running", stage_name="its")
            await session.commit()
        its_result = await its_service.get_its(shared_result.primary_code)

    reply_payload: TelegramReplyPayload = build_tg_analysis_reply(
        shared_result=shared_result,
        its_result=its_result,
    )
    reply_message = await bot_client.send_message(
        chat_id=run.chat_id,
        message_thread_id=run.topic_id,
        reply_to_message_id=run.source_message_id,
        text=reply_payload.text,
    )

    async with db_connection.session() as session:
        analysis_repo = TgAnalysisRepo(session)
        replies_repo = TgRepliesRepo(session)
        await analysis_repo.upsert_result(
            run_id=run_id,
            tnved=reply_payload.tnved,
            tnved_status=reply_payload.tnved_status,
            report_short_text=reply_payload.report_short_text,
            report_full_text=reply_payload.report_full_text,
            payload_json=reply_payload.payload_json,
        )
        await replies_repo.create_reply_link(
            chat_id=run.chat_id,
            source_message_id=run.source_message_id,
            bot_message_id=int(getattr(reply_message, "message_id", 0) or 0),
            source_topic_id=run.topic_id,
            bot_topic_id=getattr(reply_message, "message_thread_id", None),
            old_tnved=reply_payload.tnved,
            source_message_ids=[run.source_message_id],
            status="sent",
        )
        await analysis_repo.update_run_status(run_id=run_id, status="done", stage_name="build_result")
        await session.commit()

    flow_logger.info(
        "TG run processed run_id=%s chat_id=%s source_message_id=%s tnved=%s status=%s",
        run_id,
        run.chat_id,
        run.source_message_id,
        reply_payload.tnved,
        reply_payload.tnved_status,
    )
    return ProcessedTgRun(
        run_id=run_id,
        reply_message_id=int(getattr(reply_message, "message_id", 0) or 0) or None,
        tnved=reply_payload.tnved,
        tnved_status=reply_payload.tnved_status,
    )


async def fail_tg_analysis_run(
    db_connection: TgDbConnection,
    *,
    run_id: int,
    error_text: str,
) -> None:
    async with db_connection.session() as session:
        analysis_repo = TgAnalysisRepo(session)
        await analysis_repo.update_run_status(
            run_id=run_id,
            status="failed",
            stage_name="pipeline_error",
            error_text=error_text,
        )
        await session.commit()


__all__ = [
    "ProcessedTgRun",
    "QueuedTgRun",
    "TG_FLOW_NAME",
    "describe_tg_flow",
    "fail_tg_analysis_run",
    "process_tg_analysis_run",
    "queue_tg_analysis_message",
]
