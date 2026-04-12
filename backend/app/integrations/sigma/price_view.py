from __future__ import annotations

import re

from .models import SigmaEcoGroup, SigmaPaycalcResult, SigmaPriceSection, SigmaPriceSnapshot, SigmaRawRow
from .utils import (
    PP1637_CUSTOMS_FEE_EMOJI,
    SIGMA_EXCISE_EMOJI,
    SIGMA_MANDATORY_MARKING_EMOJI,
    SIGMA_PROTECTIVE_EMOJI,
    SIGMA_SECTION_ECO_EMOJI,
    normalize_emoji_flags,
)


def _collapse_spaces(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _trim_text(value: str | None, *, max_len: int = 1600) -> str:
    cleaned = _collapse_spaces(value)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def _dedupe_preserve_order(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    collected: list[str] = []
    for value in values:
        cleaned = _collapse_spaces(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        collected.append(cleaned)
    return tuple(collected)


def _classify_sigma_text(value: str | None) -> str:
    normalized = _collapse_spaces(value).lower()
    if not normalized:
        return "blank"
    if normalized in {"-", "—"}:
        return "explicit_no"
    if normalized == "нет" or normalized.startswith("нет "):
        return "explicit_no"
    if normalized == "no" or normalized.startswith("no "):
        return "explicit_no"
    if any(
        token in normalized
        for token in (
            "может требоваться",
            "может примен",
            "требуется проверка",
            "возможно",
            "зависит",
            "may be required",
            "depends",
        )
    ):
        return "conditional"
    if normalized in {"да", "есть", "yes"}:
        return "positive"
    if any(ch.isdigit() for ch in normalized):
        return "positive"
    return "conditional"


def normalize_sigma_calc_values(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    cleaned = _dedupe_preserve_order(tuple(str(item) for item in values))
    if not cleaned:
        return ()
    has_positive = any(_classify_sigma_text(value) == "positive" for value in cleaned)
    if has_positive:
        return tuple(value for value in cleaned if _classify_sigma_text(value) != "explicit_no")
    return cleaned


def _clean_detail_text(value: str | None) -> str | None:
    if not value:
        return None
    return " | ".join(_dedupe_preserve_order(tuple(part for part in str(value).split("|")))) or None


def _row_by_id(result: SigmaPaycalcResult, row_id: str) -> SigmaRawRow | None:
    normalized = str(row_id or "").strip().lower()
    for row in result.main_tariff_rows:
        if row.row_id.strip().lower() == normalized:
            return row
    return None


def _format_section_line(*, emoji: str | None, title: str, value: str | None) -> str | None:
    cleaned_value = _collapse_spaces(value)
    if not cleaned_value:
        return None
    prefix = f"{emoji} " if emoji else ""
    return f"{prefix}{title}: {cleaned_value}"


def _split_rate_and_context(value: str | None) -> tuple[str | None, str | None]:
    text = _collapse_spaces(value)
    if not text:
        return None, None
    per_unit_match = re.match(
        r"^(?P<rate>-?\d+(?:[.,]\d+)?\s*(?:руб|евро|eur|usd)\s+за\s+[A-Za-zА-Яа-яЁё0-9.\-/]{1,16})\s*(?P<tail>.*)$",
        text,
        re.IGNORECASE,
    )
    if per_unit_match is not None:
        return _collapse_spaces(per_unit_match.group("rate")), _collapse_spaces(per_unit_match.group("tail")) or None
    percent_match = re.match(r"^(?P<rate>-?\d+(?:[.,]\d+)?\s*%)\s*(?P<tail>.*)$", text)
    if percent_match is not None:
        return _collapse_spaces(percent_match.group("rate")), _collapse_spaces(percent_match.group("tail")) or None
    unit_match = re.match(
        r"^(?P<rate>-?\d+(?:[.,]\d+)?\s*(?:руб|евро|eur|usd)(?:\s*/\s*[A-Za-zА-Яа-яЁё0-9.\-/]+)?)\s*(?P<tail>.*)$",
        text,
        re.IGNORECASE,
    )
    if unit_match is not None:
        return _collapse_spaces(unit_match.group("rate")), _collapse_spaces(unit_match.group("tail")) or None
    return text, None


def _pick_primary_text(*, summary_value: str | None, calc_values: tuple[str, ...], fallback_text: str | None = None) -> str | None:
    normalized_calc_values = normalize_sigma_calc_values(calc_values)
    if normalized_calc_values:
        return normalized_calc_values[0]
    if _collapse_spaces(summary_value):
        return _collapse_spaces(summary_value)
    if _collapse_spaces(fallback_text):
        return _collapse_spaces(fallback_text)
    return None


def _normalize_measure_status_text(value: str | None) -> str | None:
    cleaned = _collapse_spaces(value)
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered == "yes":
        return "есть"
    if lowered == "no":
        return "нет"
    return cleaned


def _build_customs_fee_section(result: SigmaPaycalcResult) -> SigmaPriceSection:
    row = _row_by_id(result, "FixSbr")
    calc_values = normalize_sigma_calc_values(row.values if row is not None and row.values else result.customs_fee.calc_values)
    primary_text = _pick_primary_text(
        summary_value=result.customs_fee.summary_value,
        calc_values=calc_values,
        fallback_text=row.value_text if row is not None else None,
    )
    short_value, sigma_context = _split_rate_and_context(primary_text)
    sigma_text = _clean_detail_text(result.customs_fee.detail_text) or sigma_context or (
        row.label if row is not None else "Фиксированная ставка таможенных сборов"
    )
    is_explicit_no = _classify_sigma_text(primary_text) == "explicit_no"
    return SigmaPriceSection(
        key="customs_fee",
        title="Там. сбор",
        status=result.customs_fee.status,
        emoji=PP1637_CUSTOMS_FEE_EMOJI,
        short_value=short_value or primary_text,
        detail_text=_clean_detail_text(result.customs_fee.detail_text),
        calc_values=calc_values,
        display_line=None if is_explicit_no else _format_section_line(emoji=PP1637_CUSTOMS_FEE_EMOJI, title="Там. сбор", value=short_value or primary_text),
        sigma_line=f"Sigma: {_trim_text(sigma_text)}" if sigma_text and not is_explicit_no else None,
        contributes_to_leading_emoji=result.customs_fee.is_positive,
    )


def _build_excise_section(result: SigmaPaycalcResult) -> SigmaPriceSection:
    row = _row_by_id(result, "Excise")
    calc_values = normalize_sigma_calc_values(row.values if row is not None and row.values else result.excise.calc_values)
    primary_text = _pick_primary_text(
        summary_value=result.excise.summary_value,
        calc_values=calc_values,
        fallback_text=row.value_text if row is not None else None,
    )
    normalized_short = _normalize_measure_status_text((_split_rate_and_context(primary_text)[0]) or primary_text)
    sigma_text = _split_rate_and_context(primary_text)[1] or _clean_detail_text(result.excise.detail_text) or (
        row.label if row is not None else None
    )
    is_explicit_no = _classify_sigma_text(primary_text) == "explicit_no"
    return SigmaPriceSection(
        key="excise",
        title="Акциз",
        status=result.excise.status,
        emoji=SIGMA_EXCISE_EMOJI,
        short_value=normalized_short,
        detail_text=_clean_detail_text(result.excise.detail_text),
        calc_values=calc_values,
        display_line=None if is_explicit_no else _format_section_line(emoji=SIGMA_EXCISE_EMOJI, title="Акциз", value=normalized_short),
        sigma_line=f"Sigma: {_trim_text(sigma_text)}" if sigma_text and not is_explicit_no else None,
        contributes_to_leading_emoji=result.excise.is_positive,
    )


def _protective_rows(result: SigmaPaycalcResult) -> tuple[SigmaRawRow, ...]:
    excluded = {"duty", "excise", "fixsbr", "vat"}
    return tuple(
        row
        for row in result.main_tariff_rows
        if row.row_id.strip().lower() not in excluded and "duty" in row.row_id.strip().lower()
    )


def _build_protective_section(result: SigmaPaycalcResult) -> SigmaPriceSection:
    parts: list[str] = []
    sigma_parts: list[str] = []
    calc_values = normalize_sigma_calc_values(result.protective.calc_values)
    for row in _protective_rows(result):
        row_values = normalize_sigma_calc_values(row.values)
        if not row_values:
            continue
        primary_text = row_values[0]
        short_value, _ = _split_rate_and_context(primary_text)
        if short_value and short_value != primary_text:
            parts.append(f"{row.label} {short_value}")
        else:
            parts.append(f"{row.label}: {primary_text}")
        sigma_parts.append(f"{row.label}: {' | '.join(row_values)}")

    if not parts:
        primary_text = _pick_primary_text(summary_value=result.protective.summary_value, calc_values=calc_values)
        if primary_text and _classify_sigma_text(primary_text) != "explicit_no":
            parts.append(primary_text)
        if result.protective.detail_text:
            sigma_parts.append(_clean_detail_text(result.protective.detail_text) or "")

    summary_text = "; ".join(part for part in parts if part)
    sigma_text = "; ".join(part for part in _dedupe_preserve_order(tuple(sigma_parts)) if part)
    return SigmaPriceSection(
        key="protective",
        title="Доп. меры",
        status=result.protective.status,
        emoji=SIGMA_PROTECTIVE_EMOJI,
        short_value=summary_text or None,
        detail_text=_clean_detail_text(result.protective.detail_text),
        calc_values=calc_values,
        display_line=_format_section_line(emoji=SIGMA_PROTECTIVE_EMOJI, title="Доп. меры", value=summary_text),
        sigma_line=f"Sigma: {_trim_text(sigma_text)}" if sigma_text else None,
        contributes_to_leading_emoji=result.protective.is_positive,
    )


def _build_marking_section(result: SigmaPaycalcResult) -> SigmaPriceSection:
    short_value = _normalize_measure_status_text(result.mandatory_marking.summary_value)
    detail_text = _clean_detail_text(result.mandatory_marking.detail_text)
    return SigmaPriceSection(
        key="mandatory_marking",
        title="Маркировка",
        status=result.mandatory_marking.status,
        emoji=SIGMA_MANDATORY_MARKING_EMOJI,
        short_value=short_value,
        detail_text=detail_text,
        calc_values=(),
        display_line=(
            _format_section_line(emoji=SIGMA_MANDATORY_MARKING_EMOJI, title="Маркировка", value=short_value)
            if result.mandatory_marking.has_attention
            else None
        ),
        sigma_line=f"Sigma: {_trim_text(detail_text)}" if detail_text and result.mandatory_marking.has_attention else None,
        contributes_to_leading_emoji=result.mandatory_marking.has_attention,
    )


def extract_eco_groups(detail_text: str | None) -> tuple[SigmaEcoGroup, ...]:
    text = _clean_detail_text(detail_text)
    if not text:
        return ()
    groups: list[SigmaEcoGroup] = []
    pattern = re.compile(
        r"(?:^|[\s*;|])Группа\s*(?:N|№)?\s*(?P<number>\d+)\s*[\"«](?P<title>.*?)[\"»]\s*(?P<body>.*?)(?=(?:\s*(?:[*;|]\s*)?Группа\s*(?:N|№)?\s*\d+\s*[\"«])|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        groups.append(
            SigmaEcoGroup(
                group_no=_collapse_spaces(match.group("number")) or None,
                group_title=_collapse_spaces(match.group("title")) or None,
                group_text=_collapse_spaces(match.group("body")) or None,
            )
        )
    return tuple(groups)


def _build_eco_section(result: SigmaPaycalcResult) -> SigmaPriceSection:
    short_value = _normalize_measure_status_text(result.eco.summary_value)
    detail_text = _clean_detail_text(result.eco.detail_text)
    groups = extract_eco_groups(detail_text)
    extra_lines: list[str] = []
    if groups:
        primary_group = groups[0]
        if primary_group.group_no and primary_group.group_title:
            extra_lines.append(f"Группа {primary_group.group_no}: {primary_group.group_title}")
    return SigmaPriceSection(
        key="eco",
        title="Эко",
        status=result.eco.status,
        emoji=SIGMA_SECTION_ECO_EMOJI if result.eco.has_attention or detail_text else None,
        short_value=short_value,
        detail_text=detail_text,
        calc_values=(),
        display_line=(
            _format_section_line(emoji=SIGMA_SECTION_ECO_EMOJI, title="Эко", value=short_value)
            if result.eco.has_attention
            else _format_section_line(emoji=None, title="Эко", value=short_value)
        ),
        extra_lines=tuple(extra_lines),
        sigma_line=f"Sigma: {_trim_text(detail_text)}" if detail_text and result.eco.has_attention else None,
        contributes_to_leading_emoji=False,
    )


def build_sigma_price_section(section_key: str, result: SigmaPaycalcResult) -> SigmaPriceSection | None:
    builders = {
        "customs_fee": _build_customs_fee_section,
        "protective": _build_protective_section,
        "excise": _build_excise_section,
        "mandatory_marking": _build_marking_section,
        "eco": _build_eco_section,
    }
    builder = builders.get(str(section_key or "").strip())
    return builder(result) if builder is not None else None


def build_sigma_price_snapshot(result: SigmaPaycalcResult) -> SigmaPriceSnapshot:
    sections = tuple(
        section
        for section in (
            build_sigma_price_section("customs_fee", result),
            build_sigma_price_section("protective", result),
            build_sigma_price_section("excise", result),
            build_sigma_price_section("mandatory_marking", result),
            build_sigma_price_section("eco", result),
        )
        if section is not None and section.is_visible
    )
    leading_emojis = normalize_emoji_flags(
        [section.emoji for section in sections if section.contributes_to_leading_emoji and section.emoji is not None]
    )
    warning_lines = ("Sigma: недоступна, дополнительные меры не проверены",) if result.is_technical_failure else ()
    optional_lines: list[str] = []
    for section in sections:
        optional_lines.extend(section.render_lines())
    is_partial = any(section.status == "conditional" for section in sections) and not result.is_technical_failure
    return SigmaPriceSnapshot(
        code=result.code,
        source_url=result.source_url,
        query_date=result.query_date,
        item_name=result.item_name,
        sections=sections,
        leading_emojis=tuple(leading_emojis),
        optional_lines=tuple(optional_lines),
        warning_lines=warning_lines,
        is_partial=is_partial,
        is_technical_failure=result.is_technical_failure,
    )


def render_sigma_price_lines(snapshot: SigmaPriceSnapshot, *, blank_line_between_sections: bool = False) -> tuple[str, ...]:
    if not snapshot.sections and not snapshot.warning_lines:
        return ()
    lines: list[str] = []
    for index, section in enumerate(snapshot.sections):
        if blank_line_between_sections and index > 0:
            lines.append("")
        lines.extend(section.render_lines())
    lines.extend(snapshot.warning_lines)
    return tuple(lines)


__all__ = [
    "SigmaEcoGroup",
    "SigmaPriceSection",
    "SigmaPriceSnapshot",
    "build_sigma_price_section",
    "build_sigma_price_snapshot",
    "extract_eco_groups",
    "normalize_sigma_calc_values",
    "render_sigma_price_lines",
]
