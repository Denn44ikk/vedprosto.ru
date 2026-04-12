from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlencode

from .models import SigmaMeasureState, SigmaPaycalcResult, SigmaRawRow
from .utils import normalize_code_10

SIGMA_PAYCALC_BASE_URL = "https://www.sigma-soft.ru/service/spravka/spravka.shtml"


def build_sigma_paycalc_url(*, code: str, query_date: str) -> str:
    normalized_code = normalize_code_10(code)
    params = {
        "WAA_PACKAGE": "PayCalc",
        "WAA_FORM": "PayCalc",
        "SDATE": str(query_date or "").strip(),
        "SCODE": normalized_code,
    }
    return f"{SIGMA_PAYCALC_BASE_URL}?{urlencode(params)}"


def decode_sigma_html(raw_bytes: bytes) -> str:
    if not raw_bytes:
        return ""
    for encoding in ("cp1251", "windows-1251", "utf-8"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("cp1251", errors="replace")


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _trim_text(value: str, *, max_len: int = 2200) -> str:
    cleaned = _collapse_spaces(value)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "p", "tr"}:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return _collapse_spaces(" ".join(self._parts))


class _ElementInnerHtmlByIdExtractor(HTMLParser):
    def __init__(self, *, tag_name: str, element_id: str) -> None:
        super().__init__()
        self._tag_name = str(tag_name or "").strip().lower()
        self._element_id = str(element_id or "").strip()
        self._capturing = False
        self._depth = 0
        self._parts: list[str] = []
        self.result: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attrs_dict = {str(name).lower(): str(value or "") for name, value in attrs}
        if not self._capturing and normalized_tag == self._tag_name and attrs_dict.get("id") == self._element_id:
            self._capturing = True
            self._depth = 1
            self._parts = []
            return
        if self._capturing:
            if normalized_tag == self._tag_name:
                self._depth += 1
            self._parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capturing:
            self._parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if not self._capturing:
            return
        normalized_tag = tag.lower()
        if normalized_tag == self._tag_name:
            self._depth -= 1
            if self._depth == 0:
                self.result = "".join(self._parts)
                self._capturing = False
                return
        self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_comment(self, data: str) -> None:
        if self._capturing:
            self._parts.append(f"<!--{data}-->")


class _FirstLevelTdExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_attrs: dict[str, str] | None = None
        self._current_parts: list[str] = []
        self._td_depth = 0
        self.cells: list[tuple[dict[str, str], str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "td":
            if self._current_attrs is None:
                self._current_attrs = {str(name).lower(): str(value or "") for name, value in attrs}
                self._current_parts = []
                self._td_depth = 1
                return
            self._td_depth += 1
        if self._current_attrs is not None:
            self._current_parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._current_attrs is not None:
            self._current_parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if self._current_attrs is None:
            return
        normalized_tag = tag.lower()
        if normalized_tag == "td":
            if self._td_depth == 1:
                self.cells.append((self._current_attrs, "".join(self._current_parts)))
                self._current_attrs = None
                self._current_parts = []
                self._td_depth = 0
                return
            self._td_depth -= 1
        self._current_parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._current_attrs is not None:
            self._current_parts.append(data)

    def handle_comment(self, data: str) -> None:
        if self._current_attrs is not None:
            self._current_parts.append(f"<!--{data}-->")


def _strip_html(value: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(html.unescape(value or ""))
    parser.close()
    return parser.get_text()


def _extract_tag_by_id(html_text: str, *, tag_name: str, element_id: str) -> str | None:
    parser = _ElementInnerHtmlByIdExtractor(tag_name=tag_name, element_id=element_id)
    parser.feed(html_text or "")
    parser.close()
    return parser.result


def _extract_td_by_class(row_html: str, class_name: str) -> str | None:
    parser = _FirstLevelTdExtractor()
    parser.feed(row_html or "")
    parser.close()
    target_class = str(class_name or "").strip().lower()
    for attrs, inner_html in parser.cells:
        classes = {part.strip().lower() for part in str(attrs.get("class") or "").split() if part.strip()}
        if target_class in classes:
            return inner_html
    return None


def _parse_html_attrs(attrs_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for name, _, value in re.findall(r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", attrs_text or "", re.DOTALL):
        attrs[str(name).lower()] = html.unescape(str(value))
    return attrs


def _extract_input_blocks(block_html: str) -> tuple[tuple[dict[str, str], str, str], ...]:
    items: list[tuple[dict[str, str], str, str]] = []
    for attrs_text, inner_html in re.findall(r"<input\b([^>]*)>(.*?)</input>", block_html, re.IGNORECASE | re.DOTALL):
        items.append((_parse_html_attrs(attrs_text), attrs_text, inner_html))
    return tuple(items)


def _extract_input_texts(block_html: str) -> tuple[str, ...]:
    values: list[str] = []
    for attrs, attrs_text, inner_html in _extract_input_blocks(block_html):
        lowered_attrs = str(attrs_text or "").lower()
        hidden_attr = "hidden" in lowered_attrs
        hidden_class = "taxhidden" in str(attrs.get("class") or "").lower()
        hidden_type = str(attrs.get("type") or "").lower() == "hidden"
        if hidden_attr or hidden_class or hidden_type:
            continue
        display_text = _collapse_spaces(_strip_html(inner_html))
        if not display_text:
            display_text = _collapse_spaces(_strip_html(str(attrs.get("value") or "")))
        if display_text:
            values.append(display_text)
    normalized_values = tuple(value for value in values if value)
    if normalized_values:
        return normalized_values
    fallback = _collapse_spaces(_strip_html(block_html))
    return (fallback,) if fallback else ()


def _classify_value(text: str | None) -> str:
    normalized = _collapse_spaces(str(text or "")).lower()
    if not normalized:
        return "blank"
    if normalized == "нет" or normalized.startswith("нет "):
        return "explicit_no"
    if normalized in {"-", "—"}:
        return "explicit_no"
    if any(token in normalized for token in ("может требоваться", "может примен", "возможно", "зависит")):
        return "conditional"
    if normalized in {"да", "есть"}:
        return "positive"
    if any(ch.isdigit() for ch in normalized):
        return "positive"
    return "conditional"


def _merge_statuses(statuses: list[str]) -> str:
    normalized = [status for status in statuses if status and status != "blank"]
    if not normalized:
        return "blank"
    if "positive" in normalized:
        return "positive"
    if "conditional" in normalized:
        return "conditional"
    if "explicit_no" in normalized:
        return "explicit_no"
    return normalized[0]


def _build_state(
    *,
    summary_items: list[tuple[str, str, str]],
    calc_items: list[tuple[str, tuple[str, ...]]],
) -> SigmaMeasureState:
    summary_values = [value for _, value, _ in summary_items if value]
    detail_parts: list[str] = []
    calc_values: list[str] = []
    source_ids: list[str] = []
    statuses: list[str] = []

    for row_id, summary_value, detail_text in summary_items:
        source_ids.append(row_id)
        statuses.append(_classify_value(summary_value))
        if detail_text:
            detail_parts.append(detail_text)

    for block_id, values in calc_items:
        source_ids.append(block_id)
        calc_values.extend(values)
        statuses.extend(_classify_value(value) for value in values)

    unique_detail_parts: list[str] = []
    seen_detail_parts: set[str] = set()
    for part in detail_parts:
        normalized_part = _collapse_spaces(part)
        if not normalized_part or normalized_part in seen_detail_parts:
            continue
        seen_detail_parts.add(normalized_part)
        unique_detail_parts.append(part)

    summary_value = " | ".join(summary_values) if summary_values else None
    detail_text = " | ".join(_trim_text(part) for part in unique_detail_parts)
    return SigmaMeasureState(
        status=_merge_statuses(statuses),
        summary_value=summary_value,
        detail_text=detail_text or None,
        calc_values=tuple(value for value in calc_values if value),
        source_ids=tuple(source_ids),
    )


def _extract_summary_row(html_text: str, row_id: str) -> tuple[str, str, str] | None:
    row_html = _extract_tag_by_id(html_text, tag_name="tr", element_id=row_id)
    if row_html is None:
        return None
    value_html = _extract_td_by_class(row_html, "ColumnStavka") or ""
    detail_html = _extract_td_by_class(row_html, "ColumnDoc") or ""
    return (row_id, _collapse_spaces(_strip_html(value_html)), _trim_text(_strip_html(detail_html)))


def _extract_calc_block(html_text: str, block_id: str) -> tuple[str, tuple[str, ...]] | None:
    block_html = _extract_tag_by_id(html_text, tag_name="td", element_id=block_id)
    if block_html is None:
        return None
    return (block_id, _extract_input_texts(block_html))


def _extract_item_name(html_text: str) -> str | None:
    match = re.search(
        r"<tr[^>]*>\s*<td[^>]*>\s*\d[\d\s]+\s*</td>\s*<td[^>]*>(.*?)</td>\s*</tr>",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return None
    item_name = _collapse_spaces(_strip_html(match.group(1)))
    return item_name or None


def _extract_main_tariff_rows(html_text: str) -> tuple[SigmaRawRow, ...]:
    table_html = _extract_tag_by_id(html_text, tag_name="table", element_id="TableMainTariffIM")
    if table_html is None:
        return ()
    rows: list[SigmaRawRow] = []
    for row_attrs_text, row_html in re.findall(r"<tr\b([^>]*)>(.*?)</tr>", table_html, re.IGNORECASE | re.DOTALL):
        row_attrs = _parse_html_attrs(row_attrs_text)
        row_id = str(row_attrs.get("id") or "").strip()
        if not row_id:
            continue

        cells = re.findall(r"<td\b([^>]*)>(.*?)</td>", row_html, re.IGNORECASE | re.DOTALL)
        if not cells:
            continue

        label = _collapse_spaces(_strip_html(cells[0][1])) or None
        value_attrs_text = cells[-1][0]
        value_html = cells[-1][1]
        for candidate_attrs_text, candidate_html in cells[1:]:
            candidate_attrs = _parse_html_attrs(candidate_attrs_text)
            candidate_class = str(candidate_attrs.get("class") or "").lower()
            if candidate_attrs.get("id") or "columntovar" in candidate_class or "columnstavka" in candidate_class:
                value_attrs_text = candidate_attrs_text
                value_html = candidate_html
                break

        value_attrs = _parse_html_attrs(value_attrs_text)
        values = tuple(_trim_text(value) for value in _extract_input_texts(value_html) if value)
        rows.append(
            SigmaRawRow(
                row_id=row_id,
                label=label,
                cell_id=str(value_attrs.get("id") or "").strip() or None,
                values=values,
            )
        )
    return tuple(rows)


def _extract_main_tariff_value(rows: tuple[SigmaRawRow, ...], row_id: str) -> str | None:
    normalized_row_id = str(row_id or "").strip().lower()
    for row in rows:
        if row.row_id.strip().lower() == normalized_row_id:
            for value in row.values:
                cleaned = _collapse_spaces(value)
                if cleaned:
                    return cleaned
            return row.value_text
    return None


def parse_sigma_paycalc_html(
    html_text: str,
    *,
    code: str,
    query_date: str,
    source_url: str | None = None,
) -> SigmaPaycalcResult:
    normalized_code = normalize_code_10(code)
    url = source_url or build_sigma_paycalc_url(code=normalized_code, query_date=query_date)
    if not html_text.strip():
        return SigmaPaycalcResult(
            code=normalized_code,
            query_date=query_date,
            status="blank",
            source_url=url,
            error_text="Пустой ответ Sigma Soft",
        )

    customs_fee = _build_state(
        summary_items=[item for item in [_extract_summary_row(html_text, "t_fixsbr")] if item is not None],
        calc_items=[item for item in [_extract_calc_block(html_text, "RateFixSbr")] if item is not None],
    )
    protective = _build_state(
        summary_items=[
            item
            for item in (
                _extract_summary_row(html_text, "t_sposh"),
                _extract_summary_row(html_text, "t_aposh"),
                _extract_summary_row(html_text, "t_taposh"),
                _extract_summary_row(html_text, "t_cposh"),
            )
            if item is not None
        ],
        calc_items=[
            item
            for item in (
                _extract_calc_block(html_text, "RateAntidumpingDuty"),
                _extract_calc_block(html_text, "RateTmpAntidumpingDuty"),
            )
            if item is not None
        ],
    )
    excise = _build_state(
        summary_items=[item for item in [_extract_summary_row(html_text, "t_iakz")] if item is not None],
        calc_items=[item for item in [_extract_calc_block(html_text, "RateExcise")] if item is not None],
    )
    mandatory_marking = _build_state(
        summary_items=[item for item in [_extract_summary_row(html_text, "t_idm")] if item is not None],
        calc_items=[],
    )
    eco = _build_state(
        summary_items=[item for item in [_extract_summary_row(html_text, "t_ecosbr")] if item is not None],
        calc_items=[],
    )
    main_tariff_rows = _extract_main_tariff_rows(html_text)
    duty_text = _extract_main_tariff_value(main_tariff_rows, "Duty")
    vat_text = _extract_main_tariff_value(main_tariff_rows, "VAT")
    item_name = _extract_item_name(html_text)
    known_sections = (
        customs_fee.source_ids
        or protective.source_ids
        or excise.source_ids
        or mandatory_marking.source_ids
        or eco.source_ids
        or main_tariff_rows
    )
    status = "ok" if known_sections else "blank"

    return SigmaPaycalcResult(
        code=normalized_code,
        query_date=query_date,
        status=status,
        source_url=url,
        item_name=item_name,
        duty_text=duty_text,
        vat_text=vat_text,
        customs_fee=customs_fee,
        protective=protective,
        excise=excise,
        mandatory_marking=mandatory_marking,
        eco=eco,
        main_tariff_rows=main_tariff_rows,
        error_text=None if status == "ok" else "Sigma Soft не вернула ожидаемые секции",
    )


def parse_sigma_paycalc_bytes(
    raw_bytes: bytes,
    *,
    code: str,
    query_date: str,
    source_url: str | None = None,
) -> SigmaPaycalcResult:
    return parse_sigma_paycalc_html(
        decode_sigma_html(raw_bytes),
        code=code,
        query_date=query_date,
        source_url=source_url,
    )


__all__ = [
    "SIGMA_PAYCALC_BASE_URL",
    "build_sigma_paycalc_url",
    "decode_sigma_html",
    "parse_sigma_paycalc_bytes",
    "parse_sigma_paycalc_html",
]
