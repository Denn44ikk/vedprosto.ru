from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


IfcgScope = Literal["group", "code", "other"]
IfcgSignalType = Literal["stat_confirmed", "group_examples", "tree_hint", "mixed"]
IfcgRelationFlag = Literal["same_leaf", "same_branch_other_leaf", "different_branch", "unknown"]
IfcgDecisionStatus = Literal["confirm", "branch", "mixed", "no_signal", "error"]
IfcgDiscoveryStatus = Literal["ready", "no_signal", "empty", "error"]


@dataclass(frozen=True)
class IfcgQuery:
    text: str
    group_filter: str = ""
    kind: Literal["broad", "focused"] = "broad"
    label: str = ""
    stat_mode: bool = False
    source: Literal["llm", "fallback", "system"] = "system"
    rationale: str = ""

    @property
    def cache_key(self) -> str:
        return f"{self.text.strip().lower()}|{self.group_filter.strip()}|{int(self.stat_mode)}"


@dataclass(frozen=True)
class IfcgTreeHit:
    code: str
    description: str
    code_level: int = 0
    href: str = ""


@dataclass(frozen=True)
class IfcgSectionHit:
    code: str
    description: str
    code_level: int = 0
    href: str = ""


@dataclass(frozen=True)
class IfcgDeclarationExample:
    code: str
    description: str
    query_text: str
    group_filter: str
    source_url: str
    section_code: str = ""
    section_scope: IfcgScope = "other"
    section_title: str = ""


@dataclass(frozen=True)
class IfcgClarificationBucket:
    code: str
    record_count: int
    share_percent: int
    scope: IfcgScope = "other"
    anchor: str = ""
    title: str = ""


@dataclass(frozen=True)
class IfcgStatSection:
    anchor: str
    title: str
    code: str
    scope: IfcgScope = "other"
    description: str = ""
    record_count: int = 0
    share_percent: int = 0
    examples: tuple[IfcgDeclarationExample, ...] = ()


@dataclass(frozen=True)
class IfcgSearchResult:
    query: IfcgQuery
    url: str
    status: str
    http_status: int
    tree_hits: tuple[IfcgTreeHit, ...] = ()
    note_hits: tuple[IfcgSectionHit, ...] = ()
    predecision_hits: tuple[IfcgSectionHit, ...] = ()
    stat_sections: tuple[IfcgStatSection, ...] = ()
    declaration_examples: tuple[IfcgDeclarationExample, ...] = ()
    clarifications: tuple[IfcgClarificationBucket, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class IfcgQueryPlan:
    broad_queries: tuple[IfcgQuery, ...]
    planner_name: str
    rationale: str = ""
    warnings: tuple[str, ...] = ()
    fallback_used: bool = False


@dataclass(frozen=True)
class IfcgCodeSummary:
    code: str
    total_examples: int
    broad_examples: int
    focused_examples: int
    matched_examples: int
    clarification_records: int
    clarification_share_percent: int
    support_score: int
    support_level: str
    matched_candidate: bool
    representative_examples: tuple[str, ...] = ()
    why: str = ""
    signal_type: IfcgSignalType = "group_examples"
    source_groups: tuple[str, ...] = ()
    relation_flag: IfcgRelationFlag = "unknown"


@dataclass(frozen=True)
class IfcgInput:
    item_name: str
    selected_code: str
    candidate_codes: tuple[str, ...] = ()
    context_text: str = ""
    decision_rationale: str = ""
    observed_materials: tuple[str, ...] = ()
    product_facts: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class IfcgDiscoveryInput:
    item_name: str = ""
    context_text: str = ""
    source_text: str = ""
    observed_materials: tuple[str, ...] = ()
    product_facts: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class IfcgAnalysisResult:
    used: bool
    query_plan: IfcgQueryPlan | None
    broad_queries: tuple[IfcgQuery, ...]
    focused_queries: tuple[IfcgQuery, ...]
    searches: tuple[IfcgSearchResult, ...]
    top_codes: tuple[IfcgCodeSummary, ...]
    operator_short_line: str
    operator_long_lines: tuple[str, ...]
    error: str = ""
    trace: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class IfcgJudgeResult:
    status: IfcgDecisionStatus
    dangerous_signal: bool
    rerun_recommended: bool
    operator_summary: str
    reason: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IfcgOutput:
    status: IfcgDecisionStatus
    summary: str
    selected_code: str
    candidate_codes: tuple[str, ...]
    top_codes: tuple[IfcgCodeSummary, ...]
    operator_short_line: str
    operator_long_lines: tuple[str, ...]
    dangerous_signal: bool
    rerun_recommended: bool
    used: bool
    query_plan: IfcgQueryPlan | None
    judge_result: IfcgJudgeResult | None
    error: str = ""
    trace: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload.get("query_plan") is None:
            payload["query_plan"] = {}
        return payload


@dataclass(frozen=True)
class IfcgDiscoveryOutput:
    status: IfcgDiscoveryStatus
    summary: str
    suggested_groups: tuple[str, ...]
    suggested_codes: tuple[str, ...]
    broad_queries: tuple[str, ...]
    top_codes: tuple[IfcgCodeSummary, ...]
    operator_short_line: str
    operator_long_lines: tuple[str, ...]
    used: bool
    warnings: tuple[str, ...] = ()
    error: str = ""
    trace: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)
