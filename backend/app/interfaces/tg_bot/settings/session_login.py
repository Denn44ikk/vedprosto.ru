from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from telethon import TelegramClient as _TelegramClient
    from telethon.errors import PasswordHashInvalidError, SessionPasswordNeededError
except ImportError:
    _TelegramClient = None
    PasswordHashInvalidError = RuntimeError
    SessionPasswordNeededError = RuntimeError


@dataclass(frozen=True)
class SessionLoginProgress:
    status: str
    message: str


def _require_telethon_login() -> None:
    if _TelegramClient is None:
        raise RuntimeError("telethon is not installed")


class InteractiveSessionLogin:
    def __init__(self, *, api_id: str, api_hash: str, session_path: Path) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_path = session_path
        self._client: Any | None = None
        self._phone: str | None = None

    @property
    def session_path(self) -> Path:
        return self._session_path

    def _make_client(self) -> Any:
        _require_telethon_login()
        session_base_path = (
            str(self._session_path.with_suffix(""))
            if self._session_path.suffix.lower() == ".session"
            else str(self._session_path)
        )
        return _TelegramClient(
            session_base_path,
            int(self._api_id),
            self._api_hash,
            device_model="TNVED_Helper",
            system_version="Windows 10",
            app_version="2.0 (Settings)",
            lang_code="ru",
            system_lang_code="ru-RU",
        )

    async def start(self, phone: str) -> SessionLoginProgress:
        _require_telethon_login()
        normalized_phone = phone.strip()
        if not normalized_phone:
            return SessionLoginProgress(status="error", message="Пустой номер телефона.")
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = self._make_client()
        await self._client.connect()
        self._phone = normalized_phone
        try:
            await self._client.send_code_request(normalized_phone)
            return SessionLoginProgress(status="code_sent", message="Код отправлен. Введите код из Telegram.")
        except Exception as exc:
            await self.close()
            return SessionLoginProgress(status="error", message=f"Не удалось отправить код: {exc}")

    async def submit_code(self, code: str) -> SessionLoginProgress:
        if self._client is None or self._phone is None:
            return SessionLoginProgress(status="error", message="Login flow не инициализирован.")
        normalized_code = code.strip()
        if not normalized_code:
            return SessionLoginProgress(status="error", message="Пустой код подтверждения.")
        try:
            await self._client.sign_in(phone=self._phone, code=normalized_code)
            return SessionLoginProgress(status="done", message="Telegram session успешно авторизована.")
        except SessionPasswordNeededError:
            return SessionLoginProgress(status="need_password", message="Нужен пароль 2FA. Введите пароль.")
        except Exception as exc:
            return SessionLoginProgress(status="error", message=f"Ошибка авторизации по коду: {exc}")

    async def submit_password(self, password: str) -> SessionLoginProgress:
        if self._client is None:
            return SessionLoginProgress(status="error", message="Login flow не инициализирован.")
        normalized_password = password.strip()
        if not normalized_password:
            return SessionLoginProgress(status="error", message="Пустой пароль 2FA.")
        try:
            await self._client.sign_in(password=normalized_password)
            return SessionLoginProgress(status="done", message="Telegram session успешно авторизована.")
        except PasswordHashInvalidError:
            return SessionLoginProgress(status="error", message="Неверный пароль 2FA.")
        except Exception as exc:
            return SessionLoginProgress(status="error", message=f"Ошибка 2FA: {exc}")

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None


__all__ = ["InteractiveSessionLogin", "SessionLoginProgress"]
