from __future__ import annotations

import re
from typing import Any


class CaseReaderTool:
    @staticmethod
    def extract_relevant_codes(runtime_context: dict[str, Any], *, limit: int = 4) -> list[str]:
        current_case = runtime_context.get("current_case") if isinstance(runtime_context.get("current_case"), dict) else {}
        summary = current_case.get("summary") if isinstance(current_case.get("summary"), dict) else {}
        code_options = current_case.get("code_options") if isinstance(current_case.get("code_options"), list) else []

        codes: list[str] = []

        def _add(raw: object) -> None:
            normalized = re.sub(r"\D", "", str(raw or ""))
            if len(normalized) != 10 or normalized in codes:
                return
            codes.append(normalized)

        _add(summary.get("tnved"))
        for item in code_options:
            if not isinstance(item, dict):
                continue
            _add(item.get("code"))
            if len(codes) >= limit:
                break
        return codes[:limit]

    @staticmethod
    def build_case_digest(runtime_context: dict[str, Any]) -> dict[str, object]:
        current_case = runtime_context.get("current_case") if isinstance(runtime_context.get("current_case"), dict) else {}
        summary = current_case.get("summary") if isinstance(current_case.get("summary"), dict) else {}
        question_items = current_case.get("question_items") if isinstance(current_case.get("question_items"), list) else []
        return {
            "case_id": str(runtime_context.get("case_id") or ""),
            "case_dir": str(runtime_context.get("case_dir") or ""),
            "work_stage": str(current_case.get("work_stage") or ""),
            "selected_code": str(summary.get("tnved") or ""),
            "questions": [
                {
                    "id": str(item.get("id") or ""),
                    "question": str(item.get("question") or ""),
                    "answer": str(item.get("answer") or ""),
                }
                for item in question_items[:3]
                if isinstance(item, dict) and str(item.get("question") or "").strip()
            ],
        }
