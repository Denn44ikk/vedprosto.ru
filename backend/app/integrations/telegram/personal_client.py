from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .exceptions import (
    PersonalApiUnavailableError,
    PersonalFloodWaitError,
    PersonalPeerResolveError,
    PersonalSessionUnauthorizedError,
    PersonalTransportError,
)

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.custom.message import Message
else:
    TelegramClient = Any
    Message = Any

try:
    from telethon import TelegramClient as _TelegramClient, events
    from telethon.errors import (
        AuthKeyUnregisteredError,
        FloodWaitError,
        PasswordHashInvalidError,
        SessionPasswordNeededError,
    )
except ImportError:
    _TelegramClient = None
    events = None
    AuthKeyUnregisteredError = RuntimeError
    FloodWaitError = RuntimeError
    PasswordHashInvalidError = RuntimeError
    SessionPasswordNeededError = RuntimeError


def _require_telethon() -> None:
    if _TelegramClient is None or events is None:
        raise PersonalApiUnavailableError("telethon is not installed")


def _is_reply_after_sent_message(
    *,
    event: Message,
    sent_message: Message | None,
    ready_for_replies: bool,
) -> bool:
    if not ready_for_replies or sent_message is None:
        return False
    event_id = getattr(event, "id", None)
    sent_id = getattr(sent_message, "id", None)
    if isinstance(event_id, int) and isinstance(sent_id, int):
        return event_id > sent_id
    event_date = getattr(event, "date", None)
    sent_date = getattr(sent_message, "date", None)
    if event_date is not None and sent_date is not None:
        return event_date >= sent_date
    return True


@dataclass(frozen=True)
class PersonalTelegramConfig:
    api_id: str
    api_hash: str
    session_path: str
    timeout_sec: int = 30
    delay_sec: float = 3.0
    max_retries: int = 3
    device_model: str = "TGConnector"
    system_version: str = "Windows 10"
    app_version: str = "1.0"
    lang_code: str = "ru"
    system_lang_code: str = "ru-RU"

    @property
    def session_base_path(self) -> str:
        path = Path(self.session_path)
        if path.suffix.lower() == ".session":
            return str(path.with_suffix(""))
        return str(path)


class TelegramPersonalClient:
    def __init__(self, config: PersonalTelegramConfig, logger: logging.Logger | None = None) -> None:
        self._config = config
        self._logger = logger or logging.getLogger("agent_ui.integrations.telegram.personal")
        self._client: TelegramClient | None = None
        self._entities: dict[str, Any] = {}

    @property
    def config(self) -> PersonalTelegramConfig:
        return self._config

    def _make_client(self) -> TelegramClient:
        _require_telethon()
        return _TelegramClient(
            self._config.session_base_path,
            int(self._config.api_id),
            self._config.api_hash,
            device_model=self._config.device_model,
            system_version=self._config.system_version,
            app_version=self._config.app_version,
            lang_code=self._config.lang_code,
            system_lang_code=self._config.system_lang_code,
        )

    async def connect(
        self,
        on_phone_request: Callable[[], str | None] | None = None,
        on_code_request: Callable[[], str | None] | None = None,
        on_2fa_request: Callable[[], str | None] | None = None,
    ) -> bool:
        _require_telethon()
        session_dir = Path(self._config.session_path).expanduser().parent
        session_dir.mkdir(parents=True, exist_ok=True)

        if self._client is None:
            self._client = self._make_client()
        await self._client.connect()

        if await self._client.is_user_authorized():
            return True
        if on_phone_request is None:
            return False
        phone = on_phone_request()
        if not phone:
            return False

        try:
            await self._client.send_code_request(phone)
        except Exception as exc:
            raise PersonalTransportError(f"Failed to send Telegram code: {exc}") from exc

        if on_code_request is None:
            return False
        code = on_code_request()
        if not code:
            return False
        try:
            await self._client.sign_in(phone=phone, code=code)
            return True
        except SessionPasswordNeededError:
            if on_2fa_request is None:
                return False
            password = on_2fa_request()
            if not password:
                return False
            try:
                await self._client.sign_in(password=password)
                return True
            except PasswordHashInvalidError as exc:
                raise PersonalTransportError("Invalid 2FA password") from exc
        except Exception as exc:
            raise PersonalTransportError(f"Telegram authorization failed: {exc}") from exc

    async def reconnect(self) -> None:
        await self.disconnect()
        await self.ensure_connected()

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._entities.clear()

    async def ensure_connected(self) -> None:
        _require_telethon()
        if self._client is None:
            self._client = self._make_client()
        if not self._client.is_connected():
            await self._client.connect()
        if not await self._client.is_user_authorized():
            raise PersonalSessionUnauthorizedError("Telegram session is not authorized")

    async def check_authorized(self) -> bool:
        temp_client: TelegramClient | None = None
        try:
            session_path = Path(self._config.session_path).expanduser()
            if not session_path.exists():
                return False
            client = self._client
            if client is None:
                temp_client = self._make_client()
                client = temp_client
            if not client.is_connected():
                await client.connect()
            return bool(await client.is_user_authorized())
        except Exception:
            return False
        finally:
            if temp_client is not None:
                try:
                    await temp_client.disconnect()
                except Exception:
                    pass

    async def verify_access(self, peer: str | int | None = None) -> tuple[bool, str | None]:
        try:
            await self.ensure_connected()
            if peer is not None:
                await self.resolve_peer(peer)
            return True, None
        except Exception as exc:
            return False, str(exc) or "Telegram access check failed"

    async def resolve_peer(self, peer: str | int) -> Any:
        await self.ensure_connected()
        key = str(peer)
        if key in self._entities:
            return self._entities[key]
        try:
            entity = await self._client.get_entity(str(peer).lstrip("@"))
        except Exception as exc:
            raise PersonalPeerResolveError(f"Failed to resolve peer '{peer}': {exc}") from exc
        self._entities[key] = entity
        return entity

    async def send_message(self, peer: str | int, text: str) -> Message:
        await self.ensure_connected()
        entity = await self.resolve_peer(peer)
        try:
            return await self._client.send_message(entity, text)
        except FloodWaitError as exc:
            raise PersonalFloodWaitError(f"FloodWait: wait {getattr(exc, 'seconds', 0)} sec") from exc
        except AuthKeyUnregisteredError as exc:
            raise PersonalSessionUnauthorizedError("Telegram session is invalid") from exc
        except Exception as exc:
            raise PersonalTransportError(f"Failed to send Telegram message: {exc}") from exc

    async def send_message_and_wait(
        self,
        *,
        peer: str | int,
        text: str,
        timeout_sec: int | None = None,
        terminal_predicate: Callable[[str | None], bool] | None = None,
        non_terminal_grace_sec: float | None = None,
    ) -> str | None:
        _require_telethon()
        await self.ensure_connected()
        entity = await self.resolve_peer(peer)
        if self._client is None:
            return None

        wait_timeout = float(timeout_sec or self._config.timeout_sec)
        loop = asyncio.get_running_loop()
        reply_queue: asyncio.Queue[Message] = asyncio.Queue()
        sent_message: Message | None = None
        ready_for_replies = False

        @self._client.on(events.NewMessage(from_users=entity))
        async def _handler(event: Message) -> None:
            if not _is_reply_after_sent_message(
                event=event,
                sent_message=sent_message,
                ready_for_replies=ready_for_replies,
            ):
                return
            reply_queue.put_nowait(event)

        try:
            sent_message = await self._client.send_message(entity, text)
            ready_for_replies = True
            total_deadline = loop.time() + wait_timeout
            wait_deadline = total_deadline
            last_reply: str | None = None
            while True:
                remaining = wait_deadline - loop.time()
                if remaining <= 0:
                    return last_reply
                event = await asyncio.wait_for(reply_queue.get(), timeout=remaining)
                reply_text = str(event.raw_text or "")
                last_reply = reply_text
                if terminal_predicate is None or terminal_predicate(reply_text):
                    return reply_text
                if non_terminal_grace_sec is not None:
                    wait_deadline = min(total_deadline, loop.time() + max(0.0, float(non_terminal_grace_sec)))
        except FloodWaitError as exc:
            raise PersonalFloodWaitError(f"FloodWait: wait {getattr(exc, 'seconds', 0)} sec") from exc
        except AuthKeyUnregisteredError as exc:
            raise PersonalSessionUnauthorizedError("Telegram session is invalid") from exc
        except asyncio.TimeoutError:
            return None
        except Exception as exc:
            raise PersonalTransportError(f"Failed while waiting for Telegram reply: {exc}") from exc
        finally:
            self._client.remove_event_handler(_handler)
