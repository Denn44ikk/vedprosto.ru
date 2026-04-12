from __future__ import annotations

import re


PP1637_CUSTOMS_FEE_EMOJI = "🧾"
SIGMA_PROTECTIVE_EMOJI = "🛡️"
SIGMA_EXCISE_EMOJI = "💰"
SIGMA_MANDATORY_MARKING_EMOJI = "🏷️"
SIGMA_ECO_ATTENTION_PREFIX = "♻️"
SIGMA_SECTION_ECO_EMOJI = "♻️"

_SIGMA_EMOJI_ORDER: tuple[str, ...] = (
    PP1637_CUSTOMS_FEE_EMOJI,
    SIGMA_PROTECTIVE_EMOJI,
    SIGMA_EXCISE_EMOJI,
    SIGMA_MANDATORY_MARKING_EMOJI,
)
_SIGMA_EMOJI_PRIORITY = {emoji: index for index, emoji in enumerate(_SIGMA_EMOJI_ORDER)}


def normalize_code_10(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    text = str(value or "").strip()
    if len(digits) == 9 and re.fullmatch(r"\d{4}\D+\d{2}\D+\d{3}", text):
        digits = digits + "0"
    return digits if len(digits) == 10 else ""


def _iter_emoji_flags(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        cleaned = value.strip()
        return (cleaned,) if cleaned else ()
    if isinstance(value, (list, tuple)):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_iter_emoji_flags(item))
        return tuple(flattened)
    return ()


def normalize_emoji_flags(value: object) -> tuple[str, ...]:
    collected: list[str] = []
    seen: set[str] = set()
    for item in _iter_emoji_flags(value):
        if item in seen:
            continue
        seen.add(item)
        collected.append(item)
    ordered = sorted(
        enumerate(collected),
        key=lambda pair: (_SIGMA_EMOJI_PRIORITY.get(pair[1], len(_SIGMA_EMOJI_PRIORITY)), pair[0]),
    )
    return tuple(item for _, item in ordered)


__all__ = [
    "PP1637_CUSTOMS_FEE_EMOJI",
    "SIGMA_ECO_ATTENTION_PREFIX",
    "SIGMA_EXCISE_EMOJI",
    "SIGMA_MANDATORY_MARKING_EMOJI",
    "SIGMA_PROTECTIVE_EMOJI",
    "SIGMA_SECTION_ECO_EMOJI",
    "normalize_code_10",
    "normalize_emoji_flags",
]
