from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ChatTranscriptRole = Literal["user", "model"]


@dataclass(frozen=True)
class ChatTranscriptMessage:
    role: ChatTranscriptRole
    text: str
    created_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ChatSession:
    session_key: str
    case_id: str
    case_dir: Path
    transcript_path: Path
    context_path: Path
    mode: str
    transcript_mode: str
    web_search_mode: str
    intro_text: str


@dataclass(frozen=True)
class ChatResponse:
    case_id: str
    case_dir: str
    context_file: str
    transcript_file: str
    mode: str
    web_search_mode: str
    messages: list[dict[str, str]]

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "case_dir": self.case_dir,
            "context_file": self.context_file,
            "transcript_file": self.transcript_file,
            "mode": self.mode,
            "web_search_mode": self.web_search_mode,
            "messages": self.messages,
        }
