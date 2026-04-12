from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AgentRole = Literal["user", "model"]


class AgentCliMessageView(BaseModel):
    role: AgentRole
    text: str
    created_at: str


class AgentCliHistoryResponse(BaseModel):
    case_id: str
    case_dir: str
    context_file: str
    transcript_file: str
    mode: str
    web_search_mode: str
    messages: list[AgentCliMessageView]


class AgentCliMessageRequest(BaseModel):
    case_id: str | None = None
    message: str = Field(min_length=1)
