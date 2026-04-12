from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Coroutine

import aiohttp

from ...storage.tg.db.cache_sigma_repo import CacheSigmaRepo
from ...storage.tg.db.connection import TgDbConnection
from .models import SigmaConfig, SigmaPaycalcResult
from .parser import build_sigma_paycalc_url, parse_sigma_paycalc_bytes
from .utils import normalize_code_10

_TECHNICAL_FAILURE_STATUSES = {"timeout", "http_error", "transport_error", "fetch_error", "parse_error"}


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_sigma_config() -> SigmaConfig:
    timeout_sec = max(5, int(_env("SIGMA_TIMEOUT_SEC", "30") or "30"))
    delay_sec = max(0.0, float(_env("SIGMA_DELAY_SEC", "1.0") or "1.0"))
    max_retries = max(1, int(_env("SIGMA_MAX_RETRIES", "3") or "3"))
    cache_ttl_days = max(1, int(_env("SIGMA_CACHE_TTL_DAYS", "7") or "7"))
    return SigmaConfig(
        enabled=_env_bool("SIGMA_ENABLED", False),
        timeout_sec=timeout_sec,
        delay_sec=delay_sec,
        max_retries=max_retries,
        cache_ttl_days=cache_ttl_days,
    )


@dataclass(frozen=True)
class _QueueItem:
    code: str
    query_date: str
    future: asyncio.Future[SigmaPaycalcResult]


def _normalize_query_date(value: str | None) -> str:
    cleaned = re.sub(r"\s+", "", value or "")
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2})", cleaned)
    return cleaned if match else ""


def _cache_key(*, code: str, query_date: str) -> str:
    return f"{normalize_code_10(code)}:{_normalize_query_date(query_date)}"


def _fallback_result(*, code: str, query_date: str, status: str, error_text: str | None = None) -> SigmaPaycalcResult:
    normalized_code = normalize_code_10(code) or "0000000000"
    normalized_date = _normalize_query_date(query_date) or "01.01.70"
    return SigmaPaycalcResult(
        code=normalized_code,
        query_date=normalized_date,
        status=status,
        source_url=build_sigma_paycalc_url(code=normalized_code, query_date=normalized_date),
        error_text=error_text,
    )


def _result_from_payload(payload: dict[str, Any] | None, *, code: str, query_date: str) -> SigmaPaycalcResult | None:
    if not isinstance(payload, dict):
        return None
    try:
        return SigmaPaycalcResult.from_dict(payload)
    except Exception:
        return _fallback_result(code=code, query_date=query_date, status="parse_error", error_text="Invalid Sigma cache payload")


def _is_cache_reusable(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").strip().lower()
    return bool(status) and status not in _TECHNICAL_FAILURE_STATUSES


def _is_cache_fresh(updated_at: datetime | None, *, ttl_days: int) -> bool:
    if updated_at is None:
        return False
    normalized_updated_at = updated_at if updated_at.tzinfo is not None else updated_at.replace(tzinfo=timezone.utc)
    threshold = datetime.now(timezone.utc) - timedelta(days=max(1, int(ttl_days)))
    return normalized_updated_at >= threshold


class SigmaService:
    def __init__(
        self,
        *,
        config: SigmaConfig | None = None,
        db_connection: TgDbConnection | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config or build_sigma_config()
        self._db_connection = db_connection
        self._logger = logger or logging.getLogger("agent_ui.sigma")
        self._queue: asyncio.Queue[_QueueItem | None] = asyncio.Queue()
        self._inflight: dict[tuple[str, str], asyncio.Future[SigmaPaycalcResult]] = {}
        self._worker: asyncio.Task[None] | None = None
        self._owner_loop: asyncio.AbstractEventLoop | None = None

    @property
    def config(self) -> SigmaConfig:
        return self._config

    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    @property
    def worker_running(self) -> bool:
        return self._worker is not None and not self._worker.done()

    async def _run_in_owner_loop(
        self,
        coro: Coroutine[Any, Any, SigmaPaycalcResult | dict[str, SigmaPaycalcResult] | None],
    ) -> SigmaPaycalcResult | dict[str, SigmaPaycalcResult] | None:
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

    async def start(self) -> None:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not current_loop:
            self._reset_loop_runtime()
            self._owner_loop = current_loop
        return

    async def close(self) -> None:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is current_loop:
            self._owner_loop = None
        self._worker = None

    async def get_many(self, codes: list[str], *, query_date: str) -> dict[str, SigmaPaycalcResult]:
        normalized_date = _normalize_query_date(query_date)
        if not normalized_date:
            return {}
        results: dict[str, SigmaPaycalcResult] = {}
        ordered_codes: list[str] = []
        seen: set[str] = set()
        for raw_code in codes:
            code = normalize_code_10(raw_code)
            if not code or code in seen:
                continue
            seen.add(code)
            ordered_codes.append(code)

        batch_outage_error: str | None = None
        for code in ordered_codes:
            if batch_outage_error:
                results[code] = _fallback_result(
                    code=code,
                    query_date=normalized_date,
                    status="fetch_error",
                    error_text=batch_outage_error,
                )
                continue
            result = await self.get(code, query_date=normalized_date)
            if result.is_technical_failure:
                result = await self.get(code, query_date=normalized_date, bypass_cache=True)
            results[code] = result
            if result.is_technical_failure:
                batch_outage_error = result.error_text or "Sigma Soft временно недоступна"
        return results

    async def get(
        self,
        code: str,
        *,
        query_date: str,
        bypass_cache: bool = False,
    ) -> SigmaPaycalcResult:
        normalized_code = normalize_code_10(code)
        normalized_date = _normalize_query_date(query_date)
        if not normalized_code or not normalized_date:
            return _fallback_result(
                code=normalized_code or code,
                query_date=normalized_date or query_date,
                status="fetch_error",
                error_text="Пустой код или дата для Sigma Soft",
            )
        if not self.enabled:
            return _fallback_result(
                code=normalized_code,
                query_date=normalized_date,
                status="fetch_error",
                error_text="Sigma Soft disabled",
            )

        if not bypass_cache:
            cached = await self._load_from_cache(code=normalized_code, query_date=normalized_date)
            if cached is not None and _is_cache_reusable(cached.to_dict()):
                return cached

        result = await self._fetch_live(normalized_code, query_date=normalized_date)
        try:
            await self._store_to_cache(result)
        except Exception:
            self._logger.exception(
                "Failed to persist Sigma cache for code=%s date=%s",
                normalized_code,
                normalized_date,
            )
        return result

    async def _load_from_cache(self, *, code: str, query_date: str) -> SigmaPaycalcResult | None:
        if self._db_connection is None:
            return None
        # Temporary stability guard: async DB cache for Sigma is disabled on live path
        # because the shared async pool is still not reliable across worker loops.
        # We keep the code shape for a later safe re-enable.
        if True:
            return None
        async with self._db_connection.session() as session:
            repo = CacheSigmaRepo(session)
            record = await repo.get_record(cache_key=_cache_key(code=code, query_date=query_date))
        if record is None:
            return None
        if not record.success:
            return None
        if not _is_cache_fresh(record.updated_at, ttl_days=self._config.cache_ttl_days):
            return None
        return _result_from_payload(record.payload_json, code=code, query_date=query_date)

    async def _store_to_cache(self, result: SigmaPaycalcResult) -> None:
        if self._db_connection is None:
            return
        # Temporary stability guard: skip live DB writes until loop-safety is fully rebuilt.
        if True:
            return
        async with self._db_connection.session() as session:
            repo = CacheSigmaRepo(session)
            await repo.set(
                cache_key=_cache_key(code=result.code, query_date=result.query_date),
                payload_json=result.to_dict(),
                success=not result.is_technical_failure,
            )
            await session.commit()

    async def _fetch_live(self, code: str, *, query_date: str) -> SigmaPaycalcResult:
        url = build_sigma_paycalc_url(code=code, query_date=query_date)
        timeout = aiohttp.ClientTimeout(total=max(5, int(self._config.timeout_sec)))
        raw_bytes: bytes | None = None
        for attempt in range(1, self._config.max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            if response.status >= 500 and attempt < self._config.max_retries:
                                if self._config.delay_sec > 0:
                                    await asyncio.sleep(self._config.delay_sec)
                                continue
                            return _fallback_result(
                                code=code,
                                query_date=query_date,
                                status="http_error",
                                error_text=f"HTTP {response.status}",
                            )
                        raw_bytes = await response.read()
                break
            except asyncio.TimeoutError:
                if attempt < self._config.max_retries:
                    if self._config.delay_sec > 0:
                        await asyncio.sleep(self._config.delay_sec)
                    continue
                return _fallback_result(
                    code=code,
                    query_date=query_date,
                    status="timeout",
                    error_text=f"Timeout after {self._config.timeout_sec} sec",
                )
            except aiohttp.ClientError as exc:
                if attempt < self._config.max_retries:
                    if self._config.delay_sec > 0:
                        await asyncio.sleep(self._config.delay_sec)
                    continue
                return _fallback_result(
                    code=code,
                    query_date=query_date,
                    status="transport_error",
                    error_text=str(exc),
                )

        if raw_bytes is None:
            return _fallback_result(
                code=code,
                query_date=query_date,
                status="fetch_error",
                error_text="Sigma Soft did not return payload",
            )

        try:
            return parse_sigma_paycalc_bytes(
                raw_bytes,
                code=code,
                query_date=query_date,
                source_url=url,
            )
        except Exception as exc:
            self._logger.exception("Sigma parse failed for code=%s date=%s", code, query_date)
            return _fallback_result(
                code=code,
                query_date=query_date,
                status="parse_error",
                error_text=str(exc),
            )


__all__ = ["SigmaConfig", "SigmaService", "build_sigma_config"]
