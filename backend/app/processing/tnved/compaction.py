from __future__ import annotations

import re


TNVED_ASSEMBLY_IMAGE_DESC_MAX_CHARS = 2600
TNVED_ASSEMBLY_IMAGE_DESC_MAX_LINES = 14

TNVED_ASSEMBLY_COMPACT_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("material", "Материал"),
    ("structure", "Структура"),
    ("purpose", "Назначение"),
    ("thickness", "Толщина"),
    ("width", "Ширина"),
    ("diameter", "Диаметр"),
    ("length", "Длина"),
    ("power", "Мощность"),
    ("voltage", "Напряжение"),
    ("frequency", "Частота"),
    ("productivity", "Производительность"),
    ("layers_count", "Слои"),
)

TNVED_ASSEMBLY_SIGNAL_HINTS = (
    "товар",
    "тип",
    "назнач",
    "материал",
    "состав",
    "структур",
    "сло",
    "толщин",
    "ширин",
    "диаметр",
    "длин",
    "мощност",
    "напряжен",
    "частот",
    "производ",
    "модель",
    "артикул",
    "серийн",
    "комплект",
    "характерист",
    "параметр",
    "размер",
    "точност",
    "диапазон",
)

TNVED_ASSEMBLY_MISSING_HINTS = (
    "не подтверж",
    "не установ",
    "не определ",
    "не различ",
    "не чита",
    "не видно",
    "не указ",
    "неясн",
    "отсутств",
)

TNVED_ASSEMBLY_NOISE_HINTS = (
    "hot_view",
    "откройте приложение",
    "open app",
    "立即下单",
    "去定制",
    "поддерживает кастомизацию",
    "industrial heat",
    "热度榜",
    "批发",
    "代发",
)


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _shorten_text(value: str | None, max_len: int = 160) -> str:
    text = (value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def _is_heading_line(line: str, *, raw_line: str) -> bool:
    cleaned = _collapse_spaces(line)
    lowered = cleaned.casefold()
    if not cleaned:
        return True
    if raw_line.lstrip().startswith("#"):
        return True
    if cleaned.endswith(":") and not re.search(r"\d", cleaned):
        return True
    if lowered in {
        "видны",
        "видно",
        "читается",
        "читаемые позиции",
        "окружение",
        "комплектность",
        "видимые компоненты",
        "зоны неопределенности",
        "видимые измеримые/числовые характеристики",
    }:
        return True
    if re.fullmatch(r"(?:\d+[.)]\s*)?[A-Za-zА-Яа-я\s/()\"«»-]{1,80}", cleaned) and not re.search(r"\d", cleaned):
        return True
    return False


def _is_noise_line(line: str) -> bool:
    lowered = line.casefold()
    if any(token in lowered for token in TNVED_ASSEMBLY_NOISE_HINTS):
        return True
    if "цена" in lowered or "¥" in line:
        return True
    return False


def compact_image_description_for_tnved_assembly(
    *,
    item_name: str,
    image_description: str,
    product_facts: dict[str, list[str]] | None = None,
    max_chars: int = TNVED_ASSEMBLY_IMAGE_DESC_MAX_CHARS,
) -> str:
    original = (image_description or "").strip()
    if not original or len(original) <= max_chars:
        return original

    product_facts = product_facts or {}
    selected_lines: list[str] = []
    seen: set[str] = set()

    def _add_line(value: str, *, force: bool = False) -> None:
        text = _collapse_spaces(value or "")
        if not text:
            return
        key = text.casefold()
        if key in seen:
            return
        if not force and len("\n".join(selected_lines + [f"- {text}"])) > max_chars:
            return
        seen.add(key)
        selected_lines.append(f"- {_shorten_text(text, max_len=220)}")

    if item_name:
        _add_line(f"Товар: {item_name}", force=True)
    for field, label in TNVED_ASSEMBLY_COMPACT_FIELD_LABELS:
        values = product_facts.get(field, [])
        if values:
            _add_line(f"{label}: {', '.join(values[:2])}")

    ranked_lines: list[tuple[int, int, str]] = []
    for index, raw_line in enumerate(original.splitlines()):
        raw = raw_line.strip()
        if not raw:
            continue
        cleaned = re.sub(r"^[>*\-•\s]+", "", raw)
        cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
        cleaned = _collapse_spaces(cleaned)
        if len(cleaned) < 4:
            continue
        if _is_heading_line(cleaned, raw_line=raw) or _is_noise_line(cleaned):
            continue
        lowered = cleaned.casefold()
        score = 0
        if index == 0 or any(token in lowered for token in ("товар:", "тип товара", "наименование", "назначение")):
            score += 6
        if any(token in lowered for token in TNVED_ASSEMBLY_MISSING_HINTS):
            score += 5
        if re.search(r"(?:<=|>=|<|>|≤|≥|±)\s*\d", cleaned) or re.search(r"\d", cleaned):
            score += 4
        if any(token in lowered for token in TNVED_ASSEMBLY_SIGNAL_HINTS):
            score += 3
        if ":" in cleaned:
            score += 2
        if 16 <= len(cleaned) <= 220:
            score += 1
        if score > 0:
            ranked_lines.append((index, score, cleaned))

    top_ranked: list[tuple[int, int, str]] = []
    ranked_seen: set[str] = set()
    for item in sorted(ranked_lines, key=lambda candidate: (-candidate[1], candidate[0])):
        key = item[2].casefold()
        if key in ranked_seen:
            continue
        ranked_seen.add(key)
        top_ranked.append(item)
        if len(top_ranked) >= TNVED_ASSEMBLY_IMAGE_DESC_MAX_LINES:
            break

    for _, _, line in sorted(top_ranked, key=lambda item: item[0]):
        _add_line(line)

    compacted = "\n".join(selected_lines).strip()
    if not compacted:
        return _shorten_text(original, max_len=max_chars)
    return compacted if len(compacted) <= max_chars else _shorten_text(compacted, max_len=max_chars)
