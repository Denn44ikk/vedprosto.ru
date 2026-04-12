from __future__ import annotations

import json
import re

from .models import TnvedClarificationQuestion, TnvedCriteriaBlock, TnvedObservedAttributes


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_json_dict(raw_text: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw_text[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {}


def normalize_code_10(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) == 10 else ""


def normalize_tnved_payload(raw: dict[str, object]) -> dict[str, str]:
    tnved_raw = str(raw.get("tnved") or raw.get("tnved_10") or raw.get("code") or "").strip()
    tnved_digits = re.sub(r"\D", "", tnved_raw)
    tnved = normalize_code_10(tnved_raw) or tnved_digits
    tnved_description = _collapse_spaces(str(raw.get("tnved_description") or raw.get("description") or ""))
    selection_rationale = _collapse_spaces(
        str(raw.get("selection_rationale") or raw.get("explanation") or raw.get("rationale") or "")
    )
    error_reason = _collapse_spaces(str(raw.get("error_reason") or raw.get("error") or ""))
    return {
        "tnved": tnved,
        "tnved_description": tnved_description,
        "selection_rationale": selection_rationale,
        "error_reason": error_reason,
    }


def extract_candidate_codes(raw: dict[str, object]) -> list[str]:
    candidates: list[str] = []
    candidate_source = raw.get("candidates") or raw.get("possible_codes") or raw.get("candidate_codes") or []
    if isinstance(candidate_source, str):
        candidates.extend([part.strip() for part in re.split(r"[\n,;]+", candidate_source) if part.strip()])
    elif isinstance(candidate_source, list):
        candidates.extend([str(item).strip() for item in candidate_source if str(item).strip()])

    reasoned = raw.get("candidates_reasoned") or raw.get("reasoned_candidates") or []
    if isinstance(reasoned, list):
        for item in reasoned:
            if isinstance(item, dict):
                code = str(item.get("code") or item.get("tnved") or "").strip()
                if code:
                    candidates.append(code)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_code_10(candidate) or re.sub(r"\D", "", candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _parse_percent_value(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        raw_text = str(value).strip().replace(",", ".")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", raw_text)
        if not match:
            return None
        try:
            parsed = float(match.group(0))
        except ValueError:
            return None
    if "%" not in str(value) and 0 <= parsed <= 1:
        parsed *= 100.0
    return max(0.0, min(parsed, 100.0))


def parse_confidence_percent(raw: dict[str, object]) -> float | None:
    value = raw.get("confidence_percent") or raw.get("probability_percent") or raw.get("confidence") or raw.get(
        "confidence_pct"
    )
    return _parse_percent_value(value)


def extract_candidate_probability_map(raw: dict[str, object]) -> dict[str, float]:
    result: dict[str, float] = {}
    items = raw.get("candidates_reasoned") or raw.get("reasoned_candidates") or []
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        code = normalize_code_10(item.get("code") or item.get("tnved") or item.get("candidate") or "")
        if not code:
            continue
        parsed = _parse_percent_value(
            item.get("probability_percent") or item.get("confidence_percent") or item.get("probability")
        )
        if parsed is not None:
            result[code] = parsed
    return result


def extract_candidate_reason_map(raw: dict[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    items = raw.get("candidates_reasoned") or raw.get("reasoned_candidates") or []
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        code = normalize_code_10(item.get("code") or item.get("tnved") or item.get("candidate") or "")
        if not code:
            continue
        reason = _collapse_spaces(str(item.get("why") or item.get("reason") or item.get("difference") or ""))
        if reason:
            result[code] = reason[:320]
    return result


def _normalize_text_list(value: object, *, max_items: int = 5) -> tuple[str, ...]:
    if value is None:
        raw_items: list[object] = []
    elif isinstance(value, str):
        raw_items = [part for part in re.split(r"[;\n]+", value) if part.strip()]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = [value]

    result: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if isinstance(raw_item, dict):
            text = _collapse_spaces(
                str(raw_item.get("value") or raw_item.get("text") or raw_item.get("label") or raw_item.get("summary") or "")
            )
        else:
            text = _collapse_spaces(str(raw_item or ""))
        if not text:
            continue
        normalized = text.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(text[:220])
        if len(result) >= max_items:
            break
    return tuple(result)


def _normalize_question_text(value: object) -> str:
    text = _collapse_spaces(str(value or ""))
    text = re.sub(r"^(не подтверждено:|требуется подтверждение,?)+\s*", "", text, flags=re.IGNORECASE)
    if not text:
        return ""
    if text.endswith("?"):
        return text
    lowered = text.casefold()
    if lowered.startswith(("какой ", "какая ", "какие ", "каково ", "из ", "есть ли ", "это ")):
        return text + "?"
    return f"Уточните: {text}?"


def _normalize_priority(value: object, *, default: int) -> int:
    try:
        parsed = int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 9))


def _append_question(
    out: list[TnvedClarificationQuestion],
    *,
    seen: set[str],
    question: str,
    why: str = "",
    missing_fact: str = "",
    priority: int,
    max_items: int,
) -> None:
    normalized_question = _normalize_question_text(question)
    if not normalized_question:
        return
    key = normalized_question.casefold()
    if key in seen:
        return
    seen.add(key)
    out.append(
        TnvedClarificationQuestion(
            question=normalized_question[:240],
            why=_collapse_spaces(why)[:280],
            missing_fact=_collapse_spaces(missing_fact or question)[:220],
            priority=priority,
            source_stage="tnved",
        )
    )
    if len(out) > max_items:
        del out[max_items:]


def _fallback_questions_from_criteria(
    criteria: TnvedCriteriaBlock,
    *,
    max_items: int,
) -> tuple[TnvedClarificationQuestion, ...]:
    questions: list[TnvedClarificationQuestion] = []
    seen: set[str] = set()
    seed_facts = list(criteria.missing) + list(criteria.contradictions) + list(criteria.numeric_thresholds)
    for index, fact in enumerate(seed_facts, start=1):
        if len(questions) >= max_items:
            break
        _append_question(
            questions,
            seen=seen,
            question=fact,
            why=criteria.summary,
            missing_fact=fact,
            priority=index,
            max_items=max_items,
        )
    return tuple(questions[:max_items])


def extract_clarification_questions(
    raw: dict[str, object],
    *,
    decisive_criteria: TnvedCriteriaBlock | None = None,
    max_items: int = 3,
) -> tuple[TnvedClarificationQuestion, ...]:
    candidate_sources = (
        raw.get("clarification_questions")
        or raw.get("questions")
        or raw.get("top_questions")
        or raw.get("missing_information_questions")
        or raw.get("questions_for_operator")
        or []
    )
    questions: list[TnvedClarificationQuestion] = []
    seen: set[str] = set()
    if isinstance(candidate_sources, list):
        for index, item in enumerate(candidate_sources, start=1):
            if len(questions) >= max_items:
                break
            if isinstance(item, dict):
                _append_question(
                    questions,
                    seen=seen,
                    question=item.get("question") or item.get("text") or item.get("value") or item.get("missing_fact") or "",
                    why=item.get("why") or item.get("reason") or "",
                    missing_fact=item.get("missing_fact") or item.get("fact") or "",
                    priority=_normalize_priority(item.get("priority"), default=index),
                    max_items=max_items,
                )
            else:
                _append_question(
                    questions,
                    seen=seen,
                    question=item,
                    why="",
                    missing_fact=str(item or ""),
                    priority=index,
                    max_items=max_items,
                )
    elif isinstance(candidate_sources, str):
        for index, item in enumerate(re.split(r"[;\n]+", candidate_sources), start=1):
            if len(questions) >= max_items:
                break
            _append_question(
                questions,
                seen=seen,
                question=item,
                why="",
                missing_fact=item,
                priority=index,
                max_items=max_items,
            )

    if not questions and decisive_criteria is not None:
        return _fallback_questions_from_criteria(decisive_criteria, max_items=max_items)
    return tuple(sorted(questions[:max_items], key=lambda item: (item.priority, item.question.casefold())))


def extract_observed_attributes(raw: dict[str, object]) -> TnvedObservedAttributes:
    observed_raw = raw.get("observed_attributes")
    observed = observed_raw if isinstance(observed_raw, dict) else {}
    return TnvedObservedAttributes(
        materials=_normalize_text_list(observed.get("materials") if observed else raw.get("materials")),
        material_evidence=_normalize_text_list(
            observed.get("material_evidence") if observed else raw.get("material_evidence"),
            max_items=4,
        ),
        uncertain_materials=_normalize_text_list(
            observed.get("uncertain_materials") if observed else raw.get("uncertain_materials"),
            max_items=4,
        ),
    )


def merge_product_facts_with_observed_attributes(
    product_facts: dict[str, list[str]] | None,
    observed_attributes: TnvedObservedAttributes | None,
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {
        str(field): [str(item) for item in values]
        for field, values in (product_facts or {}).items()
        if isinstance(values, list)
    }
    merged.pop("material", None)
    if observed_attributes and observed_attributes.materials:
        merged["material"] = [str(item) for item in observed_attributes.materials]
    return merged
