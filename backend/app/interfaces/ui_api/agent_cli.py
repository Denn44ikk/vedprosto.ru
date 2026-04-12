from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...dependencies import get_container
from .contracts.agent_cli import AgentCliHistoryResponse, AgentCliMessageRequest


router = APIRouter(prefix="/agent-cli", tags=["agent-cli"])


@router.get("/history", response_model=AgentCliHistoryResponse)
async def get_agent_cli_history(
    case_id: str | None = Query(default=None),
    container=Depends(get_container),
) -> AgentCliHistoryResponse:
    try:
        payload = await container.agent_cli_service.get_history_async(case_id=case_id)
        return AgentCliHistoryResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/message", response_model=AgentCliHistoryResponse)
async def send_agent_cli_message(
    request: AgentCliMessageRequest,
    container=Depends(get_container),
) -> AgentCliHistoryResponse:
    try:
        payload = await container.agent_cli_service.send_message_async(
            case_id=request.case_id,
            message=request.message,
        )
        return AgentCliHistoryResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
