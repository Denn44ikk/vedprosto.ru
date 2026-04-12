from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import ChatSession, ChatTranscriptMessage


class ChatSessionStore:
    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def trim(messages: list[ChatTranscriptMessage], *, limit: int) -> list[ChatTranscriptMessage]:
        if limit <= 0:
            return []
        return messages[-limit:]

    def load_transcript(self, session: ChatSession) -> list[ChatTranscriptMessage]:
        if not session.transcript_path.exists():
            return []
        try:
            payload = json.loads(session.transcript_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if not isinstance(payload, dict):
            return []
        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list):
            return []

        messages: list[ChatTranscriptMessage] = []
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip()
            text = str(item.get("text", "")).strip()
            created_at = str(item.get("created_at", "")).strip() or self.now_iso()
            if role not in {"user", "model"} or not text:
                continue
            messages.append(ChatTranscriptMessage(role=role, text=text, created_at=created_at))
        return messages

    def save_transcript(self, session: ChatSession, *, messages: list[ChatTranscriptMessage]) -> None:
        session.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "case_id": session.case_id,
            "session_key": session.session_key,
            "mode": session.transcript_mode,
            "updated_at": self.now_iso(),
            "messages": [message.as_dict() for message in messages],
        }
        session.transcript_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_intro(self, session: ChatSession, messages: list[ChatTranscriptMessage]) -> list[ChatTranscriptMessage]:
        if messages:
            return messages
        return [
            ChatTranscriptMessage(
                role="model",
                text=session.intro_text,
                created_at=self.now_iso(),
            )
        ]
