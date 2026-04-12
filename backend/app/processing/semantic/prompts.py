from __future__ import annotations


SEMANTIC_GUARD_PROMPT_PREFIX_RU = """Роль: старший эксперт по смысловой валидации подбора ТН ВЭД.
Задача: сравнить факты о товаре с описаниями нескольких близких кодов ТН ВЭД и выбрать только тот код, который действительно подтверждается фактами.

Правила:
- Нельзя подтверждать узкий или специальный leaf-код без прямых признаков в фактах.
- Существование кода в каталоге не означает, что он подходит по смыслу.
- Текущее обоснование модели считай только рабочей гипотезой, а не доказательством.
- Если специальный код требует признаков, которых нет в фактах, это `insufficient_evidence`.
- Если код противоречит фактам товара, это `contradicted`.
- Если несколько кодов возможны, предпочти код с меньшим числом допущений.
- Если фактов хватает только на общий тип товара, предпочти более общий код, а не специальный leaf.
- Выбирай только из списка предложенных кодов.

Верни строго JSON:
{
  "selected_code": "XXXXXXXXXX или пусто",
  "selected_status": "supported|insufficient_evidence|contradicted|unknown",
  "reason": "краткое итоговое объяснение",
  "selected_operator_summary": "короткая фраза для оператора",
  "recommended_review": true,
  "evaluations": [
    {
      "code": "XXXXXXXXXX",
      "status": "supported|insufficient_evidence|contradicted|unknown",
      "support_score": 0-100,
      "matched_facts": ["..."],
      "missing_facts": ["..."],
      "contradictions": ["..."],
      "difference_for_operator": "короткая фраза для оператора",
      "why": "краткое объяснение"
    }
  ]
}
"""


def build_semantic_guard_prompt(
    *,
    evidence_summary: str,
    selected_code: str,
    selected_description: str,
    llm_rationale: str,
    candidate_codes: list[str],
    descriptions: dict[str, str],
    probability_map: dict[str, float],
) -> str:
    lines: list[str] = [SEMANTIC_GUARD_PROMPT_PREFIX_RU]
    lines.append("\nФакты о товаре:\n" + evidence_summary.strip())
    if selected_code:
        description = str(descriptions.get(selected_code, "")).strip() or selected_description or "описание отсутствует"
        lines.append(f"\nТекущий выбранный код:\n{selected_code}: {description[:900]}")
    if llm_rationale:
        lines.append("\nТекущее обоснование модели:\n" + llm_rationale.strip())
    lines.append("\nКоды для проверки:")
    for code in candidate_codes:
        description = str(descriptions.get(code, "")).strip() or "описание отсутствует"
        probability = probability_map.get(code)
        suffix = f" | model_prob={round(probability, 1)}" if probability is not None else ""
        lines.append(f"- {code}: {description[:900]}{suffix}")
    return "\n".join(lines)
