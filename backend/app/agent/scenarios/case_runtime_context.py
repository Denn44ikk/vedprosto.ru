from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_question_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = payload if isinstance(payload, dict) else {}
    top_items = data.get("top") if isinstance(data.get("top"), list) else []
    result: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for index, item in enumerate(top_items, start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        if not question:
            continue
        lowered = question.casefold()
        if lowered in seen_questions:
            continue
        seen_questions.add(lowered)
        result.append(
            {
                "id": str(item.get("id", "")).strip() or f"question_{index}",
                "question": question,
                "why": str(item.get("why", "")).strip(),
                "source_stage": str(item.get("source_stage", "")).strip(),
                "priority": int(item.get("priority", index) or index),
                "status": str(item.get("status", "open") or "open").strip(),
                "answer": str(item.get("answer", "")).strip(),
                "related_codes": [
                    str(code).strip()
                    for code in (item.get("related_codes") if isinstance(item.get("related_codes"), list) else [])
                    if str(code).strip()
                ],
            }
        )
    return result[:3]


def _extract_questions(payload: dict[str, Any] | None) -> list[str]:
    items = _extract_question_items(payload)
    if items:
        return [str(item.get("question", "")).strip() for item in items if str(item.get("question", "")).strip()]
    data = payload if isinstance(payload, dict) else {}
    short_items = data.get("short") if isinstance(data.get("short"), list) else []
    return [str(item).strip() for item in short_items if str(item).strip()][:3]


class CaseRuntimeContextResolver:
    def resolve_from_case_dir(self, *, case_dir: Path) -> dict[str, Any]:
        resolved_case_dir = case_dir.expanduser().resolve()
        if not resolved_case_dir.exists() or not resolved_case_dir.is_dir():
            raise FileNotFoundError(f"Case directory not found: {resolved_case_dir}")

        case_payload = _read_json(resolved_case_dir / "case.json")
        if not case_payload:
            raise FileNotFoundError(f"Missing case.json in: {resolved_case_dir}")

        source_row_payload = _read_json(resolved_case_dir / "source_row.json")
        status_payload = _read_json(resolved_case_dir / "work" / "status.json")
        expander_payload = _read_json(resolved_case_dir / "work" / "01_expander.json")
        ocr_payload = _read_json(resolved_case_dir / "work" / "ocr.json")
        tnved_payload = _read_json(resolved_case_dir / "work" / "tnved.json")
        verification_payload = _read_json(resolved_case_dir / "work" / "verification.json")
        enrichment_payload = _read_json(resolved_case_dir / "work" / "enrichment.json")
        calculations_payload = _read_json(resolved_case_dir / "work" / "calculations.json")
        questions_payload = _read_json(resolved_case_dir / "work" / "questions.json")
        pipeline_result_payload = _read_json(resolved_case_dir / "result" / "pipeline_result.json")
        ui_response_payload = _read_json(resolved_case_dir / "result" / "ui_response.json")
        export_payload = _read_json(resolved_case_dir / "result" / "export.json")
        pipeline_questions_payload = (
            pipeline_result_payload.get("questions") if isinstance(pipeline_result_payload.get("questions"), dict) else {}
        )
        effective_questions_payload = questions_payload or pipeline_questions_payload

        current_case = {
            "case_id": case_payload.get("case_id", resolved_case_dir.name),
            "title_cn": case_payload.get("raw_name", "—"),
            "title_ru": (
                str((ocr_payload.get("text_ru") or "")).strip()
                or str((pipeline_result_payload.get("decision") or {}).get("selected_description") or "").strip()
                or "—"
            ),
            "text_cn": str(ocr_payload.get("text_cn", "")).strip() or str(case_payload.get("raw_name", "")).strip() or "—",
            "text_ru": str(ocr_payload.get("text_ru", "")).strip() or "—",
            "ocr_text": str(ocr_payload.get("ocr_text", "")).strip() or "—",
            "image_description": str(ocr_payload.get("image_description", "")).strip() or "—",
            "summary": {
                "tnved": str(tnved_payload.get("selected_code", "")).strip()
                or str((pipeline_result_payload.get("decision") or {}).get("selected_code", "")).strip()
                or "—",
                "posh": str((calculations_payload.get("customs") or {}).get("effective_duty_rate_text", "")).strip() or "—",
                "its": str((enrichment_payload.get("its") or {}).get("its_value", "")).strip()
                or str((enrichment_payload.get("its") or {}).get("status", "")).strip()
                or "—",
                "nds": str((calculations_payload.get("customs") or {}).get("effective_nds_rate_text", "")).strip() or "—",
                "stp": str((calculations_payload.get("stp") or {}).get("value", "")).strip()
                or str((calculations_payload.get("stp") or {}).get("status", "")).strip()
                or "—",
            },
            "code_options": tnved_payload.get("candidates") if isinstance(tnved_payload.get("candidates"), list) else [],
            "analysis_sections": [
                {
                    "title": "TNVED",
                    "value": str(tnved_payload.get("selection_rationale", "")).strip() or "—",
                },
                {
                    "title": "Verification",
                    "value": str(verification_payload.get("validation_status", "")).strip() or "—",
                },
            ],
            "support_sections": [
                {
                    "title": "IFCG",
                    "value": str((enrichment_payload.get("ifcg_verification") or {}).get("summary", "")).strip()
                    or str((enrichment_payload.get("ifcg_verification") or {}).get("status", "")).strip()
                    or "—",
                },
                {
                    "title": "ITS",
                    "value": str((enrichment_payload.get("its") or {}).get("status", "")).strip() or "—",
                },
                {
                    "title": "Sigma",
                    "value": str((enrichment_payload.get("sigma") or {}).get("status", "")).strip() or "—",
                },
            ],
            "questions": _extract_questions(effective_questions_payload),
            "question_items": _extract_question_items(effective_questions_payload),
            "work_stage": str(
                status_payload.get("last_completed_stage")
                or status_payload.get("current_stage")
                or "workbook_intake"
            ),
        }

        work_files = sorted(path.name for path in (resolved_case_dir / "work").glob("*.json")) if (resolved_case_dir / "work").exists() else []
        result_files = sorted(path.name for path in (resolved_case_dir / "result").glob("*.json")) if (resolved_case_dir / "result").exists() else []

        return {
            "root_path": str(resolved_case_dir.parent),
            "case_id": str(case_payload.get("case_id") or resolved_case_dir.name),
            "case_dir": str(resolved_case_dir),
            "case_payload": case_payload,
            "source_row_payload": source_row_payload,
            "status_payload": status_payload,
            "expander_payload": expander_payload,
            "ocr_payload": ocr_payload,
            "tnved_payload": tnved_payload,
            "verification_payload": verification_payload,
            "enrichment_payload": enrichment_payload,
            "calculations_payload": calculations_payload,
            "questions_payload": effective_questions_payload,
            "pipeline_result_payload": pipeline_result_payload,
            "ui_response_payload": ui_response_payload,
            "export_payload": export_payload,
            "current_case": current_case,
            "work_files": work_files,
            "result_files": result_files,
        }
