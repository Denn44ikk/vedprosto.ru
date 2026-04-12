from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TnvedObservedAttributes:
    materials: tuple[str, ...] = ()
    material_evidence: tuple[str, ...] = ()
    uncertain_materials: tuple[str, ...] = ()


@dataclass(frozen=True)
class TnvedCriteriaBlock:
    summary: str = ""
    matched: tuple[str, ...] = ()
    numeric_matched: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    numeric_thresholds: tuple[str, ...] = ()
    text_flags: tuple[str, ...] = ()
    special_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TnvedClarificationQuestion:
    question: str
    why: str = ""
    missing_fact: str = ""
    priority: int = 0
    source_stage: str = "tnved"


@dataclass(frozen=True)
class TnvedCandidate:
    code: str
    probability_percent: float | None = None
    reason: str = ""
    source: str = ""
    criteria: TnvedCriteriaBlock = field(default_factory=TnvedCriteriaBlock)


@dataclass(frozen=True)
class TnvedIfcgDiscoveryHint:
    summary: str = ""
    suggested_groups: tuple[str, ...] = ()
    suggested_codes: tuple[str, ...] = ()
    broad_queries: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TnvedInput:
    item_name: str = ""
    image_description: str = ""
    user_text: str = ""
    triage_payload: dict[str, object] = field(default_factory=dict)
    web_hint_text: str = ""
    product_facts: dict[str, list[str]] = field(default_factory=dict)
    observed_attributes: TnvedObservedAttributes = field(default_factory=TnvedObservedAttributes)
    ifcg_discovery: TnvedIfcgDiscoveryHint | None = None


@dataclass(frozen=True)
class TnvedOutput:
    selected_code: str
    selected_description: str
    selection_rationale: str
    confidence_percent: float | None
    error_reason: str
    candidates: tuple[TnvedCandidate, ...]
    decisive_criteria: TnvedCriteriaBlock
    clarification_questions: tuple[TnvedClarificationQuestion, ...]
    product_facts: dict[str, list[str]]
    observed_attributes: TnvedObservedAttributes
    compacted_image_description: str
    ifcg_discovery_used: bool
    raw_payload: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)
