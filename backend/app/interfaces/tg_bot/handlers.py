from __future__ import annotations

import asyncio
import logging
from typing import Any

from ...integrations.telegram import TopicRouter
from ...orchestrator.tg_flow import fail_tg_analysis_run, process_tg_analysis_run, queue_tg_analysis_message
from .bot import TgBotRuntime
from .routing import extract_message_text
from .settings import TgBotSettingsController

try:
    from aiogram import Router
    from aiogram.types import CallbackQuery, Message
except ImportError:
    Router = None
    CallbackQuery = Any
    Message = Any


def _current_topic_router(runtime: TgBotRuntime) -> TopicRouter:
    runtime.topic_router = TopicRouter(runtime.settings_service.build_topic_router_config())
    return runtime.topic_router


def _spawn_background_analysis(runtime: TgBotRuntime, *, run_id: int, logger: logging.Logger) -> None:
    async def _runner() -> None:
        try:
            await runtime.task_queue.submit(
                name=f"tg_run:{run_id}",
                runner=lambda: process_tg_analysis_run(
                    runtime.db_connection,
                    run_id=run_id,
                    bot_client=runtime.bot_client,
                    its_service=runtime.its_service,
                    logger=logger,
                ),
            )
        except Exception as exc:
            logger.exception("TG background analysis failed run_id=%s", run_id)
            if runtime.db_connection is not None:
                await fail_tg_analysis_run(runtime.db_connection, run_id=run_id, error_text=str(exc))

    task = asyncio.create_task(_runner())

    def _log_task_result(done_task: asyncio.Task[None]) -> None:
        try:
            done_task.result()
        except Exception:
            logger.exception("TG background task crashed run_id=%s", run_id)

    task.add_done_callback(_log_task_result)


def build_tg_bot_router(
    runtime: TgBotRuntime,
    *,
    logger: logging.Logger | None = None,
) -> Router | None:
    if Router is None or runtime.bot_client is None:
        return None

    tg_logger = logger or logging.getLogger("agent_ui.interfaces.tg_bot.handlers")
    router = Router(name="tg_bot")
    settings_controller = TgBotSettingsController(
        settings=runtime.app_settings,
        settings_service=runtime.settings_service,
        bot_client=runtime.bot_client,
        its_service=runtime.its_service,
        logger=tg_logger,
    )

    @router.message()
    async def on_message(message: Message) -> None:
        message_text = extract_message_text(
            text=getattr(message, "text", None),
            caption=getattr(message, "caption", None),
        )
        if await settings_controller.handle_message(message=message, message_text=message_text):
            return

        chat_id = message.chat.id
        topic_id = getattr(message, "message_thread_id", None)
        topic_router = _current_topic_router(runtime)
        if not topic_router.is_allowed_message(chat_id=chat_id, topic_id=topic_id):
            return

        if runtime.db_connection is not None:
            queued_run = await queue_tg_analysis_message(
                runtime.db_connection,
                chat_id=chat_id,
                message_id=int(getattr(message, "message_id", 0) or 0),
                topic_id=topic_id,
                sender_id=(
                    int(getattr(getattr(message, "from_user", None), "id", 0) or 0)
                    if getattr(message, "from_user", None) is not None
                    else None
                ),
                text=message_text,
                chat_title=getattr(message.chat, "title", None),
                topic_name=getattr(getattr(message, "forum_topic_created", None), "name", None),
                message_date=getattr(message, "date", None),
            )
            tg_logger.info(
                "TG message stored chat_id=%s topic_id=%s message_id=%s run_id=%s deduplicated=%s",
                chat_id,
                topic_id,
                getattr(message, "message_id", None),
                queued_run.run_id,
                queued_run.deduplicated,
            )
            if not queued_run.deduplicated and runtime.bot_client is not None:
                _spawn_background_analysis(runtime, run_id=queued_run.run_id, logger=tg_logger)
            return

        tg_logger.info(
            "TG message accepted but TG DB is not configured chat_id=%s topic_id=%s message_id=%s",
            chat_id,
            topic_id,
            getattr(message, "message_id", None),
        )

    @router.callback_query()
    async def on_callback(query: CallbackQuery) -> None:
        if await settings_controller.handle_callback(query=query):
            return

    return router


__all__ = ["build_tg_bot_router"]
