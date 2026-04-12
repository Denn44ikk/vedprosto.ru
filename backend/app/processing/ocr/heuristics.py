from __future__ import annotations

import json
import re
from typing import Any

from .models import OcrQualityDecision


DATA_WITH_UNIT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:kw|w|hp|v|hz|mm|cm|m|kg|g|mah|a|в|а|вт|мм|см|кг)\b",
    re.IGNORECASE,
)
MODEL_CODE_RE = re.compile(r"\b[A-ZА-Я0-9]{2,}[-_/]?[A-ZА-Я0-9]{1,}\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"\d")


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def to_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "да", "истина"}:
            return True
        if normalized in {"false", "0", "no", "n", "нет", "ложь"}:
            return False
    return default


def extract_json_dict(raw_text: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw_text[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {}


def normalize_triage_json(raw: dict[str, object]) -> dict[str, object]:
    item_name = collapse_spaces(
        str(
            raw.get("item_name")
            or raw.get("item")
            or raw.get("product_name")
            or raw.get("название_товара")
            or ""
        )
    )
    item_name = re.sub(r"^[#>*\s-]*\d+\)\s*", "", item_name)
    if ":" in item_name and item_name.lower().startswith(("тип товара", "item type")):
        item_name = item_name.split(":", 1)[-1].strip()
    item_name = item_name[:140]
    if not raw:
        return {
            "item_name": item_name,
            "is_marking_present": False,
            "is_text_readable": True,
            "complex_required": True,
            "reason": "triage_json_empty",
        }
    return {
        "item_name": item_name,
        "is_marking_present": to_bool(raw.get("is_marking_present"), default=False),
        "is_text_readable": to_bool(raw.get("is_text_readable"), default=True),
        "complex_required": to_bool(raw.get("complex_required"), default=False),
        "reason": collapse_spaces(str(raw.get("reason") or raw.get("обоснование") or "")),
    }


def normalize_quality_json(raw: dict[str, Any]) -> OcrQualityDecision | None:
    if not raw:
        return None
    confidence = collapse_spaces(str(raw.get("confidence") or "")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    reason = collapse_spaces(str(raw.get("reason") or raw.get("comment") or ""))
    return OcrQualityDecision(
        retry_required=to_bool(raw.get("needs_retry"), default=False),
        reason=reason or "quality_check_no_reason",
        lazy_detected=to_bool(raw.get("needs_retry"), default=False),
        reviewer="cheap_text_check",
        confidence=confidence,
        has_concrete_data=to_bool(raw.get("has_concrete_data"), default=False),
    )


def needs_deep_ocr(user_text: str | None, triage_json: dict[str, object]) -> bool:
    if to_bool(triage_json.get("complex_required"), default=False):
        return True
    if not to_bool(triage_json.get("is_text_readable"), default=True):
        return True
    if not str(triage_json.get("item_name") or "").strip() and (user_text or "").strip():
        return True
    return False


def _has_concrete_data(text: str) -> bool:
    normalized = text.strip()
    if len(normalized) >= 120 and NUMBER_RE.search(normalized):
        return True
    if DATA_WITH_UNIT_RE.search(normalized):
        return True
    if MODEL_CODE_RE.search(normalized):
        return True
    return False


def decide_ocr_retry(
    *,
    ocr_rounds: int,
    image_description: str,
    selection_rationale: str,
) -> OcrQualityDecision:
    if ocr_rounds >= 2:
        return OcrQualityDecision(
            retry_required=False,
            reason="deep_ocr_already_used",
            lazy_detected=False,
            reviewer="fallback_rules",
            confidence="high",
            has_concrete_data=_has_concrete_data(image_description),
        )

    description = (image_description or "").strip()
    if not description:
        return OcrQualityDecision(
            retry_required=True,
            reason="empty_image_description",
            lazy_detected=True,
            reviewer="fallback_rules",
            confidence="high",
            has_concrete_data=False,
        )

    has_concrete_data = _has_concrete_data(description)
    if has_concrete_data:
        return OcrQualityDecision(
            retry_required=False,
            reason="ocr_quality_ok",
            lazy_detected=False,
            reviewer="fallback_rules",
            confidence="medium",
            has_concrete_data=True,
        )

    rationale = collapse_spaces(selection_rationale)
    short_text = len(description) < 80
    poor_structure = "\n" not in description and ":" not in description
    retry_required = short_text and poor_structure and bool(rationale)
    return OcrQualityDecision(
        retry_required=retry_required,
        reason="fallback_text_too_thin" if retry_required else "fallback_text_ok",
        lazy_detected=retry_required,
        reviewer="fallback_rules",
        confidence="low",
        has_concrete_data=False,
    )


def choose_quality_decision(
    *,
    ai_decision: OcrQualityDecision | None,
    fallback_decision: OcrQualityDecision,
) -> OcrQualityDecision:
    if ai_decision is None:
        return fallback_decision
    if fallback_decision.reason == "empty_image_description":
        return fallback_decision
    if ai_decision.retry_required:
        return ai_decision
    if fallback_decision.retry_required and not ai_decision.has_concrete_data:
        return fallback_decision
    return ai_decision


def build_single_pass_image_description(triage_json: dict[str, object]) -> str:
    item_name = str(triage_json.get("item_name", "")).strip() or "не определено"
    reason = str(triage_json.get("reason", "")).strip() or "нет пояснения"
    is_marking_present = to_bool(triage_json.get("is_marking_present"), default=False)
    is_text_readable = to_bool(triage_json.get("is_text_readable"), default=True)
    return (
        f"Название товара: {item_name}\n"
        f"Маркировка: {'есть' if is_marking_present else 'не обнаружена'}\n"
        f"Читаемость текста: {'читаем' if is_text_readable else 'плохо читаем'}\n"
        f"Комментарий triage: {reason}"
    )


def build_ocr_enrichment_block(ocr_text: str) -> str:
    cleaned = (ocr_text or "").strip()
    if not cleaned:
        return ""
    return f"\n\n[ВАЖНЫЕ ДАННЫЕ С ФОТО (OCR)]:\n{cleaned}\n[КОНЕЦ OCR]"


def merge_ocr_text_into_image_description(*, image_description: str, ocr_text: str) -> str:
    base = (image_description or "").strip()
    block = build_ocr_enrichment_block(ocr_text)
    if not block:
        return base
    if block in base:
        return base
    if not base:
        return block.strip()
    return base + block
