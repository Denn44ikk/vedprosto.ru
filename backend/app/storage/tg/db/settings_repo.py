from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .models import TgRuntimeSetting


class TgRuntimeSettingsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> TgRuntimeSetting | None:
        entity = await self._session.get(TgRuntimeSetting, 1)
        return entity

    async def ensure_row(self) -> TgRuntimeSetting:
        entity = await self._session.get(TgRuntimeSetting, 1)
        if entity is None:
            entity = TgRuntimeSetting(id=1)
            self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, **values: object) -> TgRuntimeSetting:
        entity = await self.ensure_row()
        for key, value in values.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        await self._session.flush()
        return entity


__all__ = ["TgRuntimeSettingsRepo"]
