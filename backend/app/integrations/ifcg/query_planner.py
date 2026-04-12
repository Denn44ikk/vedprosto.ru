from __future__ import annotations

import re

from ...integrations.ai.service import AIIntegrationService
from .models import IfcgInput, IfcgQuery, IfcgQueryPlan
from .query_builder import collapse_spaces, sanitize_ifcg_text


IFCG_QUERY_PLANNER_PROMPT_RU = """Роль: старший декларант РФ, который готовит broad probing-запросы для IFCG.
Задача: по описанию товара составить 5-7 коротких стартовых запросов для https://www.ifcg.ru/kb/tnved/search/ .

Что ты делаешь:
- Ты НЕ подтверждаешь заранее выбранный код и НЕ пытаешься написать одно "идеально точное" описание товара.
- Ты собираешь несколько коротких товарных гипотез для разведки поля IFCG.
- Эти запросы нужны, чтобы быстро проверить основную сущность, смежные ветки и устойчивые профессиональные формулировки.
- Входной контекст может быть длинным, шумным и неполным. Не нужно упаковывать весь контекст в один запрос.
- Если факт не влияет на ветвление или не подтвержден, лучше не включать его в запрос.

Как писать запросы:
- Основа каждого запроса: товарная сущность.
- Обычно 2-6 слов.
- В одном запросе держи сущность + максимум 1-2 важных классификационных уточнения.
- Каждый следующий запрос должен менять только одну ось: материал, назначение, конструкция, подвид, профессиональный синоним.

Критично:
- Не возвращай длинные описания, вопросы, цены, веса, мусор карточки товара, артикульный шум и отдельные числа.
- Не делай почти одинаковые повторы.
- Не пиши пояснения, только JSON.

Верни строго JSON:
{
  "queries": [
    "запрос 1",
    "запрос 2"
  ],
  "alternate_queries": [
    "альтернативная формулировка 1"
  ]
}
"""


_LETTER_RE = re.compile(r"[A-Za-zА-Яа-я]")
_JSON_STRING_RE = re.compile(r'"((?:\\.|[^"\\])*)"')


def _looks_like_usable_ifcg_query(value: str) -> bool:
    clean = sanitize_ifcg_text(value)
    if len(clean) < 3:
        return False
    if not _LETTER_RE.search(clean):
        return False
    lowered = clean.casefold()
    if lowered.startswith("сколько стоит"):
        return False
    if lowered.endswith("?"):
        return False
    return True


def _build_prompt(search_input: IfcgInput, *, max_queries: int) -> str:
    lines: list[str] = [IFCG_QUERY_PLANNER_PROMPT_RU]
    lines.append(f"\nНужно вернуть не более {max(1, max_queries)} запросов.")
    lines.append("\nКонтекст TNVED-решения:")
    lines.append(f"- item_name: {collapse_spaces(search_input.item_name) or 'нет'}")
    if search_input.context_text:
        lines.append(f"- context_text: {collapse_spaces(search_input.context_text)}")
    if search_input.decision_rationale:
        lines.append(f"- decision_rationale: {collapse_spaces(search_input.decision_rationale)}")
    if search_input.observed_materials:
        lines.append("- observed_materials: " + ", ".join(search_input.observed_materials))
    if search_input.product_facts:
        for key, values in search_input.product_facts.items():
            if not values:
                continue
            lines.append(f"- {key}: " + "; ".join(collapse_spaces(str(value)) for value in values[:6]))
    if search_input.selected_code:
        lines.append(f"- current_selected_code: {search_input.selected_code}")
    if search_input.candidate_codes:
        lines.append("- current_candidates: " + ", ".join(search_input.candidate_codes[:6]))
    return "\n".join(lines)


def _normalize_broad_queries(raw: object, *, max_queries: int, label_prefix: str = "llm") -> tuple[IfcgQuery, ...]:
    if not isinstance(raw, list):
        return ()

    queries: list[IfcgQuery] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        why = ""
        text = ""
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("query") or item.get("q") or "").strip()
            why = collapse_spaces(str(item.get("why") or item.get("reason") or ""))
        elif isinstance(item, str):
            text = item.strip()

        clean = sanitize_ifcg_text(text)[:160]
        if not _looks_like_usable_ifcg_query(clean):
            continue
        cache_key = clean.casefold()
        if cache_key in seen:
            continue
        seen.add(cache_key)
        queries.append(
            IfcgQuery(
                text=clean,
                kind="broad",
                label=f"{label_prefix}_{index}",
                source="llm",
                rationale=why,
            )
        )
        if len(queries) >= max(1, max_queries):
            break
    return tuple(queries)


def _extract_partial_string_list(raw_text: str, field_name: str) -> list[str]:
    pattern = f'"{field_name}"'
    start = raw_text.find(pattern)
    if start < 0:
        return []
    array_start = raw_text.find("[", start)
    if array_start < 0:
        return []

    depth = 0
    array_end = -1
    for index in range(array_start, len(raw_text)):
        char = raw_text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                array_end = index
                break
    if array_end < 0:
        array_slice = raw_text[array_start:]
    else:
        array_slice = raw_text[array_start : array_end + 1]

    values: list[str] = []
    for match in _JSON_STRING_RE.finditer(array_slice):
        raw_value = match.group(1)
        if "\\" in raw_value:
            try:
                decoded = bytes(raw_value, "utf-8").decode("unicode_escape")
            except Exception:
                decoded = raw_value
        else:
            decoded = raw_value
        clean = collapse_spaces(decoded)
        if clean:
            values.append(clean)
    return values


def _extract_query_lists_from_raw_text(raw_text: str) -> dict[str, list[str]]:
    return {
        "queries": _extract_partial_string_list(raw_text, "queries")
        or _extract_partial_string_list(raw_text, "broad_queries"),
        "alternate_queries": _extract_partial_string_list(raw_text, "alternate_queries")
        or _extract_partial_string_list(raw_text, "alternatives"),
    }


def _build_retry_prompt(search_input: IfcgInput, *, max_queries: int) -> str:
    return (
        "Верни только короткий JSON без пояснений и без markdown.\n"
        "Нужны короткие broad IFCG-запросы как декларант со стажем.\n"
        "Это probing-запросы для поиска сигнала в соседних и смежных ветках, а не супер-точное описание товара.\n"
        "Обычно 2-6 слов: товарная сущность + 1-2 классификационно важных уточнения.\n"
        "Формат строго такой:\n"
        '{\n  "queries": ["..."],\n  "alternate_queries": ["..."]\n}\n'
        f"Не больше {max(1, max_queries)} запросов суммарно.\n\n"
        + _build_prompt(search_input, max_queries=max_queries)
    )


def build_fallback_query_plan(
    search_input: IfcgInput,
    *,
    max_queries: int,
    warning: str = "",
) -> IfcgQueryPlan:
    warnings = [warning] if warning else []
    warnings.append("LLM is required for IFCG query planning; Python fallback is disabled")
    return IfcgQueryPlan(
        broad_queries=(),
        planner_name="llm_required",
        rationale="IFCG broad queries must be generated by LLM.",
        warnings=tuple(warnings[:5]),
        fallback_used=True,
    )


class IfcgLlmQueryPlanner:
    def __init__(
        self,
        *,
        ai_service: AIIntegrationService,
        profile: str = "text_cheap",
        max_tokens: int = 900,
        use_fallback: bool = True,
    ) -> None:
        self._ai_service = ai_service
        self._profile = profile
        self._max_tokens = max(400, int(max_tokens))
        self._use_fallback = use_fallback

    async def plan(self, search_input: IfcgInput, *, max_queries: int = 7) -> IfcgQueryPlan:
        warnings: list[str] = []
        broad_queries: tuple[IfcgQuery, ...] = ()
        prompt_variants = (
            _build_prompt(search_input, max_queries=max_queries),
            _build_retry_prompt(search_input, max_queries=max_queries),
        )

        for attempt_index, prompt in enumerate(prompt_variants, start=1):
            try:
                payload = await self._ai_service.text_json(
                    profile=self._profile,
                    prompt=prompt,
                    use_fallback=self._use_fallback,
                    max_tokens=self._max_tokens,
                )
                if not isinstance(payload, dict):
                    payload = _extract_query_lists_from_raw_text(str(payload or ""))
            except Exception as exc:
                warnings.append(f"LLM planner failed on attempt {attempt_index}: {type(exc).__name__}")
                continue

            direct_queries = _normalize_broad_queries(
                payload.get("queries") or payload.get("broad_queries"),
                max_queries=max_queries,
                label_prefix="llm",
            )
            remaining_slots = max(0, max_queries - len(direct_queries))
            alternate_queries = _normalize_broad_queries(
                payload.get("alternate_queries") or payload.get("alternatives"),
                max_queries=remaining_slots,
                label_prefix="alt",
            )
            broad_queries = tuple(
                list(direct_queries)
                + [
                    query
                    for query in alternate_queries
                    if query.text.casefold() not in {item.text.casefold() for item in direct_queries}
                ]
            )
            if broad_queries:
                break
            warnings.append(f"LLM planner returned no usable queries on attempt {attempt_index}")

        if not broad_queries:
            return build_fallback_query_plan(
                search_input,
                max_queries=max_queries,
                warning="; ".join(warnings[:2]) or "LLM planner returned no usable queries",
            )

        return IfcgQueryPlan(
            broad_queries=broad_queries,
            planner_name=self._profile,
            rationale="IFCG broad queries generated by text-only LLM planner.",
            warnings=tuple(warnings[:5]),
            fallback_used=False,
        )
