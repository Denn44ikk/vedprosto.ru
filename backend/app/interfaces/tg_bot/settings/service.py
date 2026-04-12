from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ....config import AppSettings
from ....integrations.its.models import ITSConfig
from ....integrations.telegram.bot_client import BotConfig
from ....integrations.telegram.personal_client import PersonalTelegramConfig
from ....integrations.telegram.topic_router import TopicRouterConfig
from ....storage.tg.db.connection import TgDbConnection
from ....storage.tg.db.settings_repo import TgRuntimeSettingsRepo


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _parse_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_optional_int(raw: str | None, default: int | None = None) -> int | None:
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        return default
    return int(value)


def _parse_optional_float(raw: str | None, default: float | None = None) -> float | None:
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        return default
    return float(value.replace(",", "."))


def _parse_csv_int_set(raw: str | None) -> tuple[int, ...]:
    if raw is None or not raw.strip():
        return ()
    return tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))


def _parse_request_comment_topic_map(raw: str | None) -> dict[int, int]:
    if raw is None or not raw.strip():
        return {}
    parsed: dict[int, int] = {}
    for chunk in [item.strip() for item in raw.split(",") if item.strip()]:
        match = re.fullmatch(r"(-?\d+)\s*\(\s*(-?\d+)\s*\)", chunk)
        if match is None:
            raise ValueError(
                f"Invalid value '{chunk}' in TG_REQUEST_COMMENT_TOPIC_MAP. Expected format: request(comment)"
            )
        parsed[int(match.group(1))] = int(match.group(2))
    return parsed


def _parse_supplier_topic_map(raw: str | None) -> dict[str, int]:
    if raw is None or not raw.strip():
        return {}
    parsed: dict[str, int] = {}
    for chunk in [item.strip() for item in raw.split(",") if item.strip()]:
        match = re.fullmatch(r"([^(,]+?)\s*\(\s*(-?\d+)\s*\)", chunk)
        if match is None:
            raise ValueError(
                f"Invalid value '{chunk}' in TG_PRICE_SUPPLIER_TOPIC_MAP. Expected format: supplier(topic)"
            )
        parsed[match.group(1).strip().lower()] = int(match.group(2))
    return parsed


@dataclass(frozen=True)
class TgBotRuntimeSettings:
    target_chat_id: int = 0
    allowed_topic_ids: tuple[int, ...] = ()
    request_comment_topic_map: dict[int, int] = field(default_factory=dict)
    price_topic_id: int | None = None
    settings_topic_id: int | None = None
    supplier_topic_map: dict[str, int] = field(default_factory=dict)
    settings_admin_ids: tuple[int, ...] = ()
    its_enabled: bool = False
    its_config_path: str | None = None
    its_session_path: str | None = None
    its_bot_username: str | None = None
    its_timeout_sec: int = 30
    its_delay_sec: float = 3.0
    its_max_retries: int = 3


class TgBotSettingsService:
    def __init__(self, settings: AppSettings, *, db_connection: TgDbConnection | None = None) -> None:
        self._settings = settings
        self._db_connection = db_connection
        self._current = self._load_initial_settings()

    def _local_runtime_settings_path(self) -> Path:
        raw_path = _env("TG_RUNTIME_SETTINGS_PATH")
        if raw_path:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = (self._settings.agent_ui_dir / path).resolve()
            return path
        return self._settings.tg_its_dir / "runtime_settings.json"

    def _apply_local_runtime_overrides(self, runtime_settings: TgBotRuntimeSettings) -> TgBotRuntimeSettings:
        if self._db_connection is not None:
            return runtime_settings
        path = self._local_runtime_settings_path()
        if not path.exists():
            return runtime_settings
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return runtime_settings
        if not isinstance(payload, dict) or "its_enabled" not in payload:
            return runtime_settings
        raw_its_enabled = payload.get("its_enabled")
        its_enabled = (
            _parse_bool(raw_its_enabled, default=runtime_settings.its_enabled)
            if isinstance(raw_its_enabled, str)
            else bool(raw_its_enabled)
        )
        return replace(runtime_settings, its_enabled=its_enabled)

    def _save_local_runtime_settings(self, runtime_settings: TgBotRuntimeSettings) -> None:
        if self._db_connection is not None:
            return
        path = self._local_runtime_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "its_enabled": runtime_settings.its_enabled,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_initial_settings(self) -> TgBotRuntimeSettings:
        return self._apply_local_runtime_overrides(self._build_env_settings())

    def _build_env_settings(self) -> TgBotRuntimeSettings:
        return TgBotRuntimeSettings(
            target_chat_id=_parse_optional_int(_env("TG_TARGET_CHAT_ID"), 0) or 0,
            allowed_topic_ids=_parse_csv_int_set(_env("TG_ALLOWED_TOPIC_IDS")),
            request_comment_topic_map=_parse_request_comment_topic_map(_env("TG_REQUEST_COMMENT_TOPIC_MAP")),
            price_topic_id=_parse_optional_int(_env("TG_PRICE_TOPIC_ID")),
            settings_topic_id=_parse_optional_int(_env("TG_SETTINGS_TOPIC_ID")),
            supplier_topic_map=_parse_supplier_topic_map(_env("TG_PRICE_SUPPLIER_TOPIC_MAP")),
            settings_admin_ids=_parse_csv_int_set(_env("TG_SETTINGS_ADMIN_IDS")),
            its_enabled=_parse_bool(_env("TG_ITS_ENABLED"), default=False),
            its_config_path=_env("TG_ITS_CONFIG_PATH") or None,
            its_session_path=_env("TG_ITS_SESSION_PATH") or None,
            its_bot_username=_env("TG_ITS_BOT_USERNAME") or None,
            its_timeout_sec=_parse_optional_int(_env("TG_ITS_TIMEOUT_SEC"), 30) or 30,
            its_delay_sec=_parse_optional_float(_env("TG_ITS_DELAY_SEC"), 3.0) or 3.0,
            its_max_retries=_parse_optional_int(_env("TG_ITS_MAX_RETRIES"), 3) or 3,
        )

    def load(self) -> TgBotRuntimeSettings:
        return self._current

    def save(self, runtime_settings: TgBotRuntimeSettings) -> None:
        self._current = runtime_settings
        self._save_local_runtime_settings(runtime_settings)

    async def hydrate_from_db(self) -> TgBotRuntimeSettings:
        env_settings = self._build_env_settings()
        if self._db_connection is None:
            self._current = self._apply_local_runtime_overrides(env_settings)
            return self._current

        async with self._db_connection.session() as session:
            repo = TgRuntimeSettingsRepo(session)
            row = await repo.ensure_row()
            if self._is_blank_row(row):
                row = await repo.update(**self._to_repo_values(env_settings))
            await session.commit()
            self._current = self._from_repo_row(row, fallback=env_settings)
            return self._current

    async def save_async(self, runtime_settings: TgBotRuntimeSettings) -> TgBotRuntimeSettings:
        self._current = runtime_settings
        if self._db_connection is None:
            self._save_local_runtime_settings(runtime_settings)
            return self._current

        async with self._db_connection.session() as session:
            repo = TgRuntimeSettingsRepo(session)
            await repo.update(**self._to_repo_values(runtime_settings))
            await session.commit()
        return self._current

    def build_bot_config(self) -> BotConfig | None:
        token = _env("TG_BOT_TOKEN")
        if not token:
            return None
        return BotConfig(
            token=token,
            max_attempts=_parse_optional_int(_env("TG_BOT_MAX_ATTEMPTS"), 3) or 3,
            base_delay=_parse_optional_float(_env("TG_BOT_BASE_DELAY_SEC"), 1.0) or 1.0,
            default_parse_mode=_env("TG_BOT_PARSE_MODE") or None,
        )

    def build_topic_router_config(self, runtime_settings: TgBotRuntimeSettings | None = None) -> TopicRouterConfig:
        state = runtime_settings or self.load()
        return TopicRouterConfig(
            target_chat_id=state.target_chat_id,
            allowed_topic_ids=set(state.allowed_topic_ids),
            request_comment_topic_map=dict(state.request_comment_topic_map),
            price_topic_id=state.price_topic_id,
            settings_topic_id=state.settings_topic_id,
            supplier_topic_map=dict(state.supplier_topic_map),
        )

    def build_personal_config(self) -> PersonalTelegramConfig | None:
        api_id = _env("TG_API_ID")
        api_hash = _env("TG_API_HASH")
        session_path = _env("TG_SESSION_PATH")
        if not api_id or not api_hash or not session_path:
            return None
        return PersonalTelegramConfig(
            api_id=api_id,
            api_hash=api_hash,
            session_path=session_path,
            timeout_sec=_parse_optional_int(_env("TG_PERSONAL_TIMEOUT_SEC"), 30) or 30,
            delay_sec=_parse_optional_float(_env("TG_PERSONAL_DELAY_SEC"), 3.0) or 3.0,
            max_retries=_parse_optional_int(_env("TG_PERSONAL_MAX_RETRIES"), 3) or 3,
            device_model=_env("TG_DEVICE_MODEL", "TGConnector") or "TGConnector",
            system_version=_env("TG_SYSTEM_VERSION", "Windows 10") or "Windows 10",
            app_version=_env("TG_APP_VERSION", "1.0") or "1.0",
            lang_code=_env("TG_LANG_CODE", "ru") or "ru",
            system_lang_code=_env("TG_SYSTEM_LANG_CODE", "ru-RU") or "ru-RU",
        )

    def build_its_config(self, runtime_settings: TgBotRuntimeSettings | None = None) -> ITSConfig | None:
        state = runtime_settings or self.load()
        api_id = _env("TG_API_ID")
        api_hash = _env("TG_API_HASH")
        if not api_id or not api_hash:
            return None

        bot_username = state.its_bot_username
        if not bot_username and self._settings.tg_its_config_path.exists():
            try:
                raw_json = json.loads(self._settings.tg_its_config_path.read_text(encoding="utf-8-sig"))
            except Exception:
                raw_json = {}
            bot_username = str(raw_json.get("bot_username") or "").strip() or None
        if not bot_username:
            return None

        session_path = state.its_session_path or _env("TG_SESSION_PATH") or str(
            self._settings.tg_sessions_dir / "tg_its.session"
        )
        config_path = state.its_config_path or (
            str(self._settings.tg_its_config_path) if self._settings.tg_its_config_path.exists() else None
        )
        return ITSConfig(
            api_id=api_id,
            api_hash=api_hash,
            bot_username=bot_username,
            session_path=session_path,
            timeout_sec=max(1, int(state.its_timeout_sec)),
            delay_sec=float(state.its_delay_sec),
            max_retries=max(1, int(state.its_max_retries)),
            config_path=config_path,
        )

    @staticmethod
    def _is_blank_row(row: Any) -> bool:
        return not any(
            [
                bool(getattr(row, "target_chat_id", 0)),
                bool(getattr(row, "allowed_topic_ids_json", None)),
                bool(getattr(row, "request_comment_topic_map_json", None)),
                bool(getattr(row, "price_topic_id", None)),
                bool(getattr(row, "settings_topic_id", None)),
                bool(getattr(row, "supplier_topic_map_json", None)),
                bool(getattr(row, "settings_admin_ids_json", None)),
                bool(getattr(row, "its_enabled", False)),
                bool(getattr(row, "its_config_path", None)),
                bool(getattr(row, "its_session_path", None)),
                bool(getattr(row, "its_bot_username", None)),
            ]
        )

    @staticmethod
    def _from_repo_row(row: Any, *, fallback: TgBotRuntimeSettings) -> TgBotRuntimeSettings:
        return TgBotRuntimeSettings(
            target_chat_id=int(getattr(row, "target_chat_id", fallback.target_chat_id) or 0),
            allowed_topic_ids=tuple(int(item) for item in (getattr(row, "allowed_topic_ids_json", None) or [])),
            request_comment_topic_map={
                int(key): int(value)
                for key, value in dict(getattr(row, "request_comment_topic_map_json", None) or {}).items()
            },
            price_topic_id=getattr(row, "price_topic_id", fallback.price_topic_id),
            settings_topic_id=getattr(row, "settings_topic_id", fallback.settings_topic_id),
            supplier_topic_map={
                str(key).strip().lower(): int(value)
                for key, value in dict(getattr(row, "supplier_topic_map_json", None) or {}).items()
            },
            settings_admin_ids=tuple(int(item) for item in (getattr(row, "settings_admin_ids_json", None) or [])),
            its_enabled=bool(getattr(row, "its_enabled", fallback.its_enabled)),
            its_config_path=getattr(row, "its_config_path", fallback.its_config_path),
            its_session_path=getattr(row, "its_session_path", fallback.its_session_path),
            its_bot_username=getattr(row, "its_bot_username", fallback.its_bot_username),
            its_timeout_sec=int(getattr(row, "its_timeout_sec", fallback.its_timeout_sec) or fallback.its_timeout_sec),
            its_delay_sec=float(getattr(row, "its_delay_sec", fallback.its_delay_sec) or fallback.its_delay_sec),
            its_max_retries=int(getattr(row, "its_max_retries", fallback.its_max_retries) or fallback.its_max_retries),
        )

    @staticmethod
    def _to_repo_values(runtime_settings: TgBotRuntimeSettings) -> dict[str, Any]:
        return {
            "id": 1,
            "target_chat_id": runtime_settings.target_chat_id,
            "allowed_topic_ids_json": list(runtime_settings.allowed_topic_ids),
            "request_comment_topic_map_json": {
                str(key): int(value) for key, value in runtime_settings.request_comment_topic_map.items()
            },
            "price_topic_id": runtime_settings.price_topic_id,
            "settings_topic_id": runtime_settings.settings_topic_id,
            "supplier_topic_map_json": {
                str(key).strip().lower(): int(value) for key, value in runtime_settings.supplier_topic_map.items()
            },
            "settings_admin_ids_json": list(runtime_settings.settings_admin_ids),
            "its_enabled": runtime_settings.its_enabled,
            "its_config_path": runtime_settings.its_config_path,
            "its_session_path": runtime_settings.its_session_path,
            "its_bot_username": runtime_settings.its_bot_username,
            "its_timeout_sec": runtime_settings.its_timeout_sec,
            "its_delay_sec": runtime_settings.its_delay_sec,
            "its_max_retries": runtime_settings.its_max_retries,
        }


__all__ = [
    "TgBotRuntimeSettings",
    "TgBotSettingsService",
    "_env",
    "_parse_bool",
    "_parse_csv_int_set",
    "_parse_optional_float",
    "_parse_optional_int",
    "_parse_request_comment_topic_map",
    "_parse_supplier_topic_map",
]
