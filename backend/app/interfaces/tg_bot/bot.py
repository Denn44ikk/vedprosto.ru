from __future__ import annotations

import logging
from dataclasses import dataclass

from ...config import AppSettings
from ...integrations.its import ITSService, TGItsClient
from ...integrations.telegram import TelegramBotClient, TelegramPersonalClient, TopicRouter
from ...storage.tg.db import TgDbConnection, build_tg_db_config
from .queue import TelegramTaskQueue
from .settings import TgBotRuntimeSettings, TgBotSettingsService


@dataclass
class TgBotRuntime:
    app_settings: AppSettings
    logger: logging.Logger
    db_connection: TgDbConnection | None
    runtime_settings: TgBotRuntimeSettings
    settings_service: TgBotSettingsService
    bot_client: TelegramBotClient | None
    topic_router: TopicRouter
    personal_client: TelegramPersonalClient | None
    its_service: ITSService | None
    task_queue: TelegramTaskQueue


def _build_personal_and_its(
    *,
    settings_service: TgBotSettingsService,
    runtime_settings: TgBotRuntimeSettings,
    logger: logging.Logger,
    db_connection: TgDbConnection | None,
) -> tuple[TelegramPersonalClient | None, ITSService | None]:
    if not runtime_settings.its_enabled:
        return None, None

    its_config = settings_service.build_its_config(runtime_settings)
    if its_config is None:
        return None, None

    personal_config = settings_service.build_personal_config()
    if personal_config is None:
        return None, None

    personal_client = TelegramPersonalClient(personal_config, logger=logger)
    its_service = ITSService(
        TGItsClient(its_config, personal_client=personal_client),
        logger=logger,
        db_connection=db_connection,
    )
    return personal_client, its_service


async def _rebuild_runtime_services(runtime: TgBotRuntime) -> None:
    if runtime.its_service is not None:
        await runtime.its_service.close()
    elif runtime.personal_client is not None:
        await runtime.personal_client.disconnect()

    runtime.topic_router = TopicRouter(runtime.settings_service.build_topic_router_config(runtime.runtime_settings))
    runtime.personal_client, runtime.its_service = _build_personal_and_its(
        settings_service=runtime.settings_service,
        runtime_settings=runtime.runtime_settings,
        logger=runtime.logger,
        db_connection=runtime.db_connection,
    )


def build_tg_bot_runtime(
    app_settings: AppSettings,
    *,
    logger: logging.Logger | None = None,
) -> TgBotRuntime:
    runtime_logger = logger or logging.getLogger("agent_ui.interfaces.tg_bot")
    db_config = build_tg_db_config()
    db_connection = TgDbConnection(db_config) if db_config is not None else None
    settings_service = TgBotSettingsService(app_settings, db_connection=db_connection)
    runtime_settings = settings_service.load()

    bot_config = settings_service.build_bot_config()
    topic_router = TopicRouter(settings_service.build_topic_router_config(runtime_settings))
    bot_client = TelegramBotClient(bot_config, logger=runtime_logger) if bot_config is not None else None
    personal_client, its_service = _build_personal_and_its(
        settings_service=settings_service,
        runtime_settings=runtime_settings,
        logger=runtime_logger,
        db_connection=db_connection,
    )

    return TgBotRuntime(
        app_settings=app_settings,
        logger=runtime_logger,
        db_connection=db_connection,
        runtime_settings=runtime_settings,
        settings_service=settings_service,
        bot_client=bot_client,
        topic_router=topic_router,
        personal_client=personal_client,
        its_service=its_service,
        task_queue=TelegramTaskQueue(logger=runtime_logger),
    )


async def start_tg_bot_runtime(runtime: TgBotRuntime) -> None:
    if runtime.db_connection is not None:
        await runtime.db_connection.create_schema()
        runtime.runtime_settings = await runtime.settings_service.hydrate_from_db()
        await _rebuild_runtime_services(runtime)
    await runtime.task_queue.start()
    if runtime.its_service is not None:
        await runtime.its_service.start()


async def close_tg_bot_runtime(runtime: TgBotRuntime) -> None:
    await runtime.task_queue.close()
    if runtime.its_service is not None:
        await runtime.its_service.close()
    elif runtime.personal_client is not None:
        await runtime.personal_client.disconnect()
    if runtime.bot_client is not None:
        await runtime.bot_client.close()
    if runtime.db_connection is not None:
        await runtime.db_connection.dispose()
