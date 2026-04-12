from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class VectorDbHit:
    chunk_id: str
    source_path: str
    relative_path: str
    source_kind: str
    document_type: str
    section_context: str
    text: str
    score: float
    mentioned_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)
