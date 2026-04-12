from __future__ import annotations

import re
from collections import Counter, defaultdict

from .models import IfcgCodeSummary, IfcgInput, IfcgRelationFlag, IfcgSearchResult


def _normalize_code(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) == 10 else ""


def _group_prefix(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[:4] if len(digits) >= 4 else ""


def _support_level(
    *,
    signal_type: str,
    clarification_records: int,
    clarification_share_percent: int,
    total_examples: int,
) -> str:
    if signal_type == "stat_confirmed":
        if clarification_share_percent >= 50 or clarification_records >= 5:
            return "strong"
        return "medium"
    if total_examples >= 3:
        return "medium"
    return "weak"


def build_code_summaries(
    *,
    search_input: IfcgInput,
    searches: tuple[IfcgSearchResult, ...],
    allowed_codes: set[str] | None = None,
    max_codes: int = 5,
) -> tuple[IfcgCodeSummary, ...]:
    selected_code = _normalize_code(search_input.selected_code)
    candidate_set = {_normalize_code(code) for code in search_input.candidate_codes}
    candidate_set.discard("")
    preferred_groups = {
        group
        for group in [_group_prefix(selected_code), *(_group_prefix(code) for code in candidate_set)]
        if group
    }

    broad_examples: Counter[str] = Counter()
    focused_examples: Counter[str] = Counter()
    total_examples: Counter[str] = Counter()
    clarification_records: Counter[str] = Counter()
    clarification_share_percent: dict[str, int] = {}
    examples_by_code: dict[str, list[str]] = defaultdict(list)
    group_sources: dict[str, set[str]] = defaultdict(set)
    signal_type_by_code: dict[str, str] = {}

    for search in searches:
        is_focused = bool(search.query.group_filter)
        for section in search.stat_sections:
            if section.scope == "code" and len(section.code) == 10:
                clarification_records[section.code] = max(clarification_records[section.code], section.record_count)
                clarification_share_percent[section.code] = max(
                    clarification_share_percent.get(section.code, 0),
                    section.share_percent,
                )
                signal_type_by_code[section.code] = "stat_confirmed"
            for example in section.examples:
                code = _normalize_code(example.code)
                if not code:
                    continue
                total_examples[code] += 1
                if is_focused:
                    focused_examples[code] += 1
                else:
                    broad_examples[code] += 1
                if example.description and example.description not in examples_by_code[code]:
                    examples_by_code[code].append(example.description)
                if section.code:
                    group_sources[code].add(section.code)
                signal_type_by_code.setdefault(code, "group_examples")

    if allowed_codes is not None:
        allowed_codes = {_normalize_code(code) for code in allowed_codes if _normalize_code(code)}

    all_codes = set(total_examples) | set(clarification_records)
    summaries: list[IfcgCodeSummary] = []
    for code in all_codes:
        if allowed_codes is not None and code not in allowed_codes:
            continue
        signal_type = signal_type_by_code.get(code, "group_examples")
        group_match_bonus = 1 if _group_prefix(code) in preferred_groups else 0
        candidate_bonus = 2 if code == selected_code else 1 if code in candidate_set else 0
        stat_bonus = clarification_share_percent.get(code, 0) + min(clarification_records[code], 50)
        example_bonus = min(total_examples[code], 20)
        support_score = stat_bonus + example_bonus + candidate_bonus + group_match_bonus
        support_level = _support_level(
            signal_type=signal_type,
            clarification_records=clarification_records[code],
            clarification_share_percent=clarification_share_percent.get(code, 0),
            total_examples=total_examples[code],
        )
        why_parts: list[str] = [signal_type]
        if clarification_records[code]:
            why_parts.append(f"clarified={clarification_records[code]}/{clarification_share_percent.get(code, 0)}%")
        if focused_examples[code]:
            why_parts.append(f"focused={focused_examples[code]}")
        if broad_examples[code]:
            why_parts.append(f"broad={broad_examples[code]}")
        if group_sources[code]:
            why_parts.append("groups=" + ",".join(sorted(group_sources[code])[:3]))
        if selected_code and code:
            if code == selected_code:
                relation_flag: IfcgRelationFlag = "same_leaf"
            elif _group_prefix(code) == _group_prefix(selected_code):
                relation_flag = "same_branch_other_leaf"
            else:
                relation_flag = "different_branch"
        else:
            relation_flag = "unknown"
        representative_examples = tuple(examples_by_code[code][:3])
        summaries.append(
            IfcgCodeSummary(
                code=code,
                total_examples=total_examples[code],
                broad_examples=broad_examples[code],
                focused_examples=focused_examples[code],
                matched_examples=focused_examples[code] + broad_examples[code],
                clarification_records=clarification_records[code],
                clarification_share_percent=clarification_share_percent.get(code, 0),
                support_score=support_score,
                support_level=support_level,
                matched_candidate=code == selected_code or code in candidate_set,
                representative_examples=representative_examples,
                why=", ".join(why_parts),
                signal_type=signal_type,  # type: ignore[arg-type]
                source_groups=tuple(sorted(group_sources[code])),
                relation_flag=relation_flag,
            )
        )

    summaries.sort(
        key=lambda item: (
            {"strong": 3, "medium": 2, "weak": 1}.get(item.support_level, 0),
            1 if item.signal_type == "stat_confirmed" else 0,
            item.clarification_share_percent,
            item.clarification_records,
            item.total_examples,
            1 if item.matched_candidate else 0,
            item.support_score,
        ),
        reverse=True,
    )
    return tuple(summaries[: max(1, max_codes)])
