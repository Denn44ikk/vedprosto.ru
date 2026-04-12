from __future__ import annotations

import re

from .models import TnvedCriteriaBlock
from .parsing import normalize_code_10


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_text_items(value: object, *, max_items: int = 4) -> tuple[str, ...]:
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
                str(raw_item.get("summary") or raw_item.get("value") or raw_item.get("text") or raw_item.get("label") or "")
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


def empty_criteria_block() -> TnvedCriteriaBlock:
    return TnvedCriteriaBlock()


def normalize_criteria_block(raw: object) -> TnvedCriteriaBlock:
    if not isinstance(raw, dict):
        return empty_criteria_block()
    return TnvedCriteriaBlock(
        summary=_collapse_spaces(str(raw.get("summary") or raw.get("why") or raw.get("reason") or raw.get("difference") or ""))[:320],
        matched=_normalize_text_items(raw.get("matched") or raw.get("matched_facts")),
        numeric_matched=_normalize_text_items(
            raw.get("numeric_matched") or raw.get("matched_numeric") or raw.get("matched_thresholds")
        ),
        missing=_normalize_text_items(raw.get("missing") or raw.get("missing_facts")),
        contradictions=_normalize_text_items(raw.get("contradictions")),
        numeric_thresholds=_normalize_text_items(raw.get("numeric_thresholds") or raw.get("thresholds")),
        text_flags=_normalize_text_items(raw.get("text_flags")),
        special_flags=_normalize_text_items(raw.get("special_flags") or raw.get("special_conditions")),
    )


def criteria_has_signal(block: TnvedCriteriaBlock | None) -> bool:
    if block is None:
        return False
    return any(
        (
            block.summary,
            block.matched,
            block.numeric_matched,
            block.missing,
            block.contradictions,
            block.numeric_thresholds,
            block.text_flags,
            block.special_flags,
        )
    )


def extract_main_criteria(raw: dict[str, object]) -> TnvedCriteriaBlock:
    for key in ("decisive_criteria", "criteria", "selection_criteria"):
        block = normalize_criteria_block(raw.get(key))
        if criteria_has_signal(block):
            return block
    summary = _collapse_spaces(str(raw.get("criteria_summary") or raw.get("selection_criteria_summary") or ""))
    if summary:
        return normalize_criteria_block({"summary": summary})
    return empty_criteria_block()


def extract_candidate_criteria_map(raw: dict[str, object]) -> dict[str, TnvedCriteriaBlock]:
    result: dict[str, TnvedCriteriaBlock] = {}
    reasoned = raw.get("candidates_reasoned") or raw.get("reasoned_candidates") or []
    if not isinstance(reasoned, list):
        return result
    for item in reasoned:
        if not isinstance(item, dict):
            continue
        code = normalize_code_10(item.get("code") or item.get("tnved") or item.get("candidate") or "")
        if not code:
            continue
        block = normalize_criteria_block(item.get("decisive_criteria") or item.get("criteria"))
        if not criteria_has_signal(block):
            block = normalize_criteria_block(item)
        if not criteria_has_signal(block):
            block = normalize_criteria_block({"summary": item.get("why") or item.get("reason") or item.get("difference")})
        if criteria_has_signal(block):
            result[code] = block
    return result
