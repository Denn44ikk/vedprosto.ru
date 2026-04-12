from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ....config import AppSettings
from ....integrations.telegram.bot_client import TelegramBotClient
from .service import TgBotRuntimeSettings, TgBotSettingsService, _env
from .session_runtime import resolve_session_path


@dataclass(frozen=True)
class SettingsStatusSnapshot:
    telegram_bot_id: int | None
    telegram_bot_username: str | None
    telegram_bot_display_name: str | None
    settings_topic_id: int | None
    price_topic_id: int | None
    its_enabled: bool
    its_runtime_status: str
    its_bot_username: str | None
    its_bot_username_source: str | None
    its_config_path: str | None
    its_session_path: str | None
    tg_api_id_present: bool
    tg_api_hash_present: bool
    session_file_exists: bool
    session_file_size: int | None
    session_file_mtime: str | None
    worker_running: bool
    inflight_count: int
    queue_size: int
    startup_error: str | None
    target_chat_id: int
    checked_at: str


@dataclass(frozen=True)
class ITSAccessCheckResult:
    ok: bool
    status: str
    message: str


def _bot_username_source(*, runtime_settings: TgBotRuntimeSettings, bot_username: str | None) -> str | None:
    if not bot_username:
        return None
    if runtime_settings.its_bot_username:
        return "runtime"
    return "tg_config.json"


async def build_settings_status_snapshot(
    *,
    settings: AppSettings,
    settings_service: TgBotSettingsService,
    its_service: Any | None = None,
    bot_client: TelegramBotClient | None = None,
) -> SettingsStatusSnapshot:
    runtime_settings = settings_service.load()
    its_config = settings_service.build_its_config(runtime_settings) if runtime_settings.its_enabled else None
    session_path = resolve_session_path(
        settings=settings,
        settings_service=settings_service,
        runtime_settings=runtime_settings,
        its_config=its_config,
    )
    session_file_exists = session_path.exists()
    session_file_size = session_path.stat().st_size if session_file_exists else None
    session_file_mtime = (
        datetime.fromtimestamp(session_path.stat().st_mtime).isoformat(timespec="seconds")
        if session_file_exists
        else None
    )

    runtime_status = "its_disabled"
    if runtime_settings.its_enabled:
        if its_config is None:
            runtime_status = "not_configured"
        elif not session_file_exists:
            runtime_status = "session_missing"
        elif its_service is None:
            runtime_status = "service_not_built"
        else:
            authorized = await its_service.check_authorized()
            if authorized:
                runtime_status = "authorized"
            elif its_service.startup_error:
                runtime_status = (
                    "session_invalid"
                    if "authorized" in str(its_service.startup_error).lower()
                    else "startup_error"
                )
            else:
                runtime_status = "session_invalid"

    telegram_bot_id: int | None = None
    telegram_bot_username: str | None = None
    telegram_bot_display_name: str | None = None
    if bot_client is not None:
        try:
            me: Any = await bot_client.get_me()
            telegram_bot_id = int(getattr(me, "id", 0) or 0) or None
            telegram_bot_username = (getattr(me, "username", None) or "").strip() or None
            full_name = " ".join(
                part.strip()
                for part in [
                    str(getattr(me, "first_name", "") or ""),
                    str(getattr(me, "last_name", "") or ""),
                ]
                if part and str(part).strip()
            ).strip()
            telegram_bot_display_name = full_name or telegram_bot_username
        except Exception:
            telegram_bot_id = None
            telegram_bot_username = None
            telegram_bot_display_name = None

    return SettingsStatusSnapshot(
        telegram_bot_id=telegram_bot_id,
        telegram_bot_username=telegram_bot_username,
        telegram_bot_display_name=telegram_bot_display_name,
        settings_topic_id=runtime_settings.settings_topic_id,
        price_topic_id=runtime_settings.price_topic_id,
        its_enabled=runtime_settings.its_enabled,
        its_runtime_status=runtime_status,
        its_bot_username=its_config.bot_username if its_config is not None else runtime_settings.its_bot_username,
        its_bot_username_source=_bot_username_source(
            runtime_settings=runtime_settings,
            bot_username=(its_config.bot_username if its_config is not None else runtime_settings.its_bot_username),
        ),
        its_config_path=its_config.config_path if its_config is not None else runtime_settings.its_config_path,
        its_session_path=str(session_path),
        tg_api_id_present=bool(_env("TG_API_ID")),
        tg_api_hash_present=bool(_env("TG_API_HASH")),
        session_file_exists=session_file_exists,
        session_file_size=session_file_size,
        session_file_mtime=session_file_mtime,
        worker_running=bool(its_service.worker_running) if its_service is not None else False,
        inflight_count=int(its_service.inflight_count) if its_service is not None else 0,
        queue_size=int(its_service.queue_size) if its_service is not None else 0,
        startup_error=(str(its_service.startup_error) if its_service is not None and its_service.startup_error else None),
        target_chat_id=runtime_settings.target_chat_id,
        checked_at=datetime.now().isoformat(timespec="seconds"),
    )


async def perform_its_access_check(
    *,
    settings: AppSettings,
    settings_service: TgBotSettingsService,
    its_service: Any | None,
) -> ITSAccessCheckResult:
    runtime_settings = settings_service.load()
    if not runtime_settings.its_enabled:
        return ITSAccessCheckResult(ok=False, status="its_disabled", message="ITS отключен в runtime settings.")

    its_config = settings_service.build_its_config(runtime_settings)
    if its_config is None:
        return ITSAccessCheckResult(ok=False, status="not_configured", message="ITS не сконфигурирован.")

    session_path = resolve_session_path(
        settings=settings,
        settings_service=settings_service,
        runtime_settings=runtime_settings,
        its_config=its_config,
    )
    if not session_path.exists():
        return ITSAccessCheckResult(ok=False, status="session_missing", message="Session-файл отсутствует.")
    if its_service is None:
        return ITSAccessCheckResult(ok=False, status="service_not_built", message="ITS service не собран.")

    try:
        if not await its_service.check_authorized():
            return ITSAccessCheckResult(ok=False, status="session_invalid", message="Session не авторизована.")
        ok, message = await its_service.verify_access()
        if not ok:
            lowered = (message or "").lower()
            if "authorized" in lowered:
                status = "session_invalid"
            elif "resolve peer" in lowered or "bot" in lowered:
                status = "bot_resolve_error"
            else:
                status = "startup_error"
            return ITSAccessCheckResult(ok=False, status=status, message=message or "Неизвестная ошибка")
        return ITSAccessCheckResult(ok=True, status="ok", message="Доступ к Telegram и ITS-боту подтвержден.")
    except Exception as exc:
        message = str(exc) or "Неизвестная ошибка"
        lowered = message.lower()
        if "authorized" in lowered:
            status = "session_invalid"
        elif "resolve peer" in lowered or "bot" in lowered:
            status = "bot_resolve_error"
        else:
            status = "startup_error"
        return ITSAccessCheckResult(ok=False, status=status, message=message)


__all__ = [
    "ITSAccessCheckResult",
    "SettingsStatusSnapshot",
    "build_settings_status_snapshot",
    "perform_its_access_check",
]
