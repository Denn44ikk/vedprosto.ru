from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from .models import (
    IfcgClarificationBucket,
    IfcgDeclarationExample,
    IfcgQuery,
    IfcgSearchResult,
    IfcgSectionHit,
    IfcgStatSection,
    IfcgTreeHit,
)


_ROW_CLASSES = {"row", "row-in", "mt10"}
_SHOW_ALL_RE = re.compile(r"показать\s+все\s+записи", re.IGNORECASE)


def _collapse_spaces(value: str) -> str:
    return " ".join((value or "").split())


def _normalize_code(value: str, *, min_len: int = 4, max_len: int = 10) -> str:
    digits = re.sub(r"\D", "", value or "")
    if min_len <= len(digits) <= max_len:
        return digits
    return ""


def _scope_for_code(code: str) -> str:
    if len(code) == 10:
        return "code"
    if len(code) == 4:
        return "group"
    return "other"


def _find_heading(soup: BeautifulSoup, *, heading_id: str, heading_text: str) -> Tag | None:
    heading = soup.find(id=heading_id)
    if isinstance(heading, Tag):
        return heading
    return soup.find(
        lambda tag: isinstance(tag, Tag)
        and tag.name in {"h2", "h3", "h4"}
        and heading_text in tag.get_text(" ", strip=True)
    )


def _row_matches(tag: Tag) -> bool:
    classes = set(tag.get("class", []))
    return tag.name == "div" and _ROW_CLASSES.issubset(classes)


def _collect_rows(heading: Tag | None) -> list[Tag]:
    if heading is None:
        return []
    rows: list[Tag] = []
    seen_nodes: set[int] = set()
    node = heading.next_sibling
    while node is not None:
        if isinstance(node, Tag):
            if node.name == "h2" and node is not heading:
                break
            if _row_matches(node):
                marker = id(node)
                if marker not in seen_nodes:
                    seen_nodes.add(marker)
                    rows.append(node)
        node = node.next_sibling
    return rows


def _extract_row_code_and_text(row: Tag) -> tuple[str, str, str]:
    link = row.find("a", href=re.compile(r"/kb/tnved/\d+/"))
    href = str(link.get("href") or "") if link is not None else ""
    code = ""
    if link is not None:
        code = _normalize_code(link.get_text(" ", strip=True))
        if not code:
            code = _normalize_code(href)
    columns = row.find_all("div", recursive=False)
    if not columns:
        text = _collapse_spaces(row.get_text(" ", strip=True))
        return code, text, href
    if len(columns) == 1:
        text = _collapse_spaces(columns[0].get_text(" ", strip=True))
    else:
        text = _collapse_spaces(columns[-1].get_text(" ", strip=True))
    return code, text, href


def _extract_share_percent(block: Tag) -> int:
    progress = block.select_one(".clarification--progress > div")
    if progress is None:
        return 0
    style = str(progress.get("style") or "")
    match = re.search(r"width\s*:\s*(\d+)", style)
    if match is None:
        return 0
    return max(0, min(int(match.group(1)), 100))


def _extract_clarifications(soup: BeautifulSoup) -> tuple[IfcgClarificationBucket, ...]:
    clarifications: list[IfcgClarificationBucket] = []
    seen: set[tuple[str, int, int, str]] = set()
    for block in soup.select(".clarification"):
        title = block.select_one(".clarification--title")
        if title is None:
            continue
        title_text = _collapse_spaces(title.get_text(" ", strip=True))
        raw_code_text = ""
        font_md = title.select_one(".font-md")
        if font_md is not None:
            raw_code_text = _collapse_spaces(font_md.get_text(" ", strip=True).split("—", 1)[0])
        if not raw_code_text:
            raw_code_text = _collapse_spaces(title_text.split("—", 1)[0])
        code = _normalize_code(raw_code_text)
        if not code:
            continue

        link = title.find("a", href=True)
        records_text = link.get_text(" ", strip=True) if link is not None else title_text
        records_digits = re.sub(r"\D", "", records_text or "")
        if not records_digits:
            continue
        record_count = int(records_digits)
        share_percent = _extract_share_percent(block)
        anchor = str(link.get("href") or "") if link is not None else ""

        marker = (code, record_count, share_percent, anchor)
        if marker in seen:
            continue
        seen.add(marker)
        clarifications.append(
            IfcgClarificationBucket(
                code=code,
                record_count=record_count,
                share_percent=share_percent,
                scope=_scope_for_code(code),
                anchor=anchor,
                title=title_text,
            )
        )
    return tuple(clarifications)


def _extract_tree_hits(soup: BeautifulSoup) -> tuple[IfcgTreeHit, ...]:
    hits: list[IfcgTreeHit] = []
    seen: set[tuple[str, str]] = set()
    for row in _collect_rows(_find_heading(soup, heading_id="result--tree", heading_text="ТН ВЭД ЕАЭС")):
        code, description, href = _extract_row_code_and_text(row)
        if not code or not description:
            continue
        marker = (code, description)
        if marker in seen:
            continue
        seen.add(marker)
        hits.append(
            IfcgTreeHit(
                code=code,
                description=description[:500],
                code_level=len(code),
                href=href,
            )
        )
    return tuple(hits)


def _extract_section_hits(soup: BeautifulSoup, *, heading_id: str, heading_text: str) -> tuple[IfcgSectionHit, ...]:
    hits: list[IfcgSectionHit] = []
    seen: set[tuple[str, str]] = set()
    for row in _collect_rows(_find_heading(soup, heading_id=heading_id, heading_text=heading_text)):
        code, description, href = _extract_row_code_and_text(row)
        if not description or _SHOW_ALL_RE.search(description):
            continue
        marker = (code, description)
        if marker in seen:
            continue
        seen.add(marker)
        hits.append(
            IfcgSectionHit(
                code=code,
                description=description[:700],
                code_level=len(code),
                href=href,
            )
        )
    return tuple(hits)


def _clarification_maps(
    clarifications: tuple[IfcgClarificationBucket, ...],
) -> tuple[dict[str, IfcgClarificationBucket], dict[str, IfcgClarificationBucket]]:
    by_anchor: dict[str, IfcgClarificationBucket] = {}
    by_code: dict[str, IfcgClarificationBucket] = {}
    for bucket in clarifications:
        if bucket.anchor:
            by_anchor[bucket.anchor] = bucket
        if bucket.code:
            previous = by_code.get(bucket.code)
            if previous is None or (bucket.share_percent, bucket.record_count) > (
                previous.share_percent,
                previous.record_count,
            ):
                by_code[bucket.code] = bucket
    return by_anchor, by_code


def _parse_stat_section_start(
    node: Tag,
    *,
    clarifications_by_anchor: dict[str, IfcgClarificationBucket],
    clarifications_by_code: dict[str, IfcgClarificationBucket],
) -> dict[str, object] | None:
    code = ""
    anchor = ""
    title = _collapse_spaces(node.get_text(" ", strip=True))

    if node.name == "h3":
        raw_id = str(node.get("id") or "")
        if raw_id.startswith("result--stat-g-"):
            code = _normalize_code(raw_id.removeprefix("result--stat-g-"))
            anchor = f"#{raw_id}"
    elif node.name == "div" and "ui-folder" in set(node.get("class", [])):
        code = _normalize_code(title)
        if code:
            anchor = f"#result--stat-g-{code}"
    if not code:
        return None

    bucket = clarifications_by_anchor.get(anchor) or clarifications_by_code.get(code)
    return {
        "anchor": anchor,
        "title": title,
        "code": code,
        "scope": _scope_for_code(code),
        "description": "",
        "record_count": bucket.record_count if bucket is not None else 0,
        "share_percent": bucket.share_percent if bucket is not None else 0,
        "examples": [],
    }


def _parse_stat_sections(
    soup: BeautifulSoup,
    *,
    query: IfcgQuery,
    source_url: str,
    clarifications: tuple[IfcgClarificationBucket, ...],
) -> tuple[IfcgStatSection, ...]:
    heading = _find_heading(soup, heading_id="result--stat", heading_text="Статистика декларирования")
    if heading is None:
        return ()

    clarifications_by_anchor, clarifications_by_code = _clarification_maps(clarifications)
    sections: list[IfcgStatSection] = []
    current: dict[str, object] | None = None
    node = heading.next_sibling
    while node is not None:
        if isinstance(node, Tag):
            if node.name == "h2":
                break
            started = _parse_stat_section_start(
                node,
                clarifications_by_anchor=clarifications_by_anchor,
                clarifications_by_code=clarifications_by_code,
            )
            if started is not None:
                if current is not None:
                    sections.append(
                        IfcgStatSection(
                            anchor=str(current["anchor"]),
                            title=str(current["title"]),
                            code=str(current["code"]),
                            scope=str(current["scope"]),
                            description=str(current["description"]),
                            record_count=int(current["record_count"]),
                            share_percent=int(current["share_percent"]),
                            examples=tuple(current["examples"]),
                        )
                    )
                current = started
                node = node.next_sibling
                continue

            if current is not None and _row_matches(node):
                code, description, _href = _extract_row_code_and_text(node)
                if description and not _SHOW_ALL_RE.search(description):
                    if not current["description"]:
                        current["description"] = description[:700]
                    normalized_code = _normalize_code(code, min_len=4, max_len=10)
                    if normalized_code:
                        current["examples"].append(
                            IfcgDeclarationExample(
                                code=normalized_code,
                                description=description[:500],
                                query_text=query.text,
                                group_filter=query.group_filter,
                                source_url=source_url,
                                section_code=str(current["code"]),
                                section_scope=str(current["scope"]),
                                section_title=str(current["title"]),
                            )
                        )
        node = node.next_sibling

    if current is not None:
        sections.append(
            IfcgStatSection(
                anchor=str(current["anchor"]),
                title=str(current["title"]),
                code=str(current["code"]),
                scope=str(current["scope"]),
                description=str(current["description"]),
                record_count=int(current["record_count"]),
                share_percent=int(current["share_percent"]),
                examples=tuple(current["examples"]),
            )
        )
    return tuple(sections)


def _collect_declaration_examples(stat_sections: tuple[IfcgStatSection, ...]) -> tuple[IfcgDeclarationExample, ...]:
    seen: set[tuple[str, str, str]] = set()
    rows: list[IfcgDeclarationExample] = []
    for section in stat_sections:
        for example in section.examples:
            marker = (section.code, example.code, example.description)
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(example)
    return tuple(rows)


def parse_search_page(
    *,
    html_text: str,
    query: IfcgQuery,
    source_url: str,
    http_status: int,
) -> IfcgSearchResult:
    if not html_text.strip():
        return IfcgSearchResult(
            query=query,
            url=source_url,
            status="empty",
            http_status=http_status,
            error="empty_response",
        )

    soup = BeautifulSoup(html_text, "html.parser")
    clarifications = _extract_clarifications(soup)
    stat_sections = _parse_stat_sections(
        soup,
        query=query,
        source_url=source_url,
        clarifications=clarifications,
    )
    tree_hits = _extract_tree_hits(soup)
    note_hits = _extract_section_hits(soup, heading_id="result--notes", heading_text="Пояснения к ТН ВЭД")
    predecision_hits = _extract_section_hits(
        soup,
        heading_id="result--preliminary",
        heading_text="Предварительные решения по классификации",
    )
    declaration_examples = _collect_declaration_examples(stat_sections)
    status = "ok"
    if http_status >= 400:
        status = "http_error"
    elif not (tree_hits or note_hits or predecision_hits or clarifications or stat_sections):
        status = "no_hits"
    return IfcgSearchResult(
        query=query,
        url=source_url,
        status=status,
        http_status=http_status,
        tree_hits=tree_hits,
        note_hits=note_hits,
        predecision_hits=predecision_hits,
        stat_sections=stat_sections,
        declaration_examples=declaration_examples,
        clarifications=clarifications,
        error="" if status != "http_error" else f"http_status={http_status}",
    )
