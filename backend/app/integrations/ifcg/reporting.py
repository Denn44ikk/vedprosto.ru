from __future__ import annotations

from .models import IfcgCodeSummary


def _signal_label(signal_type: str) -> str:
    if signal_type == "stat_confirmed":
        return "stat"
    if signal_type == "tree_hint":
        return "tree"
    return "примеры"


def build_ifcg_short_line(top_codes: tuple[IfcgCodeSummary, ...]) -> str:
    if not top_codes:
        return "IFCG: полезных примеров не найдено"
    parts: list[str] = []
    for item in top_codes[:2]:
        candidate_mark = " кандидат" if item.matched_candidate else ""
        detail = (
            f"{item.clarification_records} декл./{item.clarification_share_percent}%"
            if item.clarification_records
            else f"{item.total_examples} прим."
        )
        parts.append(
            f"{item.code} — {item.support_level}, {_signal_label(item.signal_type)}, {detail}{candidate_mark}"
        )
    return "IFCG: " + "; ".join(parts)


def build_ifcg_long_lines(top_codes: tuple[IfcgCodeSummary, ...]) -> tuple[str, ...]:
    if not top_codes:
        return ("IFCG: полезных примеров не найдено.",)
    lines: list[str] = []
    for item in top_codes:
        lines.append(
            (
                f"- {item.code}: level={item.support_level}, signal={item.signal_type}, score={item.support_score}, "
                f"clarified={item.clarification_records}/{item.clarification_share_percent}%, "
                f"examples={item.total_examples}, broad={item.broad_examples}, focused={item.focused_examples}, "
                f"candidate={'yes' if item.matched_candidate else 'no'}, relation={item.relation_flag}, why={item.why}"
            )
        )
        for example in item.representative_examples[:2]:
            lines.append(f"  пример: {example}")
    return tuple(lines)
