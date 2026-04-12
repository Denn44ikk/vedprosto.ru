from __future__ import annotations

import re


RE_PRICE_WITH_PAREN = re.compile(
    r"цена\s*[-–—]?\s*([0-9]+(?:[.,][0-9]+)?)\s*\(\s*([0-9]+(?:[.,][0-9]+)?)\s*\)",
    re.I,
)
RE_PRICE = re.compile(r"цена\s*[-–—]?\s*([0-9]+(?:[.,][0-9]+)?)", re.I)
RE_DATE = re.compile(
    r"дата\s*окончания\s*срока\s*действия\s*[-–—]?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
    re.I,
)
RE_NEED_14 = re.compile(r"необходимо\s*14-?ть\s*знаков", re.I)
RE_NO_PRICE = re.compile(
    r"(?:цена\s+отсутствует|цена\s+отсутстввует).*отправьте\s+запрос\s+на\s+почту",
    re.I,
)
RE_CODE_TOKEN = re.compile(r"(?<!\d)(?:\d[\s-]?){10,14}(?!\d)")


def parse_reply(text: str) -> dict[str, object]:
    raw_text = text or ""
    base: dict[str, object] = {
        "raw": raw_text,
        "variant": None,
        "its": None,
        "its_scob": None,
        "date": None,
    }
    if RE_NEED_14.search(raw_text):
        match = RE_DATE.search(raw_text)
        return {
            **base,
            "variant": 3,
            "date": match.group(1) if match else None,
        }
    if RE_NO_PRICE.search(raw_text):
        return {
            **base,
            "variant": 4,
        }
    with_paren = RE_PRICE_WITH_PAREN.search(raw_text)
    if with_paren:
        match = RE_DATE.search(raw_text)
        return {
            **base,
            "variant": 2,
            "its": float(with_paren.group(1).replace(",", ".")),
            "its_scob": float(with_paren.group(2).replace(",", ".")),
            "date": match.group(1) if match else None,
        }
    plain = RE_PRICE.search(raw_text)
    if plain:
        match = RE_DATE.search(raw_text)
        return {
            **base,
            "variant": 1,
            "its": float(plain.group(1).replace(",", ".")),
            "date": match.group(1) if match else None,
        }
    return base


def extract_reply_codes(text: str | None) -> tuple[str, ...]:
    seen: list[str] = []
    for raw_chunk in RE_CODE_TOKEN.findall(text or ""):
        normalized = re.sub(r"\D", "", raw_chunk or "")
        if len(normalized) < 10 or len(normalized) > 14:
            continue
        if normalized not in seen:
            seen.append(normalized)
    return tuple(seen)


def classify_reply_code_match(
    *,
    requested_code: str | None,
    reply_text: str | None = None,
    reply_codes: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    normalized_requested = re.sub(r"\D", "", requested_code or "")
    candidates = tuple(reply_codes) if reply_codes is not None else extract_reply_codes(reply_text)
    if not normalized_requested or not candidates:
        return "absent", candidates
    if any(candidate == normalized_requested for candidate in candidates):
        return "exact_match", candidates
    if len(normalized_requested) == 10 and any(len(candidate) == 14 and candidate.startswith(normalized_requested) for candidate in candidates):
        return "extended_match", candidates
    if len(normalized_requested) == 14 and any(candidate == normalized_requested[:10] for candidate in candidates):
        return "extended_match", candidates
    return "mismatch", candidates
