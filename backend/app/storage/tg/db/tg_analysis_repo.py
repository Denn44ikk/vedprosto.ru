from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TgAnalysisResult, TgAnalysisRun


class TgAnalysisRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self,
        *,
        chat_id: int,
        source_message_id: int,
        topic_id: int | None = None,
        flow_name: str = "tg_flow",
        status: str = "queued",
        stage_name: str | None = None,
        case_key: str | None = None,
    ) -> TgAnalysisRun:
        entity = TgAnalysisRun(
            chat_id=chat_id,
            source_message_id=source_message_id,
            topic_id=topic_id,
            flow_name=flow_name,
            status=status,
            stage_name=stage_name,
            case_key=case_key,
            started_at=datetime.utcnow() if status == "running" else None,
        )
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get_run(self, *, run_id: int) -> TgAnalysisRun | None:
        return await self._session.get(TgAnalysisRun, run_id)

    async def update_run_status(
        self,
        *,
        run_id: int,
        status: str,
        stage_name: str | None = None,
        error_text: str | None = None,
    ) -> TgAnalysisRun | None:
        entity = await self._session.get(TgAnalysisRun, run_id)
        if entity is None:
            return None
        entity.status = status
        entity.stage_name = stage_name
        entity.error_text = error_text
        if status == "running" and entity.started_at is None:
            entity.started_at = datetime.utcnow()
        if status in {"done", "failed", "cancelled"}:
            entity.finished_at = datetime.utcnow()
        await self._session.flush()
        return entity

    async def upsert_result(
        self,
        *,
        run_id: int,
        tnved: str | None,
        tnved_status: str | None,
        report_short_text: str | None = None,
        report_full_text: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> TgAnalysisResult:
        entity = await self._session.get(TgAnalysisResult, run_id)
        if entity is None:
            entity = TgAnalysisResult(
                run_id=run_id,
                tnved=tnved,
                tnved_status=tnved_status,
                report_short_text=report_short_text,
                report_full_text=report_full_text,
                payload_json=payload_json,
            )
            self._session.add(entity)
        else:
            entity.tnved = tnved
            entity.tnved_status = tnved_status
            entity.report_short_text = report_short_text
            entity.report_full_text = report_full_text
            entity.payload_json = payload_json
        await self._session.flush()
        return entity

    async def get_latest_run_for_message(self, *, chat_id: int, source_message_id: int) -> TgAnalysisRun | None:
        stmt: Select[tuple[TgAnalysisRun]] = (
            select(TgAnalysisRun)
            .where(
                TgAnalysisRun.chat_id == chat_id,
                TgAnalysisRun.source_message_id == source_message_id,
            )
            .order_by(TgAnalysisRun.created_at.desc(), TgAnalysisRun.id.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_latest_result_for_message(self, *, chat_id: int, source_message_id: int) -> TgAnalysisResult | None:
        stmt: Select[tuple[TgAnalysisResult]] = (
            select(TgAnalysisResult)
            .join(TgAnalysisRun, TgAnalysisRun.id == TgAnalysisResult.run_id)
            .where(
                TgAnalysisRun.chat_id == chat_id,
                TgAnalysisRun.source_message_id == source_message_id,
            )
            .order_by(TgAnalysisRun.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()


__all__ = ["TgAnalysisRepo"]
