from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .models import ChatSession


@dataclass(frozen=True)
class ChatContextPacket:
    markdown: str
    payload: dict[str, Any] = field(default_factory=dict)


class ChatContextStore:
    @staticmethod
    def short_json(value: object) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return "null"

    def write_context_packet(self, session: ChatSession, packet: ChatContextPacket) -> None:
        session.context_path.parent.mkdir(parents=True, exist_ok=True)
        session.context_path.write_text(packet.markdown, encoding="utf-8")
