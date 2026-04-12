from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TgBotReply


@dataclass(frozen=True)
class TgReplyLink:
    chat_id: int
    source_topic_id: int | None
    source_message_id: int
    bot_message_id: int
    bot_topic_id: int | None
    old_tnved: str | None
    source_message_ids: tuple[int, ...]
    correction_prompt_message_id: int | None
    status: str | None


class TgRepliesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_reply_link(
        self,
        *,
        chat_id: int,
        source_message_id: int,
        bot_message_id: int,
        source_topic_id: int | None = None,
        bot_topic_id: int | None = None,
        old_tnved: str | None = None,
        source_message_ids: list[int] | None = None,
        status: str | None = None,
    ) -> TgBotReply:
        entity = TgBotReply(
            chat_id=chat_id,
            source_message_id=source_message_id,
            bot_message_id=bot_message_id,
            source_topic_id=source_topic_id,
            bot_topic_id=bot_topic_id,
            old_tnved=old_tnved,
            source_message_ids_json=source_message_ids,
            status=status,
        )
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get_reply_link_by_bot_message(self, *, chat_id: int, bot_message_id: int) -> TgReplyLink | None:
        stmt: Select[tuple[TgBotReply]] = select(TgBotReply).where(
            TgBotReply.chat_id == chat_id,
            TgBotReply.bot_message_id == bot_message_id,
        )
        entity = (await self._session.execute(stmt)).scalar_one_or_none()
        if entity is None:
            return None
        return TgReplyLink(
            chat_id=entity.chat_id,
            source_topic_id=entity.source_topic_id,
            source_message_id=entity.source_message_id,
            bot_message_id=entity.bot_message_id,
            bot_topic_id=entity.bot_topic_id,
            old_tnved=entity.old_tnved,
            source_message_ids=tuple(entity.source_message_ids_json or ()),
            correction_prompt_message_id=entity.correction_prompt_message_id,
            status=entity.status,
        )

    async def set_correction_prompt_message_id(
        self,
        *,
        chat_id: int,
        bot_message_id: int,
        correction_prompt_message_id: int,
    ) -> TgBotReply | None:
        stmt: Select[tuple[TgBotReply]] = select(TgBotReply).where(
            TgBotReply.chat_id == chat_id,
            TgBotReply.bot_message_id == bot_message_id,
        )
        entity = (await self._session.execute(stmt)).scalar_one_or_none()
        if entity is None:
            return None
        entity.correction_prompt_message_id = correction_prompt_message_id
        await self._session.flush()
        return entity

    async def delete_reply_link(self, *, chat_id: int, bot_message_id: int) -> int:
        stmt = delete(TgBotReply).where(
            TgBotReply.chat_id == chat_id,
            TgBotReply.bot_message_id == bot_message_id,
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)


__all__ = ["TgRepliesRepo", "TgReplyLink"]
