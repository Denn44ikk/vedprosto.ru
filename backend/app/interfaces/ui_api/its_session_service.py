from __future__ import annotations

import asyncio
import os
import json
from dataclasses import dataclass, replace
from pathlib import Path

from ...config import AppSettings
from ...integrations.its.parser import parse_reply
from ...integrations.its.service import ITSService
from ..tg_bot.settings import (
    InteractiveSessionLogin,
    TgBotSettingsService,
    build_settings_status_snapshot,
    cleanup_temp_session_files,
    delete_current_session,
    install_temp_session,
    perform_its_access_check,
    related_session_files,
    resolve_session_path,
)


@dataclass
class _PendingUiLogin:
    login: InteractiveSessionLogin
    step: str


class UiItsSessionService:
    def __init__(
        self,
        *,
        settings: AppSettings,
        settings_service: TgBotSettingsService,
        its_service: ITSService | None = None,
    ) -> None:
        self._settings = settings
        self._settings_service = settings_service
        self._its_service = its_service
        self._pending: _PendingUiLogin | None = None
        self._lock = asyncio.Lock()

    def _load_suggested_test_code(self) -> str:
        config_path = None
        runtime_settings = self._settings_service.load()
        if runtime_settings.its_config_path:
            config_path = Path(runtime_settings.its_config_path)
        elif self._its_service is not None and getattr(self._its_service, "config", None) is not None:
            config_path_value = getattr(self._its_service.config, "config_path", None)
            if config_path_value:
                config_path = Path(str(config_path_value))
        elif self._settings.tg_its_config_path.exists():
            config_path = self._settings.tg_its_config_path

        if config_path is None:
            return ""
        if not config_path.is_absolute():
            config_path = (self._settings.runtime_dir.parent / config_path).resolve()
        if not config_path.exists():
            return ""
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return ""
        return str(payload.get("test_code") or "").strip()

    async def get_status_payload(self, *, note: str = "") -> dict[str, object]:
        snapshot = await build_settings_status_snapshot(
            settings=self._settings,
            settings_service=self._settings_service,
            its_service=self._its_service,
            bot_client=None,
        )
        return {
            "its_enabled": snapshot.its_enabled,
            "runtime_status": snapshot.its_runtime_status,
            "its_bot_username": snapshot.its_bot_username,
            "its_session_path": snapshot.its_session_path or "",
            "session_file_exists": snapshot.session_file_exists,
            "tg_api_ready": snapshot.tg_api_id_present and snapshot.tg_api_hash_present,
            "worker_running": snapshot.worker_running,
            "startup_error": snapshot.startup_error,
            "pending_login": self._pending is not None,
            "pending_step": self._pending.step if self._pending is not None else "",
            "suggested_test_code": self._load_suggested_test_code(),
            "note": note,
        }

    def _build_temp_session_path(self) -> Path:
        session_path = resolve_session_path(
            settings=self._settings,
            settings_service=self._settings_service,
            its_config=(getattr(self._its_service, "config", None) if self._its_service is not None else None),
        )
        return session_path.with_name(f"{session_path.stem}.pending_ui.session")

    async def start_login(self, *, phone: str) -> dict[str, object]:
        async with self._lock:
            if self._pending is not None:
                raise RuntimeError("ITS login уже запущен. Завершите его или отмените.")
            api_id = os.getenv("TG_API_ID", "").strip()
            api_hash = os.getenv("TG_API_HASH", "").strip()
            if not api_id or not api_hash:
                raise RuntimeError("В env не хватает TG_API_ID / TG_API_HASH.")
            production_session_path = resolve_session_path(
                settings=self._settings,
                settings_service=self._settings_service,
                its_config=(getattr(self._its_service, "config", None) if self._its_service is not None else None),
            )
            if related_session_files(production_session_path):
                raise RuntimeError("Сначала удалите текущую ITS session.")
            temp_session_path = self._build_temp_session_path()
            cleanup_temp_session_files(temp_session_path)
            login = InteractiveSessionLogin(api_id=api_id, api_hash=api_hash, session_path=temp_session_path)
            progress = await login.start(phone)
            if progress.status != "code_sent":
                await login.close()
                cleanup_temp_session_files(temp_session_path)
                raise RuntimeError(progress.message)
            self._pending = _PendingUiLogin(login=login, step="code")
        return await self.get_status_payload(note=progress.message)

    async def submit_code(self, *, code: str) -> dict[str, object]:
        async with self._lock:
            if self._pending is None:
                raise RuntimeError("ITS login не запущен.")
            if self._pending.step != "code":
                raise RuntimeError("Сейчас ожидается другой шаг логина.")
            progress = await self._pending.login.submit_code(code)
            if progress.status == "need_password":
                self._pending.step = "password"
                return await self.get_status_payload(note=progress.message)
            if progress.status == "done":
                temp_session_path = self._pending.login.session_path
                await self._pending.login.close()
                await install_temp_session(
                    settings=self._settings,
                    settings_service=self._settings_service,
                    temp_session_path=temp_session_path,
                    its_service=self._its_service,
                )
                self._pending = None
                return await self.get_status_payload(note=progress.message)
            raise RuntimeError(progress.message)

    async def submit_password(self, *, password: str) -> dict[str, object]:
        async with self._lock:
            if self._pending is None:
                raise RuntimeError("ITS login не запущен.")
            if self._pending.step != "password":
                raise RuntimeError("Сейчас 2FA пароль не ожидается.")
            progress = await self._pending.login.submit_password(password)
            if progress.status == "done":
                temp_session_path = self._pending.login.session_path
                await self._pending.login.close()
                await install_temp_session(
                    settings=self._settings,
                    settings_service=self._settings_service,
                    temp_session_path=temp_session_path,
                    its_service=self._its_service,
                )
                self._pending = None
                return await self.get_status_payload(note=progress.message)
            raise RuntimeError(progress.message)

    async def cancel_login(self) -> dict[str, object]:
        async with self._lock:
            if self._pending is not None:
                session_path = self._pending.login.session_path
                await self._pending.login.close()
                cleanup_temp_session_files(session_path)
                self._pending = None
        return await self.get_status_payload(note="ITS login отменен.")

    async def delete_session(self) -> dict[str, object]:
        async with self._lock:
            if self._pending is not None:
                raise RuntimeError("Сначала завершите или отмените активный ITS login.")
            result = await delete_current_session(
                settings=self._settings,
                settings_service=self._settings_service,
                its_service=self._its_service,
            )
        note = (
            f"Session удалена. Перемещено файлов: {len(result.moved_paths)}"
            if result.moved_paths
            else "Session-файлы не найдены."
        )
        return await self.get_status_payload(note=note)

    async def set_enabled(self, *, enabled: bool) -> dict[str, object]:
        async with self._lock:
            runtime_settings = self._settings_service.load()
            updated_settings = replace(runtime_settings, its_enabled=bool(enabled))
            await self._settings_service.save_async(updated_settings)
            if self._its_service is not None:
                await self._its_service.set_enabled(bool(enabled))
        note = (
            "ITS включен. Pipeline снова будет пробовать live-запросы в Telegram-бота."
            if enabled
            else "ITS выключен. Pipeline продолжит подбор без ожидания Telegram-бота."
        )
        return await self.get_status_payload(note=note)

    async def check_access_payload(self) -> dict[str, object]:
        result = await perform_its_access_check(
            settings=self._settings,
            settings_service=self._settings_service,
            its_service=self._its_service,
        )
        return {
            "status": await self.get_status_payload(note=result.message),
            "access_check": {
                "ok": result.ok,
                "status": result.status,
                "message": result.message,
            },
            "test_query": None,
        }

    async def test_query_payload(self, *, code: str) -> dict[str, object]:
        normalized_code = "".join(ch for ch in str(code or "").strip() if ch.isdigit())
        if not normalized_code:
            normalized_code = self._load_suggested_test_code()
        if not normalized_code:
            raise RuntimeError("Укажи тестовый код ИТС или задай test_code в tg_config.json.")
        if self._its_service is None:
            raise RuntimeError("ITS service не собран.")

        result = await self._its_service.get_its(normalized_code, bypass_cache=True)
        parsed_reply = parse_reply(result.raw_reply or "")
        note = result.error_text or f"ITS test query завершен со статусом: {result.status}"
        return {
            "status": await self.get_status_payload(note=note),
            "access_check": None,
            "test_query": {
                "code": result.code,
                "status": result.status,
                "its_value": result.its_value,
                "its_bracket_value": result.its_bracket_value,
                "reply_variant": result.reply_variant,
                "date_text": result.date_text,
                "raw_reply": result.raw_reply,
                "error_text": result.error_text,
                "reply_code_match_status": result.reply_code_match_status,
                "reply_code_candidates": list(result.reply_code_candidates),
                "parsed_reply": {
                    "variant": parsed_reply.get("variant") if isinstance(parsed_reply.get("variant"), int) else None,
                    "its": float(parsed_reply.get("its")) if isinstance(parsed_reply.get("its"), (int, float)) else None,
                    "its_scob": float(parsed_reply.get("its_scob")) if isinstance(parsed_reply.get("its_scob"), (int, float)) else None,
                    "date": str(parsed_reply.get("date") or "") or None,
                },
            },
        }
