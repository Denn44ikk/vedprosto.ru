from __future__ import annotations

import re

from ...integrations.ai.service import AIIntegrationService
from ...storage.knowledge.catalogs import normalize_code_10
from .models import SemanticCodeEvaluation, SemanticInput, SemanticOutput
from .prompts import build_semantic_guard_prompt


_ALLOWED_STATUS = {"supported", "insufficient_evidence", "contradicted", "unknown"}


def _collapse_spaces(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_status(value: object, *, default: str = "unknown") -> str:
    normalized = _collapse_spaces(value).lower()
    return normalized if normalized in _ALLOWED_STATUS else default


def _normalize_support_score(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", "."))
    except ValueError:
        return None
    return max(0.0, min(100.0, parsed))


def _normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _collapse_spaces(value).lower() in {"1", "true", "yes", "y", "да"}


def _normalize_fact_list(value: object, *, max_items: int = 4) -> tuple[str, ...]:
    if isinstance(value, list):
        items = [_collapse_spaces(item) for item in value]
    elif value is None:
        items = []
    else:
        items = [_collapse_spaces(part) for part in re.split(r"[;\n]+", str(value)) if _collapse_spaces(part)]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item[:200])
        if len(deduped) >= max_items:
            break
    return tuple(deduped)


def _normalize_output(payload: dict[str, object], *, allowed_codes: list[str]) -> SemanticOutput:
    allowed = {normalize_code_10(code) for code in allowed_codes if normalize_code_10(code)}
    evaluations_raw = payload.get("evaluations") or payload.get("candidate_evaluations") or []
    evaluations: list[SemanticCodeEvaluation] = []
    seen_codes: set[str] = set()
    if isinstance(evaluations_raw, list):
        for item in evaluations_raw:
            if not isinstance(item, dict):
                continue
            code = normalize_code_10(item.get("code") or item.get("tnved") or item.get("candidate") or "")
            if not code or code not in allowed or code in seen_codes:
                continue
            seen_codes.add(code)
            evaluations.append(
                SemanticCodeEvaluation(
                    code=code,
                    status=_normalize_status(item.get("status")),
                    support_score=_normalize_support_score(item.get("support_score") or item.get("score")),
                    difference_for_operator=_collapse_spaces(
                        item.get("difference_for_operator")
                        or item.get("operator_summary")
                        or item.get("difference_summary")
                        or ""
                    )[:280],
                    why=_collapse_spaces(item.get("why") or item.get("reason") or "")[:400],
                    matched_facts=_normalize_fact_list(item.get("matched_facts")),
                    missing_facts=_normalize_fact_list(item.get("missing_facts")),
                    contradictions=_normalize_fact_list(item.get("contradictions")),
                )
            )
    selected_code = normalize_code_10(payload.get("selected_code") or payload.get("best_code") or "")
    if selected_code not in allowed:
        selected_code = ""
    selected_status = _normalize_status(payload.get("selected_status"))
    if selected_code:
        for evaluation in evaluations:
            if evaluation.code == selected_code:
                selected_status = evaluation.status
                break
    operator_summary = _collapse_spaces(
        payload.get("selected_operator_summary") or payload.get("operator_summary") or payload.get("selected_summary") or ""
    )[:320]
    reason = _collapse_spaces(payload.get("reason") or payload.get("summary") or "")[:500]
    actionable = bool(evaluations or operator_summary or selected_code)
    return SemanticOutput(
        selected_code=selected_code,
        selected_status=selected_status,
        reason=reason,
        selected_operator_summary=operator_summary,
        evaluations=tuple(evaluations),
        recommended_review=_normalize_bool(payload.get("recommended_review")),
        actionable=actionable,
        raw_payload=payload,
        trace={
            "allowed_codes": list(allowed_codes),
            "selected_code": selected_code,
            "evaluation_count": len(evaluations),
            "actionable": actionable,
        },
    )


class SemanticService:
    def __init__(
        self,
        *,
        ai_service: AIIntegrationService,
        profile: str = "text_exp",
        max_tokens: int = 2000,
        use_fallback: bool = True,
    ) -> None:
        self._ai_service = ai_service
        self._profile = profile
        self._max_tokens = max(600, int(max_tokens))
        self._use_fallback = use_fallback

    async def analyze(self, run_input: SemanticInput) -> SemanticOutput:
        candidate_codes = [normalize_code_10(code) for code in run_input.candidate_codes if normalize_code_10(code)]
        candidate_codes = list(dict.fromkeys(candidate_codes))
        if not run_input.evidence_summary.strip() or not candidate_codes:
            return SemanticOutput(
                selected_code=normalize_code_10(run_input.selected_code),
                selected_status="unknown",
                reason="semantic_guard_skipped:no_context_or_candidates",
                selected_operator_summary="",
                evaluations=tuple(),
                recommended_review=False,
                actionable=False,
                raw_payload={},
                trace={"skipped": True},
            )
        prompt = build_semantic_guard_prompt(
            evidence_summary=run_input.evidence_summary[:5000],
            selected_code=normalize_code_10(run_input.selected_code),
            selected_description=_collapse_spaces(run_input.selected_description)[:400],
            llm_rationale=_collapse_spaces(run_input.llm_rationale)[:600],
            candidate_codes=candidate_codes,
            descriptions=run_input.descriptions,
            probability_map=run_input.probability_map,
        )
        payload = await self._ai_service.text_json(
            profile=self._profile,
            prompt=prompt,
            use_fallback=self._use_fallback,
            max_tokens=self._max_tokens,
        )
        if not isinstance(payload, dict):
            payload = {}
        output = _normalize_output(payload, allowed_codes=candidate_codes)
        return SemanticOutput(
            selected_code=output.selected_code,
            selected_status=output.selected_status,
            reason=output.reason,
            selected_operator_summary=output.selected_operator_summary,
            evaluations=output.evaluations,
            recommended_review=output.recommended_review,
            actionable=output.actionable,
            raw_payload=output.raw_payload,
            trace={**output.trace, "profile": self._profile, "prompt_chars": len(prompt)},
        )
