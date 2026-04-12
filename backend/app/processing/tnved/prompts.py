from __future__ import annotations

import json

from .models import TnvedIfcgDiscoveryHint, TnvedInput


TNVED_ASSEMBLY_PROMPT_RU = """Роль: профессиональный таможенный декларант.
Задача: на основе фактов из фото и текста подобрать код ТН ВЭД ЕАЭС.
Отвечай строго JSON, без текста вне JSON.

Правила:
- Используй только факты и проверяемые признаки.
- Если 10-значный код нельзя надежно финализировать, оставь `tnved` пустым и верни 1-3 кандидата.
- Если `tnved` пустой, список кандидатов не должен быть пустым.
- Для выбранного кода и для кандидатов раскрывай решающие признаки, а не общие формулировки.
- `observed_attributes.materials` заполняй только по явно подтвержденным данным.
- Сформируй до 3 самых полезных уточняющих вопросов, которые реально помогут выбрать код точнее.
- Вопросы должны быть короткими, конкретными и про недостающие признаки товара, а не общими советами.

IFCG discovery:
- Если передан блок IFCG discovery, считай его мягким вспомогательным evidence.
- IFCG discovery может подсказать ветку, профессиональные формулировки и соседние коды.
- IFCG discovery не имеет права сам по себе финализировать код без товарных фактов.

Схема JSON:
{
  "tnved": "XXXXXXXXXX или пусто",
  "tnved_10": "дублирующее поле, если удобно",
  "tnved_description": "короткое описание кода",
  "selection_rationale": "1-3 предложения по фактам",
  "explanation": "alias для selection_rationale",
  "error_reason": "почему код не финализирован",
  "confidence_percent": 0-100,
  "possible_codes": ["XXXXXXXXXX"],
  "candidates": ["XXXXXXXXXX"],
  "candidates_reasoned": [
    {"code":"XXXXXXXXXX","why":"краткое отличие","source":"tnved|ifcg|web","probability_percent":0-100}
  ],
  "observed_attributes": {
    "materials": ["явно подтвержденные материалы товара"],
    "material_evidence": ["короткие строки/факты"],
    "uncertain_materials": ["неподтвержденные, но возможные материалы"]
  },
  "decisive_criteria": {
    "summary": "short criteria summary",
    "matched": ["..."],
    "numeric_matched": ["..."],
    "missing": ["..."],
    "contradictions": ["..."],
    "numeric_thresholds": ["..."],
    "text_flags": ["..."],
    "special_flags": ["..."]
  },
  "clarification_questions": [
    {"question":"...", "why":"зачем этот вопрос влияет на код", "missing_fact":"какого факта не хватает", "priority":1}
  ]
}
"""


def _ifcg_hint_to_payload(hint: TnvedIfcgDiscoveryHint | None) -> dict[str, object]:
    if hint is None:
        return {}
    return {
        "summary": hint.summary,
        "suggested_groups": list(hint.suggested_groups),
        "suggested_codes": list(hint.suggested_codes),
        "broad_queries": list(hint.broad_queries),
        "warnings": list(hint.warnings),
    }


def build_tnved_assembly_prompt(
    *,
    run_input: TnvedInput,
    compacted_image_description: str,
) -> str:
    parts = [
        TNVED_ASSEMBLY_PROMPT_RU,
        "\nОписание изображения:\n" + (compacted_image_description or "нет"),
        "\nJSON triage:\n" + json.dumps(run_input.triage_payload or {}, ensure_ascii=False),
    ]
    if run_input.item_name:
        parts.append("\nНазвание товара:\n" + run_input.item_name)
    if run_input.user_text:
        parts.append("\nКонтекст пользователя:\n" + run_input.user_text)
    if run_input.product_facts:
        parts.append("\nProduct facts:\n" + json.dumps(run_input.product_facts, ensure_ascii=False))
    if run_input.observed_attributes:
        parts.append(
            "\nObserved attributes:\n"
            + json.dumps(
                {
                    "materials": list(run_input.observed_attributes.materials),
                    "material_evidence": list(run_input.observed_attributes.material_evidence),
                    "uncertain_materials": list(run_input.observed_attributes.uncertain_materials),
                },
                ensure_ascii=False,
            )
        )
    if run_input.web_hint_text:
        parts.append("\nВеб-подсказка:\n" + run_input.web_hint_text)
    if run_input.ifcg_discovery is not None:
        parts.append(
            "\nIFCG discovery (soft evidence only):\n"
            + json.dumps(_ifcg_hint_to_payload(run_input.ifcg_discovery), ensure_ascii=False)
        )
    return "".join(parts)
