from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SemanticCodeEvaluation:
    code: str
    status: str
    support_score: float | None = None
    difference_for_operator: str = ""
    why: str = ""
    matched_facts: tuple[str, ...] = ()
    missing_facts: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()


@dataclass
class SemanticInput:
    evidence_summary: str
    selected_code: str = ""
    selected_description: str = ""
    llm_rationale: str = ""
    candidate_codes: tuple[str, ...] = ()
    descriptions: dict[str, str] = field(default_factory=dict)
    probability_map: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticOutput:
    selected_code: str
    selected_status: str
    reason: str
    selected_operator_summary: str
    evaluations: tuple[SemanticCodeEvaluation, ...]
    recommended_review: bool
    actionable: bool
    raw_payload: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)
