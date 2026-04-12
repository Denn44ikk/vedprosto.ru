from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TgChat, TgMessage, TgTopic


class TgMessagesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_chat(self, *, chat_id: int, chat_title: str | None = None) -> TgChat:
        entity = await self._session.get(TgChat, chat_id)
        if entity is None:
            entity = TgChat(chat_id=chat_id, chat_title=chat_title)
            self._session.add(entity)
        else:
            entity.chat_title = chat_title
            entity.updated_at = datetime.utcnow()
        await self._session.flush()
        return entity

    async def upsert_topic(self, *, chat_id: int, topic_id: int, topic_name: str | None = None) -> TgTopic:
        entity = await self._session.get(TgTopic, {"chat_id": chat_id, "topic_id": topic_id})
        if entity is None:
            entity = TgTopic(chat_id=chat_id, topic_id=topic_id, topic_name=topic_name)
            self._session.add(entity)
        else:
            entity.topic_name = topic_name
            entity.updated_at = datetime.utcnow()
        await self._session.flush()
        return entity

    async def insert_message(
        self,
        *,
        chat_id: int,
        message_id: int,
        topic_id: int | None = None,
        sender_id: int | None = None,
        text: str | None = None,
        image_base64: str | None = None,
        image_mime: str | None = None,
        message_date: datetime | None = None,
    ) -> TgMessage:
        existing = await self.get_message(chat_id=chat_id, message_id=message_id)
        if existing is not None:
            return existing
        entity = TgMessage(
            chat_id=chat_id,
            message_id=message_id,
            topic_id=topic_id,
            sender_id=sender_id,
            text=text,
            image_base64=image_base64,
            image_mime=image_mime,
            message_date=message_date,
        )
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get_message(self, *, chat_id: int, message_id: int) -> TgMessage | None:
        stmt: Select[tuple[TgMessage]] = select(TgMessage).where(
            TgMessage.chat_id == chat_id,
            TgMessage.message_id == message_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_topic_messages(
        self,
        *,
        chat_id: int,
        topic_id: int,
        limit: int = 100,
    ) -> list[TgMessage]:
        stmt: Select[tuple[TgMessage]] = (
            select(TgMessage)
            .where(TgMessage.chat_id == chat_id, TgMessage.topic_id == topic_id)
            .order_by(TgMessage.message_id.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())


__all__ = ["TgMessagesRepo"]
