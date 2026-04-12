from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from .exceptions import BotApiUnavailableError

T = TypeVar("T")

try:
    from aiogram import Bot as _Bot
    from aiogram.exceptions import (
        TelegramBadRequest,
        TelegramConflictError,
        TelegramNetworkError,
        TelegramRetryAfter,
        TelegramServerError,
    )
    from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message
except ImportError:
    _Bot = None
    BufferedInputFile = Any
    InlineKeyboardMarkup = Any
    Message = Any
    TelegramBadRequest = RuntimeError
    TelegramConflictError = RuntimeError
    TelegramNetworkError = RuntimeError
    TelegramRetryAfter = RuntimeError
    TelegramServerError = RuntimeError


def _require_aiogram() -> None:
    if _Bot is None:
        raise BotApiUnavailableError("aiogram is not installed")


@dataclass(frozen=True)
class BotConfig:
    token: str
    max_attempts: int = 3
    base_delay: float = 1.0
    default_parse_mode: str | None = None


def classify_telegram_exception(exc: Exception) -> tuple[bool, float | None]:
    if isinstance(exc, TelegramRetryAfter):
        retry_after = getattr(exc, "retry_after", None)
        if isinstance(retry_after, (int, float)):
            return True, max(1.0, float(retry_after))
        return True, 1.0
    if isinstance(exc, (TelegramNetworkError, TelegramServerError, TelegramConflictError, asyncio.TimeoutError)):
        return True, None
    return False, None


def retry_delay_seconds(*, attempt: int, base_delay: float, cap: float = 180.0) -> float:
    return min(cap, base_delay * (2 ** max(0, attempt - 1)))


async def call_telegram_with_retry(
    *,
    operation: str,
    logger: logging.Logger,
    call: Callable[[], Awaitable[T]],
    max_attempts: int,
    base_delay: float,
) -> T:
    for attempt in range(1, max_attempts + 1):
        try:
            return await call()
        except Exception as exc:
            retryable, retry_after = classify_telegram_exception(exc)
            if retryable and attempt < max_attempts:
                delay = retry_after if retry_after is not None else retry_delay_seconds(
                    attempt=attempt,
                    base_delay=base_delay,
                    cap=60.0,
                )
                logger.warning(
                    "Telegram API retry operation=%s attempt=%s/%s delay=%.1fs error=%s",
                    operation,
                    attempt,
                    max_attempts,
                    delay,
                    exc.__class__.__name__,
                )
                await asyncio.sleep(delay)
                continue
            raise

    raise RuntimeError(f"Telegram API retry loop exited unexpectedly for operation={operation}")


class TelegramBotClient:
    def __init__(self, config: BotConfig, logger: logging.Logger | None = None) -> None:
        self._config = config
        self._logger = logger or logging.getLogger("agent_ui.integrations.telegram.bot")
        self._bot: _Bot | None = None

    @property
    def config(self) -> BotConfig:
        return self._config

    def get_bot(self) -> _Bot:
        return self._ensure_bot()

    def _ensure_bot(self) -> _Bot:
        _require_aiogram()
        if self._bot is None:
            self._bot = _Bot(token=self._config.token)
        return self._bot

    async def close(self) -> None:
        if self._bot is not None:
            await self._bot.session.close()
            self._bot = None

    async def get_me(self) -> Any:
        bot = self._ensure_bot()
        return await bot.get_me()

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        message_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message:
        bot = self._ensure_bot()

        async def _call() -> Message:
            try:
                return await bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=message_thread_id,
                    reply_to_message_id=reply_to_message_id,
                    text=text,
                    parse_mode=parse_mode or self._config.default_parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    reply_markup=reply_markup,
                )
            except Exception as exc:
                if not isinstance(exc, TelegramBadRequest):
                    raise
                message = str(exc).lower()
                missing_reply_target = "replied not found" in message or "reply message not found" in message
                if reply_to_message_id is None or not missing_reply_target:
                    raise
                self._logger.warning(
                    "Telegram reply target missing; sending without reply_to_message_id chat_id=%s thread_id=%s reply_to=%s",
                    chat_id,
                    message_thread_id,
                    reply_to_message_id,
                )
                return await bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=message_thread_id,
                    text=text,
                    parse_mode=parse_mode or self._config.default_parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    reply_markup=reply_markup,
                )

        return await call_telegram_with_retry(
            operation="send_message",
            logger=self._logger,
            call=_call,
            max_attempts=self._config.max_attempts,
            base_delay=self._config.base_delay,
        )

    async def send_photo(
        self,
        *,
        chat_id: int,
        photo: bytes | str,
        caption: str | None = None,
        filename: str = "image.jpg",
        message_thread_id: int | None = None,
        parse_mode: str | None = None,
    ) -> Message:
        bot = self._ensure_bot()

        async def _call() -> Message:
            payload = BufferedInputFile(photo, filename=filename) if isinstance(photo, bytes) else photo
            return await bot.send_photo(
                chat_id=chat_id,
                photo=payload,
                caption=caption,
                message_thread_id=message_thread_id,
                parse_mode=parse_mode or self._config.default_parse_mode,
            )

        return await call_telegram_with_retry(
            operation="send_photo",
            logger=self._logger,
            call=_call,
            max_attempts=self._config.max_attempts,
            base_delay=self._config.base_delay,
        )

    async def edit_message_text(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        disable_web_page_preview: bool | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message | bool:
        bot = self._ensure_bot()

        async def _call() -> Message | bool:
            try:
                return await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=parse_mode or self._config.default_parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    reply_markup=reply_markup,
                )
            except Exception as exc:
                if not isinstance(exc, TelegramBadRequest):
                    raise
                if "message is not modified" in str(exc).lower():
                    return True
                raise

        return await call_telegram_with_retry(
            operation="edit_message_text",
            logger=self._logger,
            call=_call,
            max_attempts=self._config.max_attempts,
            base_delay=self._config.base_delay,
        )

    async def delete_message(self, *, chat_id: int, message_id: int) -> bool:
        bot = self._ensure_bot()

        async def _call() -> bool:
            return await bot.delete_message(chat_id=chat_id, message_id=message_id)

        return await call_telegram_with_retry(
            operation="delete_message",
            logger=self._logger,
            call=_call,
            max_attempts=self._config.max_attempts,
            base_delay=self._config.base_delay,
        )

    async def forward_message(
        self,
        *,
        chat_id: int,
        from_chat_id: int,
        message_id: int,
        message_thread_id: int | None = None,
    ) -> Message:
        bot = self._ensure_bot()

        async def _call() -> Message:
            return await bot.forward_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                message_thread_id=message_thread_id,
            )

        return await call_telegram_with_retry(
            operation="forward_message",
            logger=self._logger,
            call=_call,
            max_attempts=self._config.max_attempts,
            base_delay=self._config.base_delay,
        )
