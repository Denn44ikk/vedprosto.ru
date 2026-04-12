from __future__ import annotations

import re

from .models import IfcgQuery


_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


def collapse_spaces(value: str) -> str:
    return _SPACE_RE.sub(" ", value or "").strip()


def sanitize_ifcg_text(value: str) -> str:
    text = _URL_RE.sub(" ", value or "")
    text = re.sub(r"[`*_#<>|]+", " ", text)
    text = re.sub(r"[\[\]{}()\"'«»“”]", " ", text)
    text = re.sub(r"[,:;!?/\\]+", " ", text)
    return collapse_spaces(text)


def normalize_group_filter(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if 4 <= len(digits) <= 10:
        return digits
    return ""


def build_focused_queries(
    *,
    base_query: str,
    focus_codes: list[str],
    max_queries: int = 4,
) -> list[IfcgQuery]:
    queries: list[IfcgQuery] = []
    seen: set[str] = set()
    clean_query = sanitize_ifcg_text(base_query)[:160] or "товар"
    for code in focus_codes:
        normalized = normalize_group_filter(code)
        if not normalized:
            continue
        query = IfcgQuery(
            text=clean_query,
            group_filter=normalized,
            kind="focused",
            label=f"focus_{normalized}",
            stat_mode=True,
            source="system",
        )
        if query.cache_key in seen:
            continue
        seen.add(query.cache_key)
        queries.append(query)
        if len(queries) >= max(1, max_queries):
            break
    return queries
