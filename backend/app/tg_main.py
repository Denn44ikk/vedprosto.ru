from __future__ import annotations

import asyncio
import logging

from .config import get_settings
from .interfaces.tg_bot.bot import build_tg_bot_runtime, close_tg_bot_runtime, start_tg_bot_runtime
from .interfaces.tg_bot.handlers import build_tg_bot_router

try:
    from aiogram import Dispatcher
except ImportError:
    Dispatcher = None


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def run_tg_bot() -> None:
    if Dispatcher is None:
        raise RuntimeError("aiogram is not installed")

    settings = get_settings()
    runtime = build_tg_bot_runtime(settings)
    if runtime.bot_client is None:
        raise RuntimeError("TG_BOT_TOKEN is not configured")

    await start_tg_bot_runtime(runtime)
    router = build_tg_bot_router(runtime)
    if router is None:
        await close_tg_bot_runtime(runtime)
        raise RuntimeError("Telegram router is unavailable")

    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    try:
        await dispatcher.start_polling(runtime.bot_client.get_bot())
    finally:
        await close_tg_bot_runtime(runtime)


def main() -> None:
    _configure_logging()
    asyncio.run(run_tg_bot())


if __name__ == "__main__":
    main()
