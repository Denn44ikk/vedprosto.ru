from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TnvedVbdHit:
    chunk_id: str
    source_path: str
    relative_path: str
    source_kind: str
    document_type: str
    section_context: str
    text: str
    score: float
    mentioned_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class TnvedVbdInput:
    selected_code: str
    selected_description: str = ""
    item_name: str = ""
    context_text: str = ""
    candidate_codes: tuple[str, ...] = ()
    product_facts: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class TnvedVbdOutput:
    status: str
    verification_status: str
    selected_code: str
    summary: str
    note: str = ""
    product_facts: tuple[str, ...] = ()
    reference_hits: tuple[TnvedVbdHit, ...] = ()
    example_hits: tuple[TnvedVbdHit, ...] = ()
    alternative_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    index_status: str = ""
    trace: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)
