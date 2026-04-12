from __future__ import annotations


class AnalysisPlaceholderService:
    @staticmethod
    def _value(*candidates: object, fallback: str = "—") -> str:
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return fallback

    def build_payload(
        self,
        *,
        case_payload: dict,
        expander_payload: dict | None,
        image_count: int,
        source_row_labels: list[str],
    ) -> dict[str, object]:
        expander_identity = expander_payload.get("product_identity_hypothesis") if isinstance(expander_payload, dict) else {}
        if not isinstance(expander_identity, dict):
            expander_identity = {}

        expander_summary = self._value(
            expander_identity.get("summary_ru"),
            expander_identity.get("short_label_ru"),
            fallback="По кейсу пока доступен только базовый fallback-отчет без полного pipeline.",
        )
        raw_name = self._value(case_payload.get("raw_name"))
        extra_info = self._value(case_payload.get("extra_info"))
        title_ru = self._value(expander_identity.get("short_label_ru"), expander_identity.get("summary_ru"))
        duplicate_group_size = int(case_payload.get("duplicate_group_size", 0) or 0)
        same_name_group_size = int(case_payload.get("same_name_group_size", 0) or 0)
        row_span = self._value(case_payload.get("row_span"))
        source_rows_label = ", ".join(source_row_labels) if source_row_labels else row_span

        highlights = [
            {
                "label": "Фото",
                "value": str(image_count),
                "tone": "input",
            },
            {
                "label": "Строки",
                "value": source_rows_label or row_span,
                "tone": "input",
            },
            {
                "label": "OCR",
                "value": "есть черновое описание" if extra_info != "—" else "нужно усилить",
                "tone": "input",
            },
            {
                "label": "Повторы",
                "value": f"dup {duplicate_group_size or 1} / name {same_name_group_size or 1}",
                "tone": "muted",
            },
        ]

        lines = [
            "Входной профиль товара",
            "",
            "1. Что пришло на вход",
            f"- исходное / китайское наименование: {raw_name}",
            f"- русская черновая интерпретация: {title_ru}",
            f"- OCR / LLM-описание: {extra_info if extra_info != '—' else '—'}",
            f"- фото по товару: {image_count}",
            "",
            "2. Откуда это взялось",
            f"- файл: {self._value(case_payload.get('source_file'))}",
            f"- лист: {self._value(case_payload.get('sheet_name'))}",
            f"- диапазон строки: {row_span}",
            f"- исходные строки: {source_rows_label or '—'}",
            "",
            "3. Что уже удалось вытащить из входа",
            expander_summary if expander_summary != "—" else "Пока есть только базовый fallback-черновик без полного pipeline.",
            "",
            "4. Что уже видно по кейсу",
            f"- исходное имя товара: {raw_name}",
            f"- рабочее русское название: {title_ru}",
            f"- доп. сведения из таблицы: {extra_info}",
            f"- размер duplicate-группы: {duplicate_group_size or 1}",
            f"- размер same-name группы: {same_name_group_size or 1}",
            "",
            "5. Что еще стоит уточнить у поставщика или в документах",
            "- материал / состав изделия;",
            "- основную функцию и где используется товар;",
            "- бренд, модель, артикул и маркировку;",
            "- упаковку, вес и единицы, чтобы потом собрать бирку и расчеты.",
            "- что именно видно на фотографии, а что пока не подтверждено текстом.",
        ]

        analysis_sections = [
            {
                "title": "Вход",
                "value": "\n".join(lines),
            }
        ]

        return {
            "analysis_sections": analysis_sections,
            "analysis_highlights": highlights,
            "long_report": "\n".join(lines),
        }
