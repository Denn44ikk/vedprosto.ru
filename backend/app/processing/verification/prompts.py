from __future__ import annotations


REPAIR_PROMPT_PREFIX_RU = """Роль: эксперт по ремонту подбора ТНВЭД.
Задача: выбери ровно один наиболее подходящий код только из разрешенного списка кандидатов.
Верни строго JSON:
{"tnved":"10-значный код из кандидатов или пусто","reason":"краткое объяснение"}"""


def build_repair_prompt(
    *,
    item_context: str,
    original_code: str,
    options_text: str,
) -> str:
    return (
        REPAIR_PROMPT_PREFIX_RU
        + "\n\nКонтекст товара:\n"
        + item_context
        + "\n\nИсходный код: "
        + (original_code or "пусто")
        + "\nРазрешенные кандидаты:\n"
        + options_text
        + "\n"
    )
