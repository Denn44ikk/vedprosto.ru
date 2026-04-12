from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from ....calculations.customs.models import CustomsCalculationInput
from ....calculations.customs.service import CustomsCalculationService
from ....calculations.eco_fee.service import EcoFeeService
from ....processing.ocr.service import OcrProcessingService
from ....reporting.shared import build_ifcg_panel
from ....storage.cases.service import CaseStorageService
from ....storage.runtime_state.service import RuntimeStateService
from ..analysis_placeholder_service import AnalysisPlaceholderService

_FALLBACK_NDS_RATE = 0.22
_FALLBACK_NDS_RATE_TEXT = "22%"


class WorkspaceReportingService:
    def __init__(
        self,
        *,
        runtime_state_service: RuntimeStateService,
        customs_service: CustomsCalculationService,
        eco_fee_service: EcoFeeService,
        ocr_processing_service: OcrProcessingService,
        analysis_placeholder_service: AnalysisPlaceholderService,
        case_storage_service: CaseStorageService,
    ) -> None:
        self.runtime_state_service = runtime_state_service
        self.customs_service = customs_service
        self.eco_fee_service = eco_fee_service
        self.ocr_processing_service = ocr_processing_service
        self.analysis_placeholder_service = analysis_placeholder_service
        self.case_storage_service = case_storage_service

    @staticmethod
    def _summary_value(*candidates: object, fallback: str) -> str:
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return fallback

    def review_status(self, root_path: Path, case_id: str) -> str:
        flags = self.runtime_state_service.get_case_flags(str(root_path), case_id)
        return str(flags.get("review_status", "pending"))

    def prefetch_status(self, root_path: Path, case_id: str) -> str:
        flags = self.runtime_state_service.get_case_flags(str(root_path), case_id)
        return str(flags.get("prefetch_status", "idle"))

    def ocr_state(self, root_path: Path, case_id: str) -> tuple[str, bool]:
        ocr_payload = self.case_storage_service.load_ocr_payload(root_path, case_id)
        if not isinstance(ocr_payload, dict) or not ocr_payload:
            return "idle", False

        status = str(ocr_payload.get("status", "")).strip().lower()
        result_fields = [
            str(ocr_payload.get("text_ru", "")).strip(),
            str(ocr_payload.get("ocr_text", "")).strip(),
            str(ocr_payload.get("image_description", "")).strip(),
        ]
        has_content = any(value and value != "—" for value in result_fields)

        if status in {"completed", "success", "done"}:
            return "completed", True
        if status in {"error", "failed"}:
            return "error", True
        if status in {"running", "processing"}:
            return "running", True
        if status in {"queued"}:
            return "queued", True
        if status in {"pending"}:
            return "idle", False
        if status in {"cancelled", "canceled", "stopped"}:
            return "cancelled", has_content
        return ("completed" if has_content else "idle"), has_content

    def build_case_list(self, root_path: Path, queue: list[dict], current_case_id: str) -> list[dict[str, object]]:
        cases: list[dict[str, object]] = []
        for item in queue:
            case_id = str(item.get("case_id", "")).strip()
            if not case_id:
                continue
            image_files = item.get("image_files") if isinstance(item.get("image_files"), list) else []
            ocr_status, ocr_has_content = self.ocr_state(root_path, case_id)
            pipeline_payload = self.case_storage_service.load_pipeline_result_payload(root_path, case_id)
            tnved_payload = self.case_storage_service.load_tnved_payload(root_path, case_id)
            verification_payload = self.case_storage_service.load_verification_payload(root_path, case_id)
            has_ai_result = self._case_has_analysis_result(
                ocr_has_content=ocr_has_content,
                pipeline_payload=pipeline_payload,
                tnved_payload=tnved_payload,
                verification_payload=verification_payload,
            )
            cases.append(
                {
                    "case_id": case_id,
                    "row_number": int(item.get("row_number", 0) or 0),
                    "row_span": str(item.get("row_span", "")),
                    "title": str(item.get("raw_name", "")).strip() or case_id,
                    "image_count": len(image_files),
                    "review_status": self.review_status(root_path, case_id),
                    "prefetch_status": self.prefetch_status(root_path, case_id),
                    "ocr_status": ocr_status,
                    "has_ai_result": has_ai_result,
                    "is_current": case_id == current_case_id,
                }
            )
        return cases

    def _build_source_fields(
        self,
        *,
        case_payload: dict,
        source_row_payload: dict,
        status_payload: dict,
        image_count: int,
    ) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        seen_labels: set[str] = set()

        cells = source_row_payload.get("cells")
        if isinstance(cells, list):
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                label = str(cell.get("header", "")).strip()
                if not label or label in seen_labels:
                    continue
                value = str(cell.get("value", "")).strip() or "—"
                seen_labels.add(label)
                result.append({"label": label, "value": value})

        fallback_fields = [
            ("Источник", self._summary_value(case_payload.get("source_file"), fallback="—")),
            ("Лист", self._summary_value(case_payload.get("sheet_name"), fallback="—")),
            ("Строки", self._summary_value(case_payload.get("row_span"), fallback="—")),
            ("Номер строки", str(int(case_payload.get("row_number", 0) or 0) or "—")),
            ("Фото", str(image_count)),
            ("Статус", self._summary_value(status_payload.get("status"), fallback="prepared")),
        ]
        for label, value in fallback_fields:
            if label in seen_labels:
                continue
            result.append({"label": label, "value": value})
        return result

    def _build_code_options(self, analysis_payload: dict | None) -> list[dict[str, object]]:
        branch_candidates = analysis_payload.get("branch_candidates") if isinstance(analysis_payload, dict) else []
        if not isinstance(branch_candidates, list):
            branch_candidates = []

        options: list[dict[str, object]] = []

        for index, branch in enumerate(branch_candidates):
            if not isinstance(branch, dict):
                continue
            code = str(branch.get("branch_code", "")).strip()
            if not code:
                continue
            priority = int(branch.get("priority_for_verification", index + 1) or index + 1)
            confidence_percent = max(41, min(92, 82 - (priority - 1) * 11 - index * 3))
            options.append(
                {
                    "option_key": f"{code}-{index}",
                    "code": code,
                    "confidence_percent": confidence_percent,
                    "level": str(branch.get("branch_level", "—")),
                    "branch_type": str(branch.get("branch_type", "—")),
                    "title": str(branch.get("group_path_ru", "")).strip() or code,
                    "why_alive": str(branch.get("why_alive_ru", "")).strip() or "Кандидат сохранен в legacy-кейсе из предыдущего анализа.",
                    "posh": "—",
                    "eco": self.eco_fee_service.preview_for_code(code=code, year=2026),
                    "its": "—",
                    "its_value": None,
                    "nds": "—",
                    "stp": "—",
                    "stp_value": None,
                    "priority": priority,
                }
            )

        options.sort(key=lambda item: int(item.get("priority", 999)))
        return options

    @staticmethod
    def _format_number(value: object, *, fallback: str = "—") -> str:
        if isinstance(value, (int, float)):
            return f"{float(value):.2f}".rstrip("0").rstrip(".")
        return fallback

    @staticmethod
    def _status_text(value: object, *, fallback: str = "pending") -> str:
        text = str(value or "").strip()
        return text or fallback

    @staticmethod
    def _extract_questions(question_payload: dict | None) -> tuple[list[str], list[dict[str, object]]]:
        payload = question_payload if isinstance(question_payload, dict) else {}
        top_items = payload.get("top") if isinstance(payload.get("top"), list) else []
        question_items: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        seen_questions: set[str] = set()

        for index, item in enumerate(top_items, start=1):
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            if not question:
                continue
            question_id = str(item.get("id", "")).strip() or f"question_{index}"
            lowered = question.casefold()
            if question_id in seen_ids or lowered in seen_questions:
                continue
            seen_ids.add(question_id)
            seen_questions.add(lowered)
            related_codes = item.get("related_codes") if isinstance(item.get("related_codes"), list) else []
            question_items.append(
                {
                    "id": question_id,
                    "question": question,
                    "why": str(item.get("why", "")).strip(),
                    "source_stage": str(item.get("source_stage", "")).strip(),
                    "priority": int(item.get("priority", index) or index),
                    "related_codes": [str(code).strip() for code in related_codes if str(code).strip()],
                    "status": str(item.get("status", "open") or "open").strip(),
                    "answer": str(item.get("answer", "")).strip(),
                }
            )

        questions = [str(item.get("question", "")).strip() for item in question_items if str(item.get("question", "")).strip()]
        if not questions:
            short_items = payload.get("short") if isinstance(payload.get("short"), list) else []
            questions = [str(item).strip() for item in short_items if str(item).strip()]
        return questions[:3], question_items[:3]

    @staticmethod
    def _its_status_label(value: object) -> str:
        status = str(value or "").strip().lower()
        mapping = {
            "ok": "ok",
            "disabled": "выключен",
            "no_its_in_bot": "Нет в боте",
            "need_14_digits": "Нужно 14 знаков",
            "pending": "pending",
            "not_configured": "не настроен",
            "session_invalid": "сессия невалидна",
            "transport_error": "ошибка транспорта",
            "timeout": "timeout",
            "reply_code_mismatch": "код не совпал",
            "unknown_response": "непонятный ответ",
            "worker_not_running": "worker not running",
            "batch_skipped_technical_outage": "ITS недоступен",
        }
        return mapping.get(status, status or "—")

    @staticmethod
    def _stp_status_label(value: object) -> str:
        status = str(value or "").strip().lower()
        if not status:
            return "—"
        mapping = {
            "calculated": "calculated",
            "manual_required_no_its_in_bot": "руками",
            "manual_required_non_percent_duty": "руками",
            "manual_required_non_percent_nds": "руками",
            "no_its_in_bot": "руками",
            "its_missing": "руками",
            "pending": "pending",
            "timeout": "timeout",
            "error": "error",
            "transport_error": "ошибка транспорта",
        }
        return mapping.get(status, status)

    def _its_view_text(self, payload: dict | None, *, fallback: str = "—") -> str:
        row = payload if isinstance(payload, dict) else {}
        value = row.get("its_value")
        if isinstance(value, (int, float)):
            return self._format_number(value)
        date_text = str(row.get("date_text", "")).strip()
        if date_text:
            return date_text
        status_label = self._its_status_label(row.get("status"))
        return status_label or fallback

    def _stp_view_text(self, payload: dict | None, *, fallback: str = "—") -> str:
        row = payload if isinstance(payload, dict) else {}
        value = row.get("stp_value", row.get("value"))
        if isinstance(value, (int, float)):
            return self._format_number(value)
        status_label = self._stp_status_label(row.get("stp_status") or row.get("status"))
        return status_label or fallback

    @staticmethod
    def _vbd_status_label(value: object) -> str:
        status = str(value or "").strip().lower()
        mapping = {
            "confirmed": "подтвержден",
            "needs_review": "нужна проверка",
            "no_signal": "слабый сигнал",
            "no_hits": "нет совпадений",
            "unavailable": "база пуста",
            "pending": "pending",
            "skipped": "skipped",
            "error": "error",
        }
        return mapping.get(status, status or "pending")

    def _build_tnved_vbd_view(self, payload: dict | None) -> dict[str, object] | None:
        row = payload if isinstance(payload, dict) else {}
        if not row:
            return None

        def _normalize_hits(items: object) -> list[dict[str, object]]:
            out: list[dict[str, object]] = []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                out.append(
                    {
                        "chunk_id": str(item.get("chunk_id", "")).strip(),
                        "source_path": str(item.get("source_path", "")).strip(),
                        "relative_path": str(item.get("relative_path", "")).strip(),
                        "source_kind": str(item.get("source_kind", "")).strip(),
                        "document_type": str(item.get("document_type", "")).strip(),
                        "section_context": str(item.get("section_context", "")).strip(),
                        "text": str(item.get("text", "")).strip(),
                        "score": float(item.get("score", 0) or 0),
                        "mentioned_codes": [str(code).strip() for code in item.get("mentioned_codes", []) if str(code).strip()],
                    }
                )
            return out

        return {
            "status": self._status_text(row.get("status"), fallback="pending"),
            "verification_status": self._status_text(row.get("verification_status"), fallback="pending"),
            "selected_code": str(row.get("selected_code", "")).strip(),
            "summary": str(row.get("summary", "")).strip(),
            "note": str(row.get("note", "")).strip(),
            "product_facts": [str(item).strip() for item in row.get("product_facts", []) if str(item).strip()],
            "reference_hits": _normalize_hits(row.get("reference_hits")),
            "example_hits": _normalize_hits(row.get("example_hits")),
            "alternative_codes": [str(item).strip() for item in row.get("alternative_codes", []) if str(item).strip()],
            "warnings": [str(item).strip() for item in row.get("warnings", []) if str(item).strip()],
            "index_status": str(row.get("index_status", "")).strip(),
        }

    def _build_tnved_vbd_support_value(self, payload: dict | None) -> str:
        row = payload if isinstance(payload, dict) else {}
        summary = str(row.get("summary", "")).strip()
        note = str(row.get("note", "")).strip()
        verification_status = self._vbd_status_label(row.get("verification_status") or row.get("status"))
        alternative_codes = row.get("alternative_codes") if isinstance(row.get("alternative_codes"), list) else []
        alternatives = ", ".join(str(code).strip() for code in alternative_codes if str(code).strip())
        if alternatives:
            return self._summary_value(summary, f"{verification_status}: {alternatives}", note, fallback="pending")
        return self._summary_value(summary, verification_status, note, fallback="pending")

    def _build_alternative_stp_payload(
        self,
        *,
        code: str,
        code_its_payload: dict,
        sigma_payload: dict,
        verification_duty_rates: dict[str, object],
    ) -> dict[str, object]:
        try:
            result = self.customs_service.build(
                CustomsCalculationInput(
                    code=code,
                    its_status=str(code_its_payload.get("status", "")).strip(),
                    its_value=code_its_payload.get("its_value"),
                    its_bracket_value=code_its_payload.get("its_bracket_value"),
                    primary_duty_rate_text=str(sigma_payload.get("duty_text", "")).strip() or None,
                    fallback_duty_rate_text=str(verification_duty_rates.get(code, "")).strip() or None,
                    primary_nds_rate_text=str(sigma_payload.get("vat_text", "")).strip() or None,
                    fallback_nds_rate=_FALLBACK_NDS_RATE,
                    fallback_nds_rate_text=_FALLBACK_NDS_RATE_TEXT,
                    notice_text="",
                )
            )
            return result.to_dict()
        except Exception:
            return {"stp_value": None, "stp_status": "error"}

    def _case_has_analysis_result(
        self,
        *,
        ocr_has_content: bool,
        pipeline_payload: dict,
        tnved_payload: dict,
        verification_payload: dict,
    ) -> bool:
        if self._pipeline_payload_has_analysis_result(pipeline_payload):
            return True
        if not ocr_has_content:
            return False
        if str(tnved_payload.get("selected_code", "")).strip():
            return True
        if isinstance(tnved_payload.get("candidates"), list) and bool(tnved_payload.get("candidates")):
            return True
        if str(tnved_payload.get("selection_rationale", "")).strip():
            return True
        if self._status_text(verification_payload.get("validation_status"), fallback="pending") not in {"pending", "idle", "empty"}:
            return True
        return False

    @staticmethod
    def _pipeline_payload_has_analysis_result(pipeline_payload: dict) -> bool:
        if not isinstance(pipeline_payload, dict) or not pipeline_payload:
            return False
        decision = pipeline_payload.get("decision") if isinstance(pipeline_payload.get("decision"), dict) else {}
        if str(decision.get("selected_code", "")).strip():
            return True
        if str(decision.get("selection_rationale", "")).strip():
            return True
        stages = pipeline_payload.get("stages") if isinstance(pipeline_payload.get("stages"), dict) else {}
        tnved = stages.get("tnved") if isinstance(stages.get("tnved"), dict) else {}
        verification = stages.get("verification") if isinstance(stages.get("verification"), dict) else {}
        if str(tnved.get("selected_code", "")).strip():
            return True
        if isinstance(tnved.get("candidates"), list) and bool(tnved.get("candidates")):
            return True
        if str(tnved.get("selection_rationale", "")).strip():
            return True
        if str(verification.get("final_code", "")).strip():
            return True
        return False

    def _build_stage_statuses(
        self,
        *,
        ocr_payload: dict,
        tnved_payload: dict,
        semantic_payload: dict,
        verification_payload: dict,
        tnved_vbd_payload: dict,
        ifcg_discovery_payload: dict,
        ifcg_verification_payload: dict,
        sigma_payload: dict,
        its_payload: dict,
        customs_payload: dict,
        eco_fee_payload: dict,
        status_payload: dict,
    ) -> dict[str, str]:
        tnved_status = self._status_text(tnved_payload.get("status"), fallback="")
        if not tnved_status:
            if str(tnved_payload.get("selected_code", "")).strip():
                tnved_status = "completed"
            elif isinstance(tnved_payload.get("candidates"), list) and bool(tnved_payload.get("candidates")):
                tnved_status = "completed"
            else:
                tnved_status = "pending"
        return {
            "ocr": self._status_text(ocr_payload.get("status"), fallback="idle"),
            "tnved": tnved_status,
            "semantic": self._status_text(
                semantic_payload.get("selected_status") or verification_payload.get("semantic_status"),
                fallback="pending",
            ),
            "verification": self._status_text(
                verification_payload.get("final_status") or verification_payload.get("validation_status"),
                fallback="pending",
            ),
            "tnved_vbd": self._status_text(
                tnved_vbd_payload.get("verification_status") or tnved_vbd_payload.get("status"),
                fallback="pending",
            ),
            "ifcg_discovery": self._status_text(ifcg_discovery_payload.get("status"), fallback="pending"),
            "ifcg_verification": self._status_text(ifcg_verification_payload.get("status"), fallback="pending"),
            "sigma": self._status_text(sigma_payload.get("status"), fallback="pending"),
            "its": self._status_text(its_payload.get("status"), fallback="pending"),
            "customs": self._status_text(customs_payload.get("status"), fallback="pending"),
            "eco_fee": self._status_text(eco_fee_payload.get("status"), fallback="pending"),
            "work": self._status_text(status_payload.get("status"), fallback="prepared"),
        }

    @staticmethod
    def _eco_packet_for_code(eco_fee_payload: dict, code: str) -> dict | None:
        packets = eco_fee_payload.get("by_code") if isinstance(eco_fee_payload, dict) else None
        if not isinstance(packets, list):
            return None
        for item in packets:
            if isinstance(item, dict) and str(item.get("code", "")).strip() == str(code).strip():
                return item
        return None

    def _build_workspace_eco_fee(self, *, codes: list[str]) -> dict[str, object] | None:
        packets: list[dict[str, object]] = []
        supported_years: list[int] = []
        for code in codes:
            normalized = str(code).strip()
            if not normalized:
                continue
            packet = self.eco_fee_service.build_code_packet(code=normalized, preferred_year=2026)
            packets.append({"code": normalized, **packet})
            if not supported_years:
                supported_years = [int(item) for item in packet.get("supported_years", []) if isinstance(item, int)]
        if not packets:
            return None
        return {
            "default_year": 2026,
            "supported_years": supported_years or [2026],
            "by_code": packets,
        }

    def _build_current_case_from_pipeline(
        self,
        *,
        root_path: Path,
        case_id: str,
        case_payload: dict,
        status_payload: dict,
        source_row_payload: dict,
        ocr_payload: dict,
        pipeline_payload: dict,
        questions_payload: dict,
    ) -> dict[str, object]:
        ocr_view = self.ocr_processing_service.build_analysis_view(
            case_payload=case_payload,
            source_row_payload=source_row_payload,
            ocr_payload=ocr_payload,
        )
        image_files = case_payload.get("image_files") if isinstance(case_payload.get("image_files"), list) else []
        if not image_files:
            media = case_payload.get("media")
            nested_image_files = media.get("image_files") if isinstance(media, dict) else []
            image_files = nested_image_files if isinstance(nested_image_files, list) else []
        images = []
        for image_file in image_files:
            image_name = Path(str(image_file)).name
            images.append(
                {
                    "name": image_name,
                    "url": f"/api/workspace/cases/{quote(case_id)}/images/{quote(image_name)}",
                }
            )

        source_table = self.ocr_processing_service.build_source_table(
            source_row_payload=source_row_payload,
            case_payload=case_payload,
        )
        source_fields = self._build_source_fields(
            case_payload=case_payload,
            source_row_payload=source_row_payload,
            status_payload=status_payload,
            image_count=len(images),
        )
        decision = pipeline_payload.get("decision") if isinstance(pipeline_payload.get("decision"), dict) else {}
        enrichment = pipeline_payload.get("enrichment") if isinstance(pipeline_payload.get("enrichment"), dict) else {}
        calculations = pipeline_payload.get("calculations") if isinstance(pipeline_payload.get("calculations"), dict) else {}
        stages = pipeline_payload.get("stages") if isinstance(pipeline_payload.get("stages"), dict) else {}
        tnved_stage = stages.get("tnved") if isinstance(stages.get("tnved"), dict) else {}
        semantic_stage = stages.get("semantic") if isinstance(stages.get("semantic"), dict) else {}
        verification_stage = stages.get("verification") if isinstance(stages.get("verification"), dict) else {}
        tnved_vbd_payload = (
            enrichment.get("tnved_vbd")
            if isinstance(enrichment.get("tnved_vbd"), dict)
            else (stages.get("tnved_vbd") if isinstance(stages.get("tnved_vbd"), dict) else {})
        )
        tnved_vbd_view = self._build_tnved_vbd_view(tnved_vbd_payload)
        ifcg_discovery = enrichment.get("ifcg_discovery") if isinstance(enrichment.get("ifcg_discovery"), dict) else {}
        ifcg_verification = enrichment.get("ifcg_verification") if isinstance(enrichment.get("ifcg_verification"), dict) else {}
        its_payload = enrichment.get("its") if isinstance(enrichment.get("its"), dict) else {}
        its_by_code = its_payload.get("by_code") if isinstance(its_payload.get("by_code"), dict) else {}
        sigma_payload = enrichment.get("sigma") if isinstance(enrichment.get("sigma"), dict) else {}
        customs_payload = calculations.get("customs") if isinstance(calculations.get("customs"), dict) else {}
        stp_payload = calculations.get("stp") if isinstance(calculations.get("stp"), dict) else {}
        eco_fee_payload = calculations.get("eco_fee") if isinstance(calculations.get("eco_fee"), dict) else {}
        effective_questions_payload = questions_payload if isinstance(questions_payload, dict) and questions_payload else (
            pipeline_payload.get("questions") if isinstance(pipeline_payload.get("questions"), dict) else {}
        )
        questions, question_items = self._extract_questions(effective_questions_payload)
        ifcg_panel = build_ifcg_panel(
            ifcg_discovery=ifcg_discovery,
            ifcg_verification=ifcg_verification,
            its_payload=its_payload,
        )
        selected_code = str(decision.get("selected_code", "")).strip()
        selected_description = str(decision.get("selected_description", "")).strip()
        selected_confidence = decision.get("confidence_percent")
        verification_descriptions = (
            verification_stage.get("descriptions") if isinstance(verification_stage.get("descriptions"), dict) else {}
        )
        verification_duty_rates = (
            verification_stage.get("duty_rates") if isinstance(verification_stage.get("duty_rates"), dict) else {}
        )
        candidate_rows = tnved_stage.get("candidates") if isinstance(tnved_stage.get("candidates"), list) else []
        all_code_candidates: list[str] = []
        if selected_code:
            all_code_candidates.append(selected_code)
        for candidate in candidate_rows:
            if isinstance(candidate, dict):
                candidate_code = str(candidate.get("code", "")).strip()
                if candidate_code and candidate_code not in all_code_candidates:
                    all_code_candidates.append(candidate_code)
        eco_fee_view = self._build_workspace_eco_fee(codes=all_code_candidates)
        code_options: list[dict[str, object]] = []
        for index, candidate in enumerate(candidate_rows, start=1):
            if not isinstance(candidate, dict):
                continue
            code = str(candidate.get("code", "")).strip()
            if not code:
                continue
            probability = candidate.get("probability_percent")
            confidence_percent = int(round(float(probability))) if isinstance(probability, (int, float)) else int(
                round(float(selected_confidence))
            ) if isinstance(selected_confidence, (int, float)) else max(40, 84 - index * 7)
            eco_packet_for_candidate = self._eco_packet_for_code(eco_fee_view or {}, code)
            candidate_eco = str(
                (eco_packet_for_candidate or {}).get("short_text")
                or self.eco_fee_service.preview_for_code(code=code, year=2026)
            )
            is_selected = code == selected_code
            code_its_payload = its_by_code.get(code) if isinstance(its_by_code.get(code), dict) else {}
            selected_its_value = code_its_payload.get("its_value")
            alternative_stp_payload = (
                {"stp_value": stp_payload.get("value"), "stp_status": stp_payload.get("status")}
                if is_selected
                else self._build_alternative_stp_payload(
                    code=code,
                    code_its_payload=code_its_payload,
                    sigma_payload=sigma_payload,
                    verification_duty_rates=verification_duty_rates,
                )
            )
            selected_stp_value = alternative_stp_payload.get("stp_value")
            code_options.append(
                {
                    "option_key": f"{code}-{index}",
                    "code": code,
                    "confidence_percent": confidence_percent,
                    "level": "10",
                    "branch_type": str(candidate.get("source", "") or "candidate"),
                    "title": str(candidate.get("title", "")).strip() or str(verification_descriptions.get(code, "")).strip() or code,
                    "why_alive": str(candidate.get("reason", "")).strip()
                    or str(decision.get("selection_rationale", "")).strip()
                    or "Кандидат сохранен после общего pipeline.",
                    "posh": (
                        str(customs_payload.get("effective_duty_rate_text", "")).strip()
                        if is_selected
                        else str(alternative_stp_payload.get("effective_duty_rate_text", "")).strip()
                        or str(verification_duty_rates.get(code, "")).strip()
                        or "—"
                    ),
                    "eco": candidate_eco,
                    "its": self._its_view_text(
                        code_its_payload if code_its_payload else (its_payload if is_selected else {}),
                        fallback="—",
                    ),
                    "its_value": selected_its_value,
                    "nds": (
                        str(customs_payload.get("effective_nds_rate_text", "")).strip()
                        if is_selected
                        else str(alternative_stp_payload.get("effective_nds_rate_text", "")).strip() or "—"
                    ),
                    "stp": self._stp_view_text(
                        alternative_stp_payload if isinstance(alternative_stp_payload, dict) else {},
                        fallback="—",
                    ),
                    "stp_value": selected_stp_value,
                    "priority": int(candidate.get("priority", index) or index),
                }
            )
        code_options.sort(key=lambda item: int(item.get("priority", 999)))

        summary = {
            "tnved": selected_code or "—",
            "posh": str(customs_payload.get("effective_duty_rate_text", "")).strip() or str(verification_duty_rates.get(selected_code, "")).strip() or "—",
            "eco": str(eco_fee_payload.get("short_text", "")).strip() or (self.eco_fee_service.preview_for_code(code=selected_code, year=2026) if selected_code else "—"),
            "its": self._its_view_text(its_payload, fallback="—"),
            "its_value": its_payload.get("its_value"),
            "nds": str(customs_payload.get("effective_nds_rate_text", "")).strip() or "—",
            "stp": self._stp_view_text(stp_payload, fallback="—"),
            "stp_value": stp_payload.get("value"),
            "declaration_description": self._summary_value(
                decision.get("selection_rationale"),
                selected_description,
                fallback="—",
            ),
            "label_text": self._summary_value(
                selected_description,
                ocr_view["text_ru"],
                case_payload.get("raw_name"),
                fallback="—",
            ),
        }

        semantic_reason = self._summary_value(
            semantic_stage.get("selected_operator_summary"),
            semantic_stage.get("reason"),
            fallback="Семантическая проверка еще не сформировала пояснение.",
        )
        verification_reason = self._summary_value(
            verification_stage.get("repair_reason_text"),
            verification_stage.get("repair_note"),
            verification_stage.get("error"),
            fallback="Финальная верификация завершена без дополнительного комментария.",
        )
        ifcg_summary = self._summary_value(
            ifcg_discovery.get("summary"),
            ifcg_discovery.get("operator_short_line"),
            fallback="IFCG discovery не дал дополнительного сигнала.",
        )
        ifcg_verification_summary = self._summary_value(
            ifcg_verification.get("summary"),
            ifcg_verification.get("operator_short_line"),
            fallback="IFCG verification не запускался.",
        )
        tnved_vbd_summary = self._build_tnved_vbd_support_value(tnved_vbd_payload)
        analysis_sections = [
            {"title": "TNVED", "value": self._summary_value(decision.get("selection_rationale"), selected_description, fallback="—")},
            {"title": "Semantic", "value": f"Статус: {self._summary_value(semantic_stage.get('selected_status'), fallback='—')}\n{semantic_reason}"},
            {"title": "Verification", "value": f"Статус: {self._summary_value(decision.get('final_status'), fallback='—')}\n{verification_reason}"},
            {"title": "TNVED VBD", "value": tnved_vbd_summary},
            {"title": "IFCG Discovery", "value": ifcg_summary},
            {"title": "IFCG Verification", "value": ifcg_verification_summary},
        ]
        analysis_highlights = [
            {"label": "ТН ВЭД", "value": summary["tnved"], "tone": "input"},
            {"label": "Статус", "value": self._summary_value(decision.get("final_status"), fallback="—"), "tone": "neutral"},
            {"label": "VBD", "value": self._vbd_status_label((tnved_vbd_payload or {}).get("verification_status") or (tnved_vbd_payload or {}).get("status")), "tone": "muted"},
            {"label": "Sigma", "value": self._summary_value(sigma_payload.get("status"), fallback="pending"), "tone": "muted"},
            {"label": "ITS", "value": self._summary_value(its_payload.get("status"), fallback="pending"), "tone": "muted"},
            {"label": "Эко", "value": self._summary_value(eco_fee_payload.get("status"), fallback="pending"), "tone": "muted"},
        ]
        support_sections = [
            {"title": "TNVED VBD", "value": tnved_vbd_summary},
            {"title": "Sigma", "value": self._summary_value(sigma_payload.get("duty_text"), sigma_payload.get("error_text"), sigma_payload.get("status"), fallback="pending")},
            {"title": "ITS", "value": self._summary_value(self._its_view_text(its_payload, fallback=""), its_payload.get("error_text"), fallback="pending")},
            {"title": "Customs / STP", "value": self._summary_value(customs_payload.get("effective_duty_rate_text"), stp_payload.get("status"), fallback="pending")},
            {"title": "Экосбор", "value": self._summary_value(eco_fee_payload.get("short_text"), eco_fee_payload.get("names_text"), eco_fee_payload.get("note"), eco_fee_payload.get("status"), fallback="pending")},
        ]
        stage_statuses = self._build_stage_statuses(
            ocr_payload=ocr_payload,
            tnved_payload=tnved_stage,
            semantic_payload=semantic_stage,
            verification_payload=verification_stage,
            tnved_vbd_payload=tnved_vbd_payload,
            ifcg_discovery_payload=ifcg_discovery,
            ifcg_verification_payload=ifcg_verification,
            sigma_payload=sigma_payload,
            its_payload=its_payload,
            customs_payload=customs_payload,
            eco_fee_payload=eco_fee_payload,
            status_payload=status_payload,
        )
        long_report = "\n\n".join(
            section["value"]
            for section in analysis_sections
            if isinstance(section, dict) and isinstance(section.get("value"), str) and section.get("value")
        )
        ocr_status, has_ai_result = self.ocr_state(root_path, case_id)
        source_rows = [int(item) for item in case_payload.get("source_rows", []) if isinstance(item, int)]
        return {
            "case_id": case_id,
            "row_number": int(case_payload.get("row_number", 0) or 0),
            "row_span": str(case_payload.get("row_span", "")),
            "source_rows": source_rows,
            "title_cn": ocr_view["title_cn"],
            "title_ru": self._summary_value(ocr_view["text_ru"], selected_description, fallback="—"),
            "text_cn": ocr_view["text_cn"],
            "text_ru": ocr_view["text_ru"],
            "ocr_text": ocr_view["ocr_text"],
            "image_description": ocr_view["image_description"],
            "images": images,
            "summary": summary,
            "code_options": code_options,
            "analysis_sections": analysis_sections,
            "analysis_highlights": analysis_highlights,
            "questions": questions,
            "question_items": question_items,
            "long_report": long_report,
            "source_fields": source_fields,
            "source_table": source_table,
            "support_sections": support_sections,
            "ifcg_panel": ifcg_panel,
            "stage_statuses": stage_statuses,
            "eco_fee": eco_fee_view,
            "tnved_vbd": tnved_vbd_view,
            "background_status": self.prefetch_status(root_path, case_id),
            "ocr_status": ocr_status,
            "has_ai_result": has_ai_result or bool(selected_code),
            "work_status": str(status_payload.get("status", "prepared")),
            "work_stage": str(
                status_payload.get("last_completed_stage")
                or status_payload.get("current_stage")
                or "workbook_intake"
            ),
        }

    def build_current_case(self, root_path: Path, case_id: str) -> dict[str, object] | None:
        if not case_id:
            return None

        case_payload, status_payload, analysis_payload = self.case_storage_service.load_case_payload(root_path, case_id)
        source_row_payload = self.case_storage_service.load_source_row_payload(root_path, case_id)
        ocr_payload = self.case_storage_service.load_ocr_payload(root_path, case_id)
        pipeline_payload = self.case_storage_service.load_pipeline_result_payload(root_path, case_id)
        questions_payload = self.case_storage_service.load_questions_payload(root_path, case_id)
        if not case_payload:
            return None
        if pipeline_payload:
            return self._build_current_case_from_pipeline(
                root_path=root_path,
                case_id=case_id,
                case_payload=case_payload,
                status_payload=status_payload,
                source_row_payload=source_row_payload,
                ocr_payload=ocr_payload,
                pipeline_payload=pipeline_payload,
                questions_payload=questions_payload,
            )

        product_identity = analysis_payload.get("product_identity_hypothesis") if isinstance(analysis_payload, dict) else {}
        if not isinstance(product_identity, dict):
            product_identity = {}

        analysis_summary = product_identity.get("summary_ru") if isinstance(product_identity.get("summary_ru"), str) else ""
        analysis_short = product_identity.get("short_label_ru") if isinstance(product_identity.get("short_label_ru"), str) else ""
        ocr_view = self.ocr_processing_service.build_analysis_view(
            case_payload=case_payload,
            source_row_payload=source_row_payload,
            ocr_payload=ocr_payload,
        )
        image_files = case_payload.get("image_files") if isinstance(case_payload.get("image_files"), list) else []
        if not image_files:
            media = case_payload.get("media")
            nested_image_files = media.get("image_files") if isinstance(media, dict) else []
            image_files = nested_image_files if isinstance(nested_image_files, list) else []
        images = []
        for image_file in image_files:
            image_name = Path(str(image_file)).name
            images.append(
                {
                    "name": image_name,
                    "url": f"/api/workspace/cases/{quote(case_id)}/images/{quote(image_name)}",
                }
            )

        source_table = self.ocr_processing_service.build_source_table(
            source_row_payload=source_row_payload,
            case_payload=case_payload,
        )
        code_options = self._build_code_options(analysis_payload if isinstance(analysis_payload, dict) else None)
        primary_option = code_options[0] if code_options else None

        support_sections = [
            {
                "title": "IFCG",
                "value": "Для legacy-кейса IFCG еще не запускался.",
            },
            {
                "title": "Sigma",
                "value": "Для legacy-кейса Sigma еще не запускалась.",
            },
            {
                "title": "ЧЗ",
                "value": "Проверка маркировки для legacy-кейса еще не запускалась.",
            },
            {
                "title": "Документы",
                "value": "Подбор документов для legacy-кейса еще не запускался.",
            },
        ]

        source_rows = [int(item) for item in case_payload.get("source_rows", []) if isinstance(item, int)]
        analysis_view = self.analysis_placeholder_service.build_payload(
            case_payload=case_payload,
            expander_payload=analysis_payload if isinstance(analysis_payload, dict) else None,
            image_count=len(images),
            source_row_labels=source_table.get("row_labels", []) if isinstance(source_table, dict) else [],
        )

        source_fields = self._build_source_fields(
            case_payload=case_payload,
            source_row_payload=source_row_payload,
            status_payload=status_payload,
            image_count=len(images),
        )
        ocr_status, has_ai_result = self.ocr_state(root_path, case_id)
        stage_statuses = self._build_stage_statuses(
            ocr_payload=ocr_payload,
            tnved_payload={},
            semantic_payload={},
            verification_payload={},
            tnved_vbd_payload={},
            ifcg_discovery_payload={},
            ifcg_verification_payload={},
            sigma_payload={},
            its_payload={},
            customs_payload={},
            eco_fee_payload={},
            status_payload=status_payload,
        )

        return {
            "case_id": case_id,
            "row_number": int(case_payload.get("row_number", 0) or 0),
            "row_span": str(case_payload.get("row_span", "")),
            "source_rows": source_rows,
            "title_cn": ocr_view["title_cn"],
            "title_ru": self._summary_value(
                ocr_view["text_ru"],
                analysis_short,
                analysis_summary,
                fallback="—",
            ),
            "text_cn": ocr_view["text_cn"],
            "text_ru": ocr_view["text_ru"],
            "ocr_text": ocr_view["ocr_text"],
            "image_description": ocr_view["image_description"],
            "images": images,
            "summary": {
                "tnved": str(primary_option.get("code", "—")) if primary_option else "—",
                "posh": str(primary_option.get("posh", "—")) if primary_option else "—",
                "eco": str(primary_option.get("eco", "—")) if primary_option else "—",
                "its": str(primary_option.get("its", "—")) if primary_option else "—",
                "its_value": primary_option.get("its_value") if primary_option else None,
                "nds": str(primary_option.get("nds", "—")) if primary_option else "—",
                "stp": str(primary_option.get("stp", "—")) if primary_option else "—",
                "stp_value": primary_option.get("stp_value") if primary_option else None,
                "declaration_description": self._summary_value(
                    analysis_summary,
                    analysis_short,
                    fallback="—",
                ),
                "label_text": self._summary_value(
                    analysis_short,
                    case_payload.get("raw_name"),
                    fallback="—",
                ),
            },
            "code_options": code_options,
            "analysis_sections": analysis_view["analysis_sections"],
            "analysis_highlights": analysis_view["analysis_highlights"],
            "questions": [],
            "question_items": [],
            "long_report": str(analysis_view["long_report"]),
            "source_fields": source_fields,
            "source_table": source_table,
            "support_sections": support_sections,
            "ifcg_panel": None,
            "stage_statuses": stage_statuses,
            "eco_fee": None,
            "tnved_vbd": None,
            "background_status": self.prefetch_status(root_path, case_id),
            "ocr_status": ocr_status,
            "has_ai_result": has_ai_result,
            "work_status": str(status_payload.get("status", "prepared")),
            "work_stage": str(
                status_payload.get("last_completed_stage")
                or status_payload.get("current_stage")
                or "workbook_intake"
            ),
        }

    @staticmethod
    def build_counters(cases: list[dict[str, object]]) -> dict[str, int]:
        saved = sum(1 for item in cases if item["review_status"] == "saved")
        skipped = sum(1 for item in cases if item["review_status"] == "skipped")
        pending = sum(1 for item in cases if item["review_status"] == "pending")
        return {
            "total": len(cases),
            "pending": pending,
            "saved": saved,
            "skipped": skipped,
        }
