from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocument:
    source_path: str
    relative_path: str
    source_kind: str
    document_type: str
    parser: str
    file_sha256: str
    size_bytes: int = 0
    modified_at: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    source_path: str
    relative_path: str
    source_kind: str
    document_type: str
    chunk_index: int
    text: str
    section_context: str = ""
    mentioned_codes: tuple[str, ...] = field(default_factory=tuple)
    text_length: int = 0

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)
