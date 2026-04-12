from __future__ import annotations

import json


TRIAGE_PROMPT_RU = """Роль: эксперт по предварительной классификации грузов.
Задача: проанализируй 1-5 изображений и определи, что за товар на них.
Верни строго JSON:
{
  "item_name": "краткое название товара",
  "is_marking_present": true,
  "is_text_readable": true,
  "complex_required": false,
  "reason": "почему нужен или не нужен углубленный разбор"
}
Ставь complex_required=true, если есть технические шильды, мелкий состав, таблицы или важные детали.
"""

IMAGE_ANALYSIS_PROMPT_RU = """Роль: технический визуальный аналитик.
Задача: составь максимально подробное фактическое описание изображения товара без подбора ТН ВЭД и без классификационных выводов.
Укажи:
- тип товара и видимые компоненты;
- материалы;
- технические шильды/таблицы, серийные номера, модели;
- измеримые характеристики, которые видны;
- зоны неопределенности.
Пиши только наблюдаемые факты по изображению.
Не используй формулировки вроде "для таможенной классификации", "предварительная классификация", "код ТН ВЭД".
Верни структурированный текст на русском языке.
"""

FORCED_OCR_PROMPT_RU = """Роль: специалист OCR по техническим маркировкам.
Задача: вытащи максимум фактических данных с фото.
Обязательно:
- выписывай конкретные значения;
- если виден текст на иностранном языке, дай перевод на русский;
- не пиши общие фразы вроде "видна таблица", пиши именно данные;
- нечитабельные части отмечай как "неразборчиво".
Верни обычный структурированный текст на русском языке.
"""

TRANSLATE_NAME_PROMPT_RU = """Переведи название товара на русский язык.
Верни только короткий русский вариант без пояснений и без JSON.
Если текст уже на русском, просто аккуратно нормализуй его.
"""

OCR_QUALITY_CHECK_PROMPT_RU = """Роль: дешевый текстовый контролер качества OCR.
Ты НЕ смотришь на изображения, а оцениваешь только текст OCR и контекст товара.
Нужно понять: хватает ли фактов для дальнейшего анализа, или нужен повторный углубленный OCR.

Верни строго JSON:
{
  "needs_retry": false,
  "confidence": "high",
  "has_concrete_data": true,
  "reason": "краткая причина",
  "missing_signals": ["модель", "мощность"]
}

Правила:
- needs_retry=true, если OCR слишком общий, пустой или почти без фактов;
- has_concrete_data=true, если в тексте уже есть конкретные признаки: модель, размеры, мощность, состав, артикул, серийные данные или другие технические детали;
- confidence: high / medium / low;
- missing_signals: короткий список того, чего не хватает.
"""


def build_triage_prompt(*, user_text: str | None) -> str:
    prompt = TRIAGE_PROMPT_RU
    if user_text:
        prompt += f"\n\nКонтекст пользователя:\n{user_text}"
    return prompt


def build_deep_ocr_prompt(*, user_text: str | None, triage_json: dict[str, object]) -> str:
    prompt = IMAGE_ANALYSIS_PROMPT_RU
    if user_text:
        prompt += f"\n\nКонтекст пользователя:\n{user_text}"
    prompt += "\n\nJSON triage:\n" + json.dumps(triage_json, ensure_ascii=False)
    return prompt


def build_forced_ocr_prompt(*, user_text: str | None, triage_json: dict[str, object]) -> str:
    prompt = FORCED_OCR_PROMPT_RU + "\n\nJSON triage:\n" + json.dumps(triage_json, ensure_ascii=False)
    if user_text:
        prompt += f"\n\nКонтекст пользователя:\n{user_text}"
    return prompt


def build_quality_check_prompt(
    *,
    user_text: str | None,
    triage_json: dict[str, object],
    image_description: str,
) -> str:
    prompt = OCR_QUALITY_CHECK_PROMPT_RU
    if user_text:
        prompt += f"\n\nКонтекст пользователя:\n{user_text}"
    prompt += "\n\nJSON triage:\n" + json.dumps(triage_json, ensure_ascii=False)
    prompt += f"\n\nТекст OCR/описания:\n{image_description or '—'}"
    return prompt
