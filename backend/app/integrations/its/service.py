from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Coroutine

from ...storage.tg.db import CacheItsRepo, TgDbConnection
from .client import TGItsClient
from .models import ITSFetchResult


@dataclass(frozen=True)
class _QueueItem:
    code: str
    future: asyncio.Future[ITSFetchResult]


def _normalize_code(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_cache_fresh(updated_at: datetime | None, *, ttl_days: int) -> bool:
    if updated_at is None:
        return False
    normalized_updated_at = updated_at if updated_at.tzinfo is not None else updated_at.replace(tzinfo=timezone.utc)
    threshold = _now_utc() - timedelta(days=max(1, int(ttl_days)))
    return normalized_updated_at >= threshold


def _is_cache_reusable(result: ITSFetchResult) -> bool:
    return result.status not in {
        "disabled",
        "not_configured",
        "session_invalid",
        "timeout",
        "transport_error",
        "auth_error",
        "bot_resolve_error",
        "batch_skipped_technical_outage",
        "worker_not_running",
        "its_error",
    }


class ITSService:
    def __init__(
        self,
        client: TGItsClient,
        *,
        logger: logging.Logger | None = None,
        db_connection: TgDbConnection | None = None,
        enabled: bool = True,
    ) -> None:
        self._client = client
        self._logger = logger or logging.getLogger("agent_ui.integrations.its")
        self._db_connection = db_connection
        self._cache_ttl_days = max(1, int((os.getenv("ITS_CACHE_TTL_DAYS", "7") or "7").strip()))
        self._queue: asyncio.Queue[_QueueItem | None] = asyncio.Queue()
        self._inflight: dict[str, asyncio.Future[ITSFetchResult]] = {}
        self._cache: dict[str, ITSFetchResult] = {}
        self._cache_updated_at: dict[str, datetime] = {}
        self._worker: asyncio.Task[None] | None = None
        self._worker_guard = asyncio.Lock()
        self._startup_error: str | None = None
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._enabled = bool(enabled)

    def _startup_check_timeout_sec(self) -> float:
        config = getattr(self._client, "config", None)
        timeout_sec = float(getattr(config, "timeout_sec", 10) or 10)
        return min(10.0, max(3.0, timeout_sec))

    @property
    def startup_error(self) -> str | None:
        return self._startup_error

    @property
    def config(self) -> object:
        return getattr(self._client, "config", None)

    @property
    def worker_running(self) -> bool:
        return self._worker is not None and not self._worker.done()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def inflight_count(self) -> int:
        return len(self._inflight)

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    async def _run_in_owner_loop(
        self,
        coro: Coroutine[Any, Any, ITSFetchResult | dict[str, ITSFetchResult] | bool | tuple[bool, str | None] | None],
    ) -> ITSFetchResult | dict[str, ITSFetchResult] | bool | tuple[bool, str | None] | None:
        owner_loop = self._owner_loop
        current_loop = asyncio.get_running_loop()
        if owner_loop is None or owner_loop is current_loop or not owner_loop.is_running():
            return await coro
        future = asyncio.run_coroutine_threadsafe(coro, owner_loop)
        return await asyncio.wrap_future(future)

    def _reset_loop_runtime(self) -> None:
        self._queue = asyncio.Queue()
        self._inflight = {}
        self._worker = None
        self._worker_guard = asyncio.Lock()

    def _disabled_result(self, code: str) -> ITSFetchResult:
        return ITSFetchResult(
            code=code,
            status="disabled",
            its_value=None,
            its_bracket_value=None,
            reply_variant=None,
            date_text=None,
            raw_reply="",
            error_text="ITS disabled by operator",
        )

    async def set_enabled(self, enabled: bool) -> None:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and self._owner_loop is not current_loop and self._owner_loop.is_running():
            await self._run_in_owner_loop(self.set_enabled(enabled))
            return
        self._enabled = bool(enabled)
        if self._enabled:
            await self.start()
            return

        for code, future in list(self._inflight.items()):
            if not future.done():
                future.set_result(self._disabled_result(code))
        self._inflight.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        await self._client.disconnect()

    async def start(self) -> None:
        if not self._enabled:
            self._startup_error = None
            return
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and self._owner_loop is not current_loop and self._owner_loop.is_running():
            await self._run_in_owner_loop(self.start())
            return
        if self._owner_loop is not current_loop:
            self._reset_loop_runtime()
            self._owner_loop = current_loop
        try:
            authorized = await asyncio.wait_for(
                self._client.check_authorized(),
                timeout=self._startup_check_timeout_sec(),
            )
            self._startup_error = None if authorized else "Telegram ITS session is not authorized"
        except asyncio.TimeoutError:
            self._startup_error = "Telegram ITS startup check timed out"
            self._logger.warning("ITS startup check timed out")
        except Exception as exc:
            self._startup_error = str(exc)
            self._logger.exception("ITS startup check failed")
        if not self.worker_running:
            self._worker = asyncio.create_task(self._worker_loop())

    async def close(self) -> None:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and self._owner_loop is not current_loop and self._owner_loop.is_running():
            await self._run_in_owner_loop(self.close())
            return
        if self._worker is not None:
            await self._queue.put(None)
            await self._worker
            self._worker = None
        await self._client.disconnect()

    async def reload_runtime(self) -> None:
        if not self._enabled:
            return
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and self._owner_loop is not current_loop and self._owner_loop.is_running():
            await self._run_in_owner_loop(self.reload_runtime())
            return
        await self.close()
        self._queue = asyncio.Queue()
        self._inflight = {}
        self._startup_error = None
        await self.start()

    async def check_authorized(self) -> bool:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and self._owner_loop is not current_loop and self._owner_loop.is_running():
            result = await self._run_in_owner_loop(self.check_authorized())
            return bool(result)
        try:
            authorized = await self._client.check_authorized()
            if authorized:
                self._startup_error = None
            return authorized
        except Exception:
            return False

    async def verify_access(self) -> tuple[bool, str | None]:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and self._owner_loop is not current_loop and self._owner_loop.is_running():
            result = await self._run_in_owner_loop(self.verify_access())
            return result if isinstance(result, tuple) else (False, "verify_access_proxy_failed")
        ok, message = await self._client.verify_access()
        if ok:
            self._startup_error = None
        else:
            self._startup_error = message or self._startup_error
        return ok, message

    async def get_its_many(self, codes: list[str], *, bypass_cache: bool = False) -> dict[str, ITSFetchResult]:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and self._owner_loop is not current_loop and self._owner_loop.is_running():
            result = await self._run_in_owner_loop(self.get_its_many(codes, bypass_cache=bypass_cache))
            return result if isinstance(result, dict) else {}
        results: dict[str, ITSFetchResult] = {}
        batch_outage_error: str | None = None
        seen: set[str] = set()
        for raw_code in codes:
            code = _normalize_code(raw_code)
            if not code or code in seen:
                continue
            seen.add(code)
            if not self._enabled:
                results[code] = self._disabled_result(code)
                continue
            if batch_outage_error:
                results[code] = ITSFetchResult(
                    code=code,
                    status="batch_skipped_technical_outage",
                    its_value=None,
                    its_bracket_value=None,
                    reply_variant=None,
                    date_text=None,
                    raw_reply="",
                    error_text=batch_outage_error,
                )
                continue
            result = await self.get_its(code, bypass_cache=bypass_cache)
            if result.is_batch_outage_failure:
                result = await self.get_its(code, bypass_cache=True)
            results[code] = result
            if result.is_batch_outage_failure:
                batch_outage_error = result.error_text or "ITS service is unavailable"
        return results

    async def get_its(self, code: str, *, bypass_cache: bool = False) -> ITSFetchResult:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and self._owner_loop is not current_loop and self._owner_loop.is_running():
            result = await self._run_in_owner_loop(self.get_its(code, bypass_cache=bypass_cache))
            if isinstance(result, ITSFetchResult):
                return result
        normalized = _normalize_code(code)
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
        if not self._enabled:
            return self._disabled_result(normalized)

        if not bypass_cache:
            cached = self._cache.get(normalized)
            cached_updated_at = self._cache_updated_at.get(normalized)
            if cached is not None and cached_updated_at is not None and not _is_cache_fresh(
                cached_updated_at,
                ttl_days=self._cache_ttl_days,
            ):
                self._cache.pop(normalized, None)
                self._cache_updated_at.pop(normalized, None)
                cached = None
            if cached is not None and _is_cache_reusable(cached):
                return cached
            cached = await self._load_from_db_cache(normalized)
            if cached is not None and _is_cache_reusable(cached):
                self._cache[normalized] = cached
                self._cache_updated_at[normalized] = _now_utc()
                return cached

        worker_ready = await self._ensure_worker_available()
        if not worker_ready:
            return ITSFetchResult(
                code=normalized,
                status="worker_not_running",
                its_value=None,
                its_bracket_value=None,
                reply_variant=None,
                date_text=None,
                raw_reply="",
                error_text=self._startup_error or "ITS worker recovery failed",
            )

        existing = self._inflight.get(normalized)
        if existing is not None:
            return await existing

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ITSFetchResult] = loop.create_future()
        self._inflight[normalized] = future
        await self._queue.put(_QueueItem(code=normalized, future=future))
        return await future

    async def _load_from_db_cache(self, code: str) -> ITSFetchResult | None:
        if self._db_connection is None:
            return None
        try:
            async with self._db_connection.session() as session:
                repo = CacheItsRepo(session)
                record = await repo.get_record(code=code)
            if record is None:
                return None
            if not _is_cache_fresh(record.updated_at, ttl_days=self._cache_ttl_days):
                return None
            return record.result
        except Exception:
            self._logger.exception("ITS DB cache read failed code=%s", code)
            return None

    async def _store_to_db_cache(self, result: ITSFetchResult) -> None:
        if self._db_connection is None:
            return
        try:
            async with self._db_connection.session() as session:
                repo = CacheItsRepo(session)
                await repo.set(result)
                await session.commit()
        except Exception:
            self._logger.exception("ITS DB cache write failed code=%s", result.code)

    async def _ensure_worker_available(self) -> bool:
        if self.worker_running:
            return True
        async with self._worker_guard:
            if self.worker_running:
                return True
            for code, future in list(self._inflight.items()):
                if not future.done():
                    future.set_result(
                        ITSFetchResult(
                            code=code,
                            status="worker_not_running",
                            its_value=None,
                            its_bracket_value=None,
                            reply_variant=None,
                            date_text=None,
                            raw_reply="",
                            error_text="ITS worker stopped before request completion",
                        )
                    )
            self._inflight.clear()
            self._logger.warning("ITS worker is not running, attempting runtime reload")
            try:
                await self.reload_runtime()
            except Exception as exc:
                self._startup_error = str(exc)
                self._logger.exception("ITS runtime reload failed while recovering worker")
                return False
            return self.worker_running

    async def _worker_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            try:
                result = await self._client.fetch_its(item.code)
                if _is_cache_reusable(result):
                    self._cache[item.code] = result
                    self._cache_updated_at[item.code] = _now_utc()
                    await self._store_to_db_cache(result)
                else:
                    self._cache.pop(item.code, None)
                    self._cache_updated_at.pop(item.code, None)
                if not item.future.done():
                    item.future.set_result(result)
            except Exception as exc:
                self._logger.exception("ITS worker failed for code=%s", item.code)
                fallback = ITSFetchResult(
                    code=item.code,
                    status="its_error",
                    its_value=None,
                    its_bracket_value=None,
                    reply_variant=None,
                    date_text=None,
                    raw_reply="",
                    error_text=str(exc),
                )
                self._cache.pop(item.code, None)
                self._cache_updated_at.pop(item.code, None)
                if not item.future.done():
                    item.future.set_result(fallback)
            finally:
                self._inflight.pop(item.code, None)
