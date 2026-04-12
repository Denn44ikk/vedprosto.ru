from __future__ import annotations

import asyncio
import re

from ..telegram import (
    PersonalApiUnavailableError,
    PersonalFloodWaitError,
    PersonalPeerResolveError,
    PersonalSessionUnauthorizedError,
    PersonalTelegramConfig,
    PersonalTransportError,
    TelegramPersonalClient,
)
from .models import ITSConfig, ITSFetchResult
from .parser import classify_reply_code_match, parse_reply


def _non_terminal_reply_grace_sec(timeout_sec: int) -> float:
    return min(10.0, max(5.0, float(timeout_sec or 0)))


def _is_terminal_its_reply(*, requested_code: str, reply_text: str | None) -> bool:
    text = str(reply_text or "")
    parsed = parse_reply(text)
    reply_code_match_status, _ = classify_reply_code_match(
        requested_code=requested_code,
        reply_text=text,
    )
    if reply_code_match_status == "mismatch":
        return True
    return parsed.get("variant") in {1, 2, 3, 4}


class TGItsClient:
    def __init__(
        self,
        config: ITSConfig,
        personal_client: TelegramPersonalClient | None = None,
    ) -> None:
        self._config = config
        self._personal = personal_client or TelegramPersonalClient(
            PersonalTelegramConfig(
                api_id=config.api_id,
                api_hash=config.api_hash,
                session_path=config.session_path,
                timeout_sec=config.timeout_sec,
                delay_sec=config.delay_sec,
                max_retries=config.max_retries,
            )
        )

    @property
    def config(self) -> ITSConfig:
        return self._config

    @property
    def personal_client(self) -> TelegramPersonalClient:
        return self._personal

    async def check_authorized(self) -> bool:
        return await self._personal.check_authorized()

    async def verify_access(self) -> tuple[bool, str | None]:
        return await self._personal.verify_access(peer=self._config.bot_username)

    async def connect(self, **kwargs: object) -> bool:
        return await self._personal.connect(**kwargs)

    async def disconnect(self) -> None:
        await self._personal.disconnect()

    async def reconnect(self) -> None:
        await self._personal.reconnect()

    async def fetch_its(self, code: str) -> ITSFetchResult:
        normalized = re.sub(r"\D", "", code or "")
        if not normalized:
            return ITSFetchResult(
                code="",
                status="invalid_code",
                its_value=None,
                its_bracket_value=None,
                reply_variant=None,
                date_text=None,
                raw_reply="",
                error_text="Empty or invalid code",
            )

        try:
            await self._personal.resolve_peer(self._config.bot_username)
        except PersonalApiUnavailableError:
            return ITSFetchResult(
                code=normalized,
                status="telethon_missing",
                its_value=None,
                its_bracket_value=None,
                reply_variant=None,
                date_text=None,
                raw_reply="",
                error_text="telethon is not installed",
            )
        except PersonalSessionUnauthorizedError as exc:
            return ITSFetchResult(
                code=normalized,
                status="session_invalid",
                its_value=None,
                its_bracket_value=None,
                reply_variant=None,
                date_text=None,
                raw_reply="",
                error_text=str(exc),
            )
        except PersonalPeerResolveError as exc:
            return ITSFetchResult(
                code=normalized,
                status="bot_resolve_error",
                its_value=None,
                its_bracket_value=None,
                reply_variant=None,
                date_text=None,
                raw_reply="",
                error_text=str(exc),
            )

        last_error = ""
        for attempt in range(1, self._config.max_retries + 1):
            try:
                reply_timeout_sec = self._config.timeout_sec + _non_terminal_reply_grace_sec(
                    self._config.timeout_sec
                )
                reply = await asyncio.wait_for(
                    self._personal.send_message_and_wait(
                        peer=self._config.bot_username,
                        text=normalized,
                        timeout_sec=reply_timeout_sec,
                        terminal_predicate=lambda text: _is_terminal_its_reply(
                            requested_code=normalized,
                            reply_text=text,
                        ),
                        non_terminal_grace_sec=_non_terminal_reply_grace_sec(self._config.timeout_sec),
                    ),
                    timeout=reply_timeout_sec + 5.0,
                )
            except asyncio.TimeoutError:
                last_error = f"Timeout ({self._config.timeout_sec} sec)"
                if attempt < self._config.max_retries:
                    await asyncio.sleep(self._config.delay_sec)
                continue
            except PersonalSessionUnauthorizedError:
                return ITSFetchResult(
                    code=normalized,
                    status="session_invalid",
                    its_value=None,
                    its_bracket_value=None,
                    reply_variant=None,
                    date_text=None,
                    raw_reply="",
                    error_text="Telegram session is invalid",
                )
            except PersonalFloodWaitError as exc:
                delay_sec = float(self._config.delay_sec)
                wait_hint = re.search(r"(\d+)", str(exc))
                if wait_hint is not None:
                    delay_sec = max(delay_sec, float(wait_hint.group(1)) + 1.0)
                last_error = str(exc)
                await asyncio.sleep(delay_sec)
                continue
            except PersonalTransportError as exc:
                last_error = str(exc)
                if attempt < self._config.max_retries:
                    await asyncio.sleep(self._config.delay_sec)
                continue

            if reply is None:
                last_error = f"Timeout ({self._config.timeout_sec} sec)"
                if attempt < self._config.max_retries:
                    await asyncio.sleep(self._config.delay_sec)
                continue

            parsed = parse_reply(reply)
            reply_code_match_status, reply_code_candidates = classify_reply_code_match(
                requested_code=normalized,
                reply_text=reply,
            )
            if reply_code_match_status == "mismatch":
                candidate_text = ", ".join(reply_code_candidates) if reply_code_candidates else "?"
                return ITSFetchResult(
                    code=normalized,
                    status="reply_code_mismatch",
                    its_value=None,
                    its_bracket_value=None,
                    reply_variant=int(parsed.get("variant")) if isinstance(parsed.get("variant"), int) else None,
                    date_text=str(parsed.get("date") or "") or None,
                    raw_reply=reply,
                    error_text=f"ITS reply did not match request code: {candidate_text}",
                    reply_code_match_status=reply_code_match_status,
                    reply_code_candidates=reply_code_candidates,
                )
            variant = parsed.get("variant")
            if variant == 1:
                return ITSFetchResult(
                    code=normalized,
                    status="ok",
                    its_value=float(parsed.get("its")) if parsed.get("its") is not None else None,
                    its_bracket_value=None,
                    reply_variant=1,
                    date_text=str(parsed.get("date") or "") or None,
                    raw_reply=reply,
                    reply_code_match_status=reply_code_match_status,
                    reply_code_candidates=reply_code_candidates,
                )
            if variant == 2:
                return ITSFetchResult(
                    code=normalized,
                    status="ok",
                    its_value=float(parsed.get("its")) if parsed.get("its") is not None else None,
                    its_bracket_value=float(parsed.get("its_scob")) if parsed.get("its_scob") is not None else None,
                    reply_variant=2,
                    date_text=str(parsed.get("date") or "") or None,
                    raw_reply=reply,
                    reply_code_match_status=reply_code_match_status,
                    reply_code_candidates=reply_code_candidates,
                )
            if variant == 3:
                return ITSFetchResult(
                    code=normalized,
                    status="need_14_digits",
                    its_value=None,
                    its_bracket_value=None,
                    reply_variant=3,
                    date_text=str(parsed.get("date") or "") or None,
                    raw_reply=reply,
                    error_text="ITS bot requires 14 digits",
                    reply_code_match_status=reply_code_match_status,
                    reply_code_candidates=reply_code_candidates,
                )
            if variant == 4:
                return ITSFetchResult(
                    code=normalized,
                    status="no_its_in_bot",
                    its_value=None,
                    its_bracket_value=None,
                    reply_variant=4,
                    date_text=None,
                    raw_reply=reply,
                    error_text="ITS value is missing in the bot",
                    reply_code_match_status=reply_code_match_status,
                    reply_code_candidates=reply_code_candidates,
                )
            return ITSFetchResult(
                code=normalized,
                status="unknown_response",
                its_value=None,
                its_bracket_value=None,
                reply_variant=None,
                date_text=None,
                raw_reply=reply,
                error_text="ITS bot reply is not recognized",
                reply_code_match_status=reply_code_match_status,
                reply_code_candidates=reply_code_candidates,
            )

        return ITSFetchResult(
            code=normalized,
            status="timeout" if "timeout" in last_error.lower() else "transport_error",
            its_value=None,
            its_bracket_value=None,
            reply_variant=None,
            date_text=None,
            raw_reply="",
            error_text=last_error or "All retry attempts were exhausted",
        )
