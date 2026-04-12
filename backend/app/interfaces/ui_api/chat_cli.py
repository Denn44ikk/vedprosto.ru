from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...dependencies import get_container
from .contracts.chat_cli import ChatCliHistoryResponse, ChatCliMessageRequest


router = APIRouter(prefix="/chat-cli", tags=["chat-cli"])


@router.get("/history", response_model=ChatCliHistoryResponse)
async def get_chat_cli_history(
    case_id: str | None = Query(default=None),
    container=Depends(get_container),
) -> ChatCliHistoryResponse:
    try:
        payload = await container.chat_cli_service.get_history_async(case_id=case_id)
        return ChatCliHistoryResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/message", response_model=ChatCliHistoryResponse)
async def send_chat_cli_message(
    request: ChatCliMessageRequest,
    container=Depends(get_container),
) -> ChatCliHistoryResponse:
    try:
        payload = await container.chat_cli_service.send_message_async(
            case_id=request.case_id,
            message=request.message,
        )
        return ChatCliHistoryResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
