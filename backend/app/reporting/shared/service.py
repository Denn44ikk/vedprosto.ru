from __future__ import annotations

from typing import Any


def _text(value: object) -> str:
    return str(value or "").strip()


def _query_key(query_text: object, group_filter: object) -> str:
    return f"{_text(query_text)}|{_text(group_filter)}"


def _query_hits_count(*, code: str, query_items: list[dict[str, Any]]) -> int:
    if not code:
        return 0
    hits = 0
    for query in query_items:
        groups = query.get("groups") if isinstance(query.get("groups"), list) else []
        focused = query.get("focused") if isinstance(query.get("focused"), list) else []
        matched = any(_text(item.get("code")) == code for item in groups if isinstance(item, dict))
        if not matched:
            for row in focused:
                if not isinstance(row, dict):
                    continue
                codes = row.get("codes") if isinstance(row.get("codes"), list) else []
                if any(_text(item.get("code")) == code for item in codes if isinstance(item, dict)):
                    matched = True
                    break
        if matched:
            hits += 1
    return hits


def _build_inline_code_summary(
    *,
    code: str,
    item: dict[str, Any] | None,
    verify_summary: str,
    query_items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    normalized_code = _text(code)
    if not normalized_code:
        return None
    row = item if isinstance(item, dict) else {}
    records = int(row.get("records") or 0)
    share_percent = int(row.get("share_percent") or 0)
    support_level = _text(row.get("support_level")) or "no_signal"
    signal_type = _text(row.get("signal_type"))
    query_hits = _query_hits_count(code=normalized_code, query_items=query_items)
    short_line_parts = [normalized_code]
    if records > 0:
        short_line_parts.append(f"{records} декл.")
    if share_percent > 0:
        short_line_parts.append(f"{share_percent}%")
    if query_hits > 0:
        short_line_parts.append(f"{query_hits} запросов")
    if support_level:
        short_line_parts.append(support_level)
    return {
        "code": normalized_code,
        "records": records,
        "share_percent": share_percent,
        "support_level": support_level,
        "signal_type": signal_type,
        "query_hits": query_hits,
        "short_line": "IFCG: " + " / ".join(short_line_parts[1:]) if len(short_line_parts) > 1 else f"IFCG: {normalized_code}",
        "verify_line": verify_summary if verify_summary and normalized_code == _text(code) else "",
    }


def build_ifcg_panel(
    *,
    ifcg_discovery: dict[str, Any] | None,
    ifcg_verification: dict[str, Any] | None,
    its_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    discovery = ifcg_discovery if isinstance(ifcg_discovery, dict) else {}
    verification = ifcg_verification if isinstance(ifcg_verification, dict) else {}
    its = its_payload if isinstance(its_payload, dict) else {}
    source = verification if verification else discovery
    if not source:
        return None

    trace = source.get("trace") if isinstance(source.get("trace"), dict) else {}
    query_map = trace.get("query_map") if isinstance(trace.get("query_map"), list) else []
    search_statuses = trace.get("search_statuses") if isinstance(trace.get("search_statuses"), list) else []
    status_rows: dict[str, dict[str, Any]] = {}
    focused_rows: dict[str, list[dict[str, Any]]] = {}
    for row in search_statuses:
        if not isinstance(row, dict):
            continue
        key = _query_key(row.get("query"), row.get("group_filter"))
        status_rows[key] = row
        if _text(row.get("group_filter")):
            focused_rows.setdefault(_text(row.get("query")), []).append(row)

    query_items: list[dict[str, Any]] = []
    for index, row in enumerate(query_map, start=1):
        if not isinstance(row, dict):
            continue
        query_text = _text(row.get("query"))
        if not query_text:
            continue
        broad_status = status_rows.get(_query_key(query_text, ""))
        groups = []
        raw_groups = row.get("groups") if isinstance(row.get("groups"), list) else []
        for item in raw_groups[:6]:
            if not isinstance(item, dict):
                continue
            code = _text(item.get("code"))
            if not code:
                continue
            groups.append(
                {
                    "code": code,
                    "record_count": int(item.get("record_count") or 0),
                    "share_percent": int(item.get("share_percent") or 0),
                }
            )
        focused = []
        for focused_row in focused_rows.get(query_text, [])[:3]:
            sections = focused_row.get("stat_sections") if isinstance(focused_row.get("stat_sections"), list) else []
            codes = []
            for section in sections[:3]:
                if not isinstance(section, dict):
                    continue
                code = _text(section.get("code"))
                if not code:
                    continue
                codes.append(
                    {
                        "code": code,
                        "record_count": int(section.get("record_count") or 0),
                        "share_percent": int(section.get("share_percent") or 0),
                    }
                )
            if codes:
                focused.append(
                    {
                        "group_filter": _text(focused_row.get("group_filter")),
                        "codes": codes,
                    }
                )
        query_items.append(
            {
                "index": index,
                "text": query_text,
                "url": _text((broad_status or {}).get("url")),
                "groups": groups,
                "focused": focused,
            }
        )

    its_by_code = its.get("by_code") if isinstance(its.get("by_code"), dict) else {}
    top_codes: list[dict[str, Any]] = []
    top_code_map: dict[str, dict[str, Any]] = {}
    raw_top_codes = source.get("top_codes") if isinstance(source.get("top_codes"), list) else []
    for item in raw_top_codes[:5]:
        if not isinstance(item, dict):
            continue
        code = _text(item.get("code"))
        if not code:
            continue
        its_row = its_by_code.get(code) if isinstance(its_by_code.get(code), dict) else {}
        summary_row = {
            "code": code,
            "support_level": _text(item.get("support_level")),
            "signal_type": _text(item.get("signal_type")),
            "records": int(item.get("clarification_records") or 0),
            "share_percent": int(item.get("clarification_share_percent") or 0),
            "why": _text(item.get("why")),
            "its_value": its_row.get("its_value"),
            "its_status": _text(its_row.get("status")),
            "its_date_text": _text(its_row.get("date_text")),
        }
        top_codes.append(summary_row)
        top_code_map[code] = summary_row

    selected_code = _text(verification.get("selected_code"))
    verify_summary = _text(verification.get("summary") or verification.get("operator_short_line"))
    selected_summary = _build_inline_code_summary(
        code=selected_code,
        item=top_code_map.get(selected_code),
        verify_summary=verify_summary,
        query_items=query_items,
    )
    candidate_summaries = []
    for item in top_codes:
        code = _text(item.get("code"))
        if code == selected_code:
            continue
        inline_summary = _build_inline_code_summary(
            code=code,
            item=item,
            verify_summary="",
            query_items=query_items,
        )
        if inline_summary is not None:
            candidate_summaries.append(inline_summary)

    strongest_code = ""
    if top_codes:
        strongest_code = _text(top_codes[0].get("code"))

    return {
        "status": _text(source.get("status")),
        "summary": _text(source.get("summary") or source.get("operator_short_line")),
        "verify_summary": verify_summary,
        "selected_code": selected_code,
        "selected_summary": selected_summary,
        "candidate_summaries": candidate_summaries,
        "review_headline": verify_summary or _text(source.get("summary") or source.get("operator_short_line")),
        "strongest_code": strongest_code,
        "query_count": len(query_items),
        "queries": query_items,
        "top_codes": top_codes,
        "hidden_queries": max(0, len(query_items) - min(len(query_items), 5)),
        "rerun_recommended": bool(verification.get("rerun_recommended")),
        "dangerous_signal": bool(verification.get("dangerous_signal")),
    }


__all__ = ["build_ifcg_panel"]
