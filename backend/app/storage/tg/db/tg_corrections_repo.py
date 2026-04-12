from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TgCorrection


class TgCorrectionsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_correction(
        self,
        *,
        chat_id: int,
        request_topic_id: int | None,
        comment_topic_id: int | None,
        source_message_id: int,
        bot_message_id: int,
        operator_user_id: int | None,
        operator_name: str | None,
        old_tnved: str | None,
        new_tnved: str | None,
        reason_text: str | None,
        rule_text: str | None,
        raw_text: str | None,
        ref_text: str | None,
        forward_source_message_id: int | None = None,
        forward_bot_message_id: int | None = None,
        forward_note_message_id: int | None = None,
        status: str | None = None,
        error_text: str | None = None,
    ) -> TgCorrection:
        entity = TgCorrection(
            chat_id=chat_id,
            request_topic_id=request_topic_id,
            comment_topic_id=comment_topic_id,
            source_message_id=source_message_id,
            bot_message_id=bot_message_id,
            operator_user_id=operator_user_id,
            operator_name=operator_name,
            old_tnved=old_tnved,
            new_tnved=new_tnved,
            reason_text=reason_text,
            rule_text=rule_text,
            raw_text=raw_text,
            ref_text=ref_text,
            forward_source_message_id=forward_source_message_id,
            forward_bot_message_id=forward_bot_message_id,
            forward_note_message_id=forward_note_message_id,
            status=status,
            error_text=error_text,
        )
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def list_recent_corrections(self, *, chat_id: int, limit: int = 100) -> list[TgCorrection]:
        stmt: Select[tuple[TgCorrection]] = (
            select(TgCorrection)
            .where(TgCorrection.chat_id == chat_id)
            .order_by(TgCorrection.created_at.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())


__all__ = ["TgCorrectionsRepo"]
