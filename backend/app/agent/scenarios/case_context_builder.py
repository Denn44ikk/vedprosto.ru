from __future__ import annotations

import json
from typing import Any

from ..core import ChatAttachments, ChatContextPacket, ChatTranscriptMessage


def _truncate_text(value: object, *, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]..."


def _short_json(value: object, *, limit: int = 5000) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        rendered = "null"
    return _truncate_text(rendered, limit=limit)


class CaseAgentContextBuilder:
    def __init__(self, *, attachments: ChatAttachments) -> None:
        self._attachments = attachments

    def build(
        self,
        *,
        runtime_context: dict[str, Any],
        recent_messages: list[ChatTranscriptMessage],
        channel_label: str,
    ) -> ChatContextPacket:
        case_payload = runtime_context.get("case_payload") if isinstance(runtime_context.get("case_payload"), dict) else {}
        source_row_payload = runtime_context.get("source_row_payload") if isinstance(runtime_context.get("source_row_payload"), dict) else {}
        status_payload = runtime_context.get("status_payload") if isinstance(runtime_context.get("status_payload"), dict) else {}
        current_case = runtime_context.get("current_case") if isinstance(runtime_context.get("current_case"), dict) else {}
        expander_payload = runtime_context.get("expander_payload") if isinstance(runtime_context.get("expander_payload"), dict) else {}
        ocr_payload = runtime_context.get("ocr_payload") if isinstance(runtime_context.get("ocr_payload"), dict) else {}
        tnved_payload = runtime_context.get("tnved_payload") if isinstance(runtime_context.get("tnved_payload"), dict) else {}
        verification_payload = runtime_context.get("verification_payload") if isinstance(runtime_context.get("verification_payload"), dict) else {}
        enrichment_payload = runtime_context.get("enrichment_payload") if isinstance(runtime_context.get("enrichment_payload"), dict) else {}
        calculations_payload = runtime_context.get("calculations_payload") if isinstance(runtime_context.get("calculations_payload"), dict) else {}
        questions_payload = runtime_context.get("questions_payload") if isinstance(runtime_context.get("questions_payload"), dict) else {}
        web_research_payload = runtime_context.get("web_research_payload") if isinstance(runtime_context.get("web_research_payload"), dict) else {}
        agent_tools_payload = runtime_context.get("agent_tools_payload") if isinstance(runtime_context.get("agent_tools_payload"), dict) else {}
        pipeline_result_payload = runtime_context.get("pipeline_result_payload") if isinstance(runtime_context.get("pipeline_result_payload"), dict) else {}
        ui_response_payload = runtime_context.get("ui_response_payload") if isinstance(runtime_context.get("ui_response_payload"), dict) else {}
        export_payload = runtime_context.get("export_payload") if isinstance(runtime_context.get("export_payload"), dict) else {}

        work_files = runtime_context.get("work_files") if isinstance(runtime_context.get("work_files"), list) else []
        result_files = runtime_context.get("result_files") if isinstance(runtime_context.get("result_files"), list) else []
        summary = current_case.get("summary") if isinstance(current_case.get("summary"), dict) else {}
        code_options = current_case.get("code_options") if isinstance(current_case.get("code_options"), list) else []
        support_sections = current_case.get("support_sections") if isinstance(current_case.get("support_sections"), list) else []
        analysis_sections = current_case.get("analysis_sections") if isinstance(current_case.get("analysis_sections"), list) else []
        question_items = current_case.get("question_items") if isinstance(current_case.get("question_items"), list) else []
        questions = current_case.get("questions") if isinstance(current_case.get("questions"), list) else []

        image_lines = [f"- {name}" for name in self._attachments.image_names(runtime_context)] or ["- Изображения не найдены."]
        work_file_lines = [f"- {item}" for item in work_files] or ["- work/*.json пока нет."]
        result_file_lines = [f"- {item}" for item in result_files] or ["- result/*.json пока нет."]
        recent_dialog_lines = [f"- {message.role}: {message.text}" for message in recent_messages] or ["- Диалога пока нет."]

        code_lines: list[str] = []
        for option in code_options[:8]:
            if not isinstance(option, dict):
                continue
            code_lines.append(
                f"- {option.get('code', '—')} | confidence={option.get('confidence_percent', '—')}% | "
                f"ПОШ={option.get('posh', '—')} | ИТС={option.get('its', '—')} | НДС={option.get('nds', '—')} | "
                f"СТП={option.get('stp', '—')} | why={_truncate_text(option.get('why_alive', '—'), limit=260)}"
            )
        if not code_lines:
            code_lines = ["- Кандидаты пока не собраны."]

        support_lines: list[str] = []
        for item in support_sections[:8]:
            if not isinstance(item, dict):
                continue
            support_lines.append(
                f"- {item.get('title', '—')}: {_truncate_text(item.get('value', '—'), limit=260)}"
            )
        if not support_lines:
            support_lines = ["- Блок support_sections пока пуст."]

        analysis_lines: list[str] = []
        for item in analysis_sections[:8]:
            if not isinstance(item, dict):
                continue
            analysis_lines.append(
                f"- {item.get('title', '—')}: {_truncate_text(item.get('value', '—'), limit=260)}"
            )
        if not analysis_lines:
            analysis_lines = ["- Аналитические секции пока пусты."]

        question_lines: list[str] = []
        for item in question_items[:5]:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            if not question:
                continue
            why = _truncate_text(item.get("why", "—"), limit=220)
            question_lines.append(
                f"- {question} | stage={item.get('source_stage', '—')} | why={why}"
            )
        if not question_lines:
            question_lines = [f"- {str(item).strip()}" for item in questions[:5] if str(item).strip()]
        if not question_lines:
            question_lines = ["- Уточняющие вопросы пока не сформированы."]

        web_research_lines: list[str] = []
        if web_research_payload:
            status = str(web_research_payload.get("status", "")).strip() or "unknown"
            query = str(web_research_payload.get("query", "")).strip()
            note = str(web_research_payload.get("note", "")).strip()
            web_research_lines.append(f"- status={status}")
            if query:
                web_research_lines.append(f"- query: {query}")
            for index, item in enumerate(web_research_payload.get("results", []) if isinstance(web_research_payload.get("results"), list) else [], start=1):
                if not isinstance(item, dict):
                    continue
                title = _truncate_text(item.get("title", "—"), limit=180)
                url = _truncate_text(item.get("url", "—"), limit=220)
                snippet = _truncate_text(item.get("snippet", "—"), limit=220)
                web_research_lines.append(f"- {index}. {title} | {url} | {snippet}")
            if note:
                web_research_lines.append(f"- note: {note}")
        if not web_research_lines:
            web_research_lines = ["- Web research пока не запускался."]

        agent_tool_lines: list[str] = []
        if agent_tools_payload:
            available_tools = agent_tools_payload.get("available_tools") if isinstance(agent_tools_payload.get("available_tools"), dict) else {}
            relevant_codes = agent_tools_payload.get("relevant_codes") if isinstance(agent_tools_payload.get("relevant_codes"), list) else []
            live_reads = agent_tools_payload.get("live_reads") if isinstance(agent_tools_payload.get("live_reads"), dict) else {}
            if available_tools:
                enabled_names = [name for name, enabled in available_tools.items() if bool(enabled)]
                disabled_names = [name for name, enabled in available_tools.items() if not bool(enabled)]
                if enabled_names:
                    agent_tool_lines.append(f"- enabled: {', '.join(enabled_names)}")
                if disabled_names:
                    agent_tool_lines.append(f"- disabled: {', '.join(disabled_names)}")
            if relevant_codes:
                agent_tool_lines.append(f"- relevant_codes: {', '.join(str(item) for item in relevant_codes)}")
            if live_reads:
                agent_tool_lines.append(f"- live_reads: {', '.join(live_reads.keys())}")
        if not agent_tool_lines:
            agent_tool_lines = ["- Agent tools payload пока пуст."]

        markdown = "\n".join(
            [
                "# Case Agent Context Packet",
                "",
                "## Правила",
                f"- Канал вызова: {channel_label}.",
                "- Это agent по одному case ТН ВЭД.",
                "- Используй только данные из этого case, истории диалога и приложенных изображений.",
                "- Если в payload есть agent tool digests, считай их валидными Python-readouts проекта.",
                "- Если данных недостаточно, прямо укажи, каких файлов/фактов не хватает.",
                "- Не придумывай внешние результаты, которых нет в case-файлах.",
                "- Если в case есть противоречие между legacy и pipeline данными, явно скажи об этом.",
                "",
                "## Идентификация кейса",
                f"- case_id: {runtime_context.get('case_id', '—')}",
                f"- case_dir: {runtime_context.get('case_dir', '—')}",
                f"- root_path: {runtime_context.get('root_path', '—')}",
                f"- source_file: {case_payload.get('source_file', '—')}",
                f"- sheet_name: {case_payload.get('sheet_name', '—')}",
                f"- row_number: {case_payload.get('row_number', '—')}",
                f"- row_span: {case_payload.get('row_span', '—')}",
                "",
                "## Быстрая сводка",
                f"- raw_name: {case_payload.get('raw_name', '—')}",
                f"- title_ru: {current_case.get('title_ru', '—')}",
                f"- title_cn: {current_case.get('title_cn', '—')}",
                f"- summary_tnved: {summary.get('tnved', '—')}",
                f"- summary_posh: {summary.get('posh', '—')}",
                f"- summary_its: {summary.get('its', '—')}",
                f"- summary_nds: {summary.get('nds', '—')}",
                f"- summary_stp: {summary.get('stp', '—')}",
                f"- work_status: {status_payload.get('status', '—')}",
                f"- current_stage: {status_payload.get('current_stage', '—')}",
                f"- current_case.work_stage: {current_case.get('work_stage', '—')}",
                "",
                "## OCR / текст",
                f"- text_ru: {_truncate_text(current_case.get('text_ru', '—'), limit=700)}",
                f"- text_cn: {_truncate_text(current_case.get('text_cn', '—'), limit=700)}",
                f"- ocr_text: {_truncate_text(current_case.get('ocr_text', '—'), limit=1200)}",
                f"- image_description: {_truncate_text(current_case.get('image_description', '—'), limit=1200)}",
                "",
                "## Кандидаты кодов",
                *code_lines,
                "",
                "## UI analysis sections",
                *analysis_lines,
                "",
                "## Уточняющие вопросы",
                *question_lines,
                "",
                "## Web research",
                *web_research_lines,
                "",
                "## Agent tools",
                *agent_tool_lines,
                "",
                "## Support / enrichment",
                *support_lines,
                "",
                "## Изображения кейса",
                *image_lines,
                "",
                "## Файлы work/",
                *work_file_lines,
                "",
                "## Файлы result/",
                *result_file_lines,
                "",
                "## Последний диалог",
                *recent_dialog_lines,
                "",
                "## raw case.json",
                _short_json(case_payload),
                "",
                "## raw source_row.json",
                _short_json(source_row_payload),
                "",
                "## raw work/status.json",
                _short_json(status_payload),
                "",
                "## raw work/01_expander.json",
                _short_json(expander_payload),
                "",
                "## raw work/ocr.json",
                _short_json(ocr_payload),
                "",
                "## raw work/tnved.json",
                _short_json(tnved_payload),
                "",
                "## raw work/verification.json",
                _short_json(verification_payload),
                "",
                "## raw work/enrichment.json",
                _short_json(enrichment_payload),
                "",
                "## raw work/calculations.json",
                _short_json(calculations_payload),
                "",
                "## raw work/questions.json",
                _short_json(questions_payload),
                "",
                "## raw web research",
                _short_json(web_research_payload, limit=3000),
                "",
                "## raw agent tools",
                _short_json(agent_tools_payload, limit=5000),
                "",
                "## raw result/pipeline_result.json",
                _short_json(pipeline_result_payload),
                "",
                "## raw result/ui_response.json",
                _short_json(ui_response_payload),
                "",
                "## raw result/export.json",
                _short_json(export_payload),
            ]
        ).strip() + "\n"

        return ChatContextPacket(
            markdown=markdown,
            payload={
                "case_id": runtime_context.get("case_id"),
                "case_dir": runtime_context.get("case_dir"),
                "root_path": runtime_context.get("root_path"),
                "work_files": work_files,
                "result_files": result_files,
                "image_names": self._attachments.image_names(runtime_context),
            },
        )
