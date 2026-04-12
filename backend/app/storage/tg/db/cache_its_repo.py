from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ....integrations.its.models import ITSFetchResult
from .models import ServiceCacheIts


@dataclass(frozen=True)
class ItsCacheRecord:
    result: ITSFetchResult
    updated_at: datetime | None


class CacheItsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, code: str) -> ITSFetchResult | None:
        record = await self.get_record(code=code)
        return record.result if record is not None else None

    async def get_record(self, *, code: str) -> ItsCacheRecord | None:
        entity = await self._session.get(ServiceCacheIts, code)
        if entity is None:
            return None
        return ItsCacheRecord(
            result=ITSFetchResult(
                code=code,
                status=entity.status or "unknown",
                its_value=entity.its_value,
                its_bracket_value=entity.its_bracket_value,
                reply_variant=entity.reply_variant,
                date_text=entity.date_text,
                raw_reply="",
                error_text=entity.error_text,
                reply_code_match_status=entity.reply_code_match_status or "not_checked",
                reply_code_candidates=tuple(entity.reply_code_candidates_json or ()),
            ),
            updated_at=entity.updated_at,
        )

    async def set(self, result: ITSFetchResult) -> ServiceCacheIts:
        entity = await self._session.get(ServiceCacheIts, result.code)
        if entity is None:
            entity = ServiceCacheIts(
                code=result.code,
                status=result.status,
                its_value=result.its_value,
                its_bracket_value=result.its_bracket_value,
                reply_variant=result.reply_variant,
                date_text=result.date_text,
                error_text=result.error_text,
                reply_code_match_status=result.reply_code_match_status,
                reply_code_candidates_json=list(result.reply_code_candidates),
            )
            self._session.add(entity)
        else:
            entity.status = result.status
            entity.its_value = result.its_value
            entity.its_bracket_value = result.its_bracket_value
            entity.reply_variant = result.reply_variant
            entity.date_text = result.date_text
            entity.error_text = result.error_text
            entity.reply_code_match_status = result.reply_code_match_status
            entity.reply_code_candidates_json = list(result.reply_code_candidates)
        await self._session.flush()
        return entity

__all__ = ["CacheItsRepo", "ItsCacheRecord"]
