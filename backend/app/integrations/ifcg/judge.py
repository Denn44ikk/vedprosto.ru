from __future__ import annotations

import json

from ...integrations.ai.service import AIIntegrationService
from .models import IfcgAnalysisResult, IfcgDecisionStatus, IfcgInput, IfcgJudgeResult


IFCG_JUDGE_PROMPT_RU = """Роль: старший декларант РФ.
Задача: интерпретировать уже собранную структурированную сводку IFCG по практике декларирования.

Правила:
- Не подбирай новый код автоматически.
- Не делай вывод только по одному совпавшему слову.
- Главный сигнал: устойчивость broad-групп, затем устойчивость stat-кодов, затем примеры.
- Если broad и stat стабильно подтверждают текущую ветку, это `confirm`.
- Если IFCG устойчиво показывает другую сущность или другую 4-значную ветку, это `branch`.
- Если сигнал частично полезный, но шумный или разнонаправленный, это `mixed`.
- Если IFCG не дал устойчивой практики, это `no_signal`.
- `dangerous_signal=true` только если это не соседний шум, а реальная альтернативная сущность.
- `rerun_recommended=true` только если есть устойчивый опасный branch-сигнал.

Верни строго JSON:
{
  "status": "confirm|branch|mixed|no_signal",
  "dangerous_signal": true,
  "rerun_recommended": false,
  "operator_summary": "1-2 коротких предложения для оператора",
  "reason": "краткое объяснение"
}
"""


def _collapse_spaces(value: str) -> str:
    return " ".join((value or "").split())


def _top_code_payload(result: IfcgAnalysisResult) -> list[dict[str, object]]:
    return [
        {
            "code": item.code,
            "support_level": item.support_level,
            "signal_type": item.signal_type,
            "clarification_records": item.clarification_records,
            "clarification_share_percent": item.clarification_share_percent,
            "total_examples": item.total_examples,
            "matched_candidate": item.matched_candidate,
            "source_groups": list(item.source_groups),
            "relation_flag": item.relation_flag,
            "why": item.why,
            "representative_examples": list(item.representative_examples[:2]),
        }
        for item in result.top_codes[:5]
    ]


def build_ifcg_v2_payload(
    *,
    search_input: IfcgInput,
    result: IfcgAnalysisResult,
    initial_status: str = "",
    initial_summary: str = "",
) -> dict[str, object]:
    broad_queries: list[dict[str, object]] = []
    focused_searches: list[dict[str, object]] = []
    query_map = result.trace.get("query_map")
    search_statuses = result.trace.get("search_statuses")

    for search in result.searches:
        if not search.query.group_filter:
            broad_queries.append(
                {
                    "query": search.query.text,
                    "rationale": search.query.rationale,
                    "status": search.status,
                    "groups": [
                        {
                            "code": bucket.code,
                            "record_count": bucket.record_count,
                            "share_percent": bucket.share_percent,
                        }
                        for bucket in search.clarifications
                        if bucket.scope == "group"
                    ][:8],
                    "tree_hits": [
                        {
                            "code": item.code,
                            "code_level": item.code_level,
                            "description": item.description,
                        }
                        for item in search.tree_hits[:5]
                    ],
                    "note_hits": [
                        {
                            "code": item.code,
                            "description": item.description,
                        }
                        for item in search.note_hits[:5]
                    ],
                    "predecision_hits": [
                        {
                            "code": item.code,
                            "description": item.description,
                        }
                        for item in search.predecision_hits[:5]
                    ],
                }
            )
        else:
            focused_searches.append(
                {
                    "query": search.query.text,
                    "group_filter": search.query.group_filter,
                    "status": search.status,
                    "codes": [
                        {
                            "code": section.code,
                            "record_count": section.record_count,
                            "share_percent": section.share_percent,
                            "example_count": len(section.examples),
                            "examples": [example.description for example in section.examples[:2]],
                        }
                        for section in search.stat_sections
                        if section.scope == "code"
                    ][:8],
                }
            )

    return {
        "source_context": {
            "item_name": search_input.item_name,
            "context_text": search_input.context_text,
            "decision_rationale": search_input.decision_rationale,
            "observed_materials": list(search_input.observed_materials),
            "product_facts": search_input.product_facts,
        },
        "current_selection": {
            "item_name": search_input.item_name,
            "selected_code": search_input.selected_code,
            "candidate_codes": list(search_input.candidate_codes),
        },
        "query_plan": {
            "planner_name": result.query_plan.planner_name if result.query_plan is not None else "",
            "rationale": result.query_plan.rationale if result.query_plan is not None else "",
            "warnings": list(result.query_plan.warnings) if result.query_plan is not None else [],
            "fallback_used": bool(result.query_plan.fallback_used) if result.query_plan is not None else False,
        },
        "initial_signal": {
            "status": initial_status,
            "summary": initial_summary,
        },
        "query_map": query_map if isinstance(query_map, list) else [],
        "search_statuses": search_statuses if isinstance(search_statuses, list) else [],
        "broad_queries": broad_queries,
        "focused_searches": focused_searches,
        "top_codes": _top_code_payload(result),
        "operator_short": result.operator_short_line,
        "operator_long": list(result.operator_long_lines),
    }


def _normalize_status(value: str) -> IfcgDecisionStatus | None:
    normalized = value.strip().lower()
    if normalized in {"confirm", "branch", "mixed", "no_signal", "error"}:
        return normalized  # type: ignore[return-value]
    return None


async def run_ifcg_judge(
    *,
    ai_service: AIIntegrationService,
    payload: dict[str, object],
    profile: str = "text_cheap",
    use_fallback: bool = True,
    max_tokens: int = 650,
) -> IfcgJudgeResult | None:
    prompt = IFCG_JUDGE_PROMPT_RU + "\n\nIFCG payload:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        response = await ai_service.text_json(
            profile=profile,
            prompt=prompt,
            use_fallback=use_fallback,
            max_tokens=max_tokens,
        )
    except Exception:
        return None

    if not isinstance(response, dict):
        return None
    status = _normalize_status(str(response.get("status") or ""))
    if status is None:
        return None
    return IfcgJudgeResult(
        status=status,
        dangerous_signal=bool(response.get("dangerous_signal")),
        rerun_recommended=bool(response.get("rerun_recommended")),
        operator_summary=_collapse_spaces(str(response.get("operator_summary") or "")),
        reason=_collapse_spaces(str(response.get("reason") or "")),
        raw=response,
    )
