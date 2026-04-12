from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import ServiceCacheSigma


@dataclass(frozen=True)
class SigmaCacheRecord:
    cache_key: str
    payload_json: dict[str, Any] | None
    success: bool
    updated_at: datetime | None


class CacheSigmaRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, cache_key: str) -> dict[str, Any] | None:
        entity = await self._session.get(ServiceCacheSigma, cache_key)
        if entity is None:
            return None
        return dict(entity.payload_json or {})

    async def get_record(self, *, cache_key: str) -> SigmaCacheRecord | None:
        entity = await self._session.get(ServiceCacheSigma, cache_key)
        if entity is None:
            return None
        return SigmaCacheRecord(
            cache_key=entity.cache_key,
            payload_json=dict(entity.payload_json or {}) if entity.payload_json is not None else None,
            success=bool(entity.success),
            updated_at=entity.updated_at,
        )

    async def set(
        self,
        *,
        cache_key: str,
        payload_json: dict[str, Any] | None,
        success: bool = True,
    ) -> ServiceCacheSigma:
        entity = await self._session.get(ServiceCacheSigma, cache_key)
        if entity is None:
            entity = ServiceCacheSigma(cache_key=cache_key, payload_json=payload_json, success=success)
            self._session.add(entity)
        else:
            entity.payload_json = payload_json
            entity.success = success
        await self._session.flush()
        return entity


__all__ = ["CacheSigmaRepo", "SigmaCacheRecord"]
