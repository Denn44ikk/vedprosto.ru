from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any
from typing import Callable

from ...integrations.ai.service import AIIntegrationService
from .heuristics import (
    build_single_pass_image_description,
    choose_quality_decision,
    collapse_spaces,
    decide_ocr_retry,
    extract_json_dict,
    merge_ocr_text_into_image_description,
    needs_deep_ocr,
    normalize_quality_json,
    normalize_triage_json,
)
from .models import OcrQualityDecision
from .models import OcrRunInput
from .prompts import (
    TRANSLATE_NAME_PROMPT_RU,
    build_deep_ocr_prompt,
    build_forced_ocr_prompt,
    build_quality_check_prompt,
    build_triage_prompt,
)


NAME_HEADERS = ("Наименование", "Название", "Name", "product_name")
DESCRIPTION_HEADERS = ("Доп инфа", "Описание", "Description", "comment", "row_text")


class OcrProcessingService:
    def __init__(self, *, ai_integration_service: AIIntegrationService | None = None) -> None:
        self.ai_integration_service = ai_integration_service

    def _get_column_value(self, source_row_payload: dict[str, Any], candidates: tuple[str, ...]) -> str:
        columns = source_row_payload.get("columns")
        if not isinstance(columns, dict):
            return ""
        for header in candidates:
            value = columns.get(header)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def build_seed_payload(
        self,
        *,
        case_payload: dict[str, Any],
        source_row_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        source_row_payload = source_row_payload or {}
        text_cn = self._get_column_value(source_row_payload, NAME_HEADERS)
        if not text_cn:
            product = case_payload.get("product")
            if isinstance(product, dict):
                raw_name = product.get("raw_name")
                if isinstance(raw_name, str) and raw_name.strip():
                    text_cn = raw_name.strip()
        if not text_cn:
            raw_name = case_payload.get("raw_name")
            if isinstance(raw_name, str):
                text_cn = raw_name.strip()

        source_description = self._get_column_value(source_row_payload, DESCRIPTION_HEADERS)
        if not source_description:
            product = case_payload.get("product")
            if isinstance(product, dict):
                extra_info = product.get("extra_info")
                if isinstance(extra_info, str) and extra_info.strip():
                    source_description = extra_info.strip()
        if not source_description:
            extra_info = case_payload.get("extra_info")
            if isinstance(extra_info, str):
                source_description = extra_info.strip()

        return {
            "status": "pending",
            "error_text": "",
            "text_cn": text_cn,
            "text_ru": "",
            "ocr_text": "",
            "image_description": "",
            "source_description": source_description,
            "triage": {
                "item_name": text_cn,
                "is_marking_present": False,
                "is_text_readable": True,
                "complex_required": False,
                "reason": "",
            },
            "ocr_rounds": 0,
            "quality_check": {},
            "structured_attributes": {},
        }

    def normalize_payload(
        self,
        *,
        case_payload: dict[str, Any],
        source_row_payload: dict[str, Any] | None,
        ocr_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        seed = self.build_seed_payload(case_payload=case_payload, source_row_payload=source_row_payload)
        if not isinstance(ocr_payload, dict):
            return seed

        merged = dict(seed)
        merged.update({key: value for key, value in ocr_payload.items() if value is not None})
        triage = merged.get("triage")
        if not isinstance(triage, dict):
            merged["triage"] = seed["triage"]
        structured = merged.get("structured_attributes")
        if not isinstance(structured, dict):
            merged["structured_attributes"] = {}
        quality = merged.get("quality_check")
        if not isinstance(quality, dict):
            merged["quality_check"] = {}
        for key in ("status", "error_text", "text_cn", "text_ru", "ocr_text", "image_description", "source_description"):
            value = merged.get(key)
            merged[key] = value.strip() if isinstance(value, str) else seed.get(key, "")
        if not merged["ocr_text"] and merged["image_description"]:
            merged["ocr_text"] = merged["image_description"]
        return merged

    def build_source_table(self, source_row_payload: dict[str, Any] | None, case_payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(source_row_payload, dict):
            return {
                "status": "missing",
                "workbook_name": str(case_payload.get("source_file", "")).strip() or "—",
                "workbook_path": "",
                "sheet_name": str(case_payload.get("sheet_name", "")).strip() or "—",
                "row_labels": [f"стр. {int(case_payload.get('row_number', 0) or 0)}"],
                "note": "source_row.json пока не найден.",
                "fields": [],
            }

        workbook_name = str(source_row_payload.get("source_file", "")).strip() or "—"
        sheet_name = str(source_row_payload.get("sheet_name", "")).strip() or "—"
        row_number = int(source_row_payload.get("row_number", 0) or 0)
        cells = source_row_payload.get("cells")
        fields: list[dict[str, Any]] = []
        if isinstance(cells, list):
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                header = str(cell.get("header", "")).strip()
                if not header:
                    continue
                value = str(cell.get("value", "")).strip() or "—"
                fields.append({"label": header, "values": [value]})

        return {
            "status": "ready" if fields else "empty",
            "workbook_name": workbook_name,
            "workbook_path": "",
            "sheet_name": sheet_name,
            "row_labels": [f"стр. {row_number or 1}"],
            "note": f"{workbook_name} · {sheet_name} · стр. {row_number or 1}",
            "fields": fields,
        }

    def build_analysis_view(
        self,
        *,
        case_payload: dict[str, Any],
        source_row_payload: dict[str, Any] | None,
        ocr_payload: dict[str, Any] | None,
    ) -> dict[str, str]:
        normalized = self.normalize_payload(
            case_payload=case_payload,
            source_row_payload=source_row_payload,
            ocr_payload=ocr_payload,
        )
        return {
            "title_cn": normalized["text_cn"] or "Нет исходного названия",
            "text_cn": normalized["text_cn"] or "—",
            "text_ru": normalized["text_ru"] or "Перевод названия еще не готов.",
            "ocr_text": normalized["ocr_text"] or "OCR еще не запускался.",
            "image_description": normalized["image_description"] or normalized["ocr_text"] or "Подробный OCR еще не запускался.",
        }

    def _image_to_data_url(self, image_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(image_path.name)
        if not mime_type:
            mime_type = "application/octet-stream"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _build_multimodal_messages(self, *, prompt: str, image_paths: list[Path]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_path in image_paths[:5]:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._image_to_data_url(image_path),
                        "detail": "high",
                    },
                }
            )
        return [{"role": "user", "content": content}]

    def _chat_with_images(
        self,
        *,
        profile: str,
        prompt: str,
        image_paths: list[Path],
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 1800,
    ) -> str:
        if self.ai_integration_service is None:
            raise RuntimeError("AI integration service is not configured for OCR.")
        result = self.ai_integration_service.chat_sync(
            profile=profile,
            messages=self._build_multimodal_messages(prompt=prompt, image_paths=image_paths),
            response_format=response_format,
            max_tokens=max_tokens,
        )
        return str(result.text or "").strip()

    def _translate_name(self, *, text_cn: str, source_description: str, ocr_text: str) -> str:
        text_cn = text_cn.strip()
        if not text_cn:
            return ""
        if self.ai_integration_service is None:
            return ""
        prompt = (
            f"{TRANSLATE_NAME_PROMPT_RU}\n\n"
            f"Исходное название:\n{text_cn}\n\n"
            f"Контекст:\n{source_description or '—'}\n\n"
            f"OCR:\n{ocr_text or '—'}"
        )
        result = self.ai_integration_service.text_sync(
            profile="ocr_cheap",
            prompt=prompt,
            max_tokens=180,
        )
        return collapse_spaces(str(result.text or ""))

    def _run_quality_check(
        self,
        *,
        user_text: str,
        triage_json: dict[str, object],
        image_description: str,
    ) -> OcrQualityDecision | None:
        if self.ai_integration_service is None:
            return None
        raw = self.ai_integration_service.text_json_sync(
            profile="ocr_cheap",
            prompt=build_quality_check_prompt(
                user_text=user_text or None,
                triage_json=triage_json,
                image_description=image_description,
            ),
            max_tokens=280,
        )
        if isinstance(raw, dict):
            return normalize_quality_json(raw)
        return normalize_quality_json(extract_json_dict(str(raw or "")))

    @staticmethod
    def _ensure_not_cancelled(should_stop: Callable[[], bool] | None) -> None:
        if should_stop is not None and should_stop():
            raise RuntimeError("Подбор остановлен оператором.")

    def _collect_image_paths(self, *, case_dir: Path, case_payload: dict[str, Any]) -> list[Path]:
        candidates = case_payload.get("image_files")
        if not isinstance(candidates, list):
            media = case_payload.get("media")
            candidates = media.get("image_files") if isinstance(media, dict) else []

        paths: list[Path] = []
        for item in candidates or []:
            image_path = (case_dir / str(item)).resolve()
            if image_path.exists() and image_path.is_file():
                paths.append(image_path)
        if paths:
            return paths

        images_dir = case_dir / "images"
        if not images_dir.exists():
            return []
        return sorted(path for path in images_dir.iterdir() if path.is_file())

    def run_input_ocr(
        self,
        payload: OcrRunInput,
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        self._ensure_not_cancelled(should_stop)
        normalized = {
            "status": str(payload.existing_payload.get("status", "pending")),
            "error_text": str(payload.existing_payload.get("error_text", "")),
            "text_cn": str(payload.text_cn or "").strip(),
            "text_ru": str(payload.existing_text_ru or payload.existing_payload.get("text_ru", "")).strip(),
            "ocr_text": str(payload.existing_payload.get("ocr_text", "")).strip(),
            "image_description": str(payload.existing_payload.get("image_description", "")).strip(),
            "source_description": str(payload.source_description or payload.existing_payload.get("source_description", "")).strip(),
            "triage": payload.existing_payload.get("triage") if isinstance(payload.existing_payload.get("triage"), dict) else {
                "item_name": str(payload.text_cn or "").strip(),
                "is_marking_present": False,
                "is_text_readable": True,
                "complex_required": False,
                "reason": "",
            },
            "ocr_rounds": int(payload.existing_payload.get("ocr_rounds", 0) or 0),
            "quality_check": payload.existing_payload.get("quality_check") if isinstance(payload.existing_payload.get("quality_check"), dict) else {},
            "structured_attributes": payload.existing_payload.get("structured_attributes") if isinstance(payload.existing_payload.get("structured_attributes"), dict) else {},
        }

        text_cn = normalized["text_cn"]
        source_description = normalized["source_description"]
        user_text = "\n".join(part for part in (text_cn, source_description) if part).strip()
        image_paths = list(payload.image_paths)

        if not image_paths:
            self._ensure_not_cancelled(should_stop)
            text_ru = normalized["text_ru"] or self._translate_name(
                text_cn=text_cn,
                source_description=source_description,
                ocr_text=source_description,
            )
            return {
                **normalized,
                "status": "completed",
                "text_ru": text_ru,
                "ocr_text": source_description,
                "image_description": source_description,
                "ocr_rounds": 0,
                "quality_check": {
                    "reviewer": "no_images_mode",
                    "retry_required": False,
                    "reason": "source_description_only",
                    "confidence": "medium",
                    "has_concrete_data": bool(source_description.strip()),
                },
                "error_text": "",
            }

        triage_prompt = build_triage_prompt(user_text=user_text or None)
        self._ensure_not_cancelled(should_stop)
        triage_raw = self._chat_with_images(
            profile="ocr_exp",
            prompt=triage_prompt,
            image_paths=image_paths,
            response_format={"type": "json_object"},
            max_tokens=700,
        )
        self._ensure_not_cancelled(should_stop)
        triage_json = normalize_triage_json(extract_json_dict(triage_raw))

        deep_required = needs_deep_ocr(user_text or None, triage_json)
        ocr_text = build_single_pass_image_description(triage_json)
        if deep_required:
            self._ensure_not_cancelled(should_stop)
            image_description = self._chat_with_images(
                profile="ocr_exp",
                prompt=build_deep_ocr_prompt(user_text=user_text or None, triage_json=triage_json),
                image_paths=image_paths,
                max_tokens=2200,
            )
            ocr_rounds = 1
        else:
            image_description = ocr_text
            ocr_rounds = 0

        self._ensure_not_cancelled(should_stop)
        fallback_quality = decide_ocr_retry(
            ocr_rounds=ocr_rounds,
            image_description=image_description,
            selection_rationale=user_text,
        )
        self._ensure_not_cancelled(should_stop)
        ai_quality = self._run_quality_check(
            user_text=user_text,
            triage_json=triage_json,
            image_description=image_description,
        )
        quality = choose_quality_decision(
            ai_decision=ai_quality,
            fallback_decision=fallback_quality,
        )
        if quality.retry_required:
            self._ensure_not_cancelled(should_stop)
            forced_text = self._chat_with_images(
                profile="ocr_exp",
                prompt=build_forced_ocr_prompt(user_text=user_text or None, triage_json=triage_json),
                image_paths=image_paths,
                max_tokens=2200,
            )
            image_description = merge_ocr_text_into_image_description(
                image_description=image_description,
                ocr_text=forced_text,
            )
            ocr_rounds = max(ocr_rounds, 1) + 1

        self._ensure_not_cancelled(should_stop)
        text_ru = normalized["text_ru"] or self._translate_name(
            text_cn=text_cn,
            source_description=source_description,
            ocr_text=image_description,
        )

        return {
            **normalized,
            "status": "completed",
            "error_text": "",
            "text_ru": text_ru,
            "ocr_text": ocr_text.strip(),
            "image_description": image_description.strip(),
            "triage": triage_json,
            "ocr_rounds": ocr_rounds,
            "quality_check": {
                "reviewer": quality.reviewer,
                "retry_required": quality.retry_required,
                "reason": quality.reason,
                "confidence": quality.confidence,
                "has_concrete_data": quality.has_concrete_data,
                "fallback_reason": fallback_quality.reason,
            },
        }

    def _write_payload(self, *, case_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
        target = case_dir / "work" / "ocr.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _update_status(self, *, case_dir: Path, success: bool | None, error_text: str = "") -> None:
        status_path = case_dir / "work" / "status.json"
        payload: dict[str, Any] = {}
        if status_path.exists():
            try:
                parsed = json.loads(status_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}

        payload["current_stage"] = "ocr"
        if success is True:
            payload["last_completed_stage"] = "ocr"
            payload["status"] = "ocr_completed"
            payload["failed_stage"] = ""
            payload["error_text"] = ""
        elif success is None:
            payload["status"] = "ocr_cancelled"
            payload["failed_stage"] = ""
            payload["error_text"] = error_text
        else:
            payload["status"] = "ocr_error"
            payload["failed_stage"] = "ocr"
            payload["error_text"] = error_text
        status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def seed_case_file(
        self,
        *,
        case_dir: Path,
        case_payload: dict[str, Any],
        source_row_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = self.build_seed_payload(case_payload=case_payload, source_row_payload=source_row_payload)
        return self._write_payload(case_dir=case_dir, payload=payload)

    def run_case_ocr(
        self,
        *,
        case_dir: Path,
        case_payload: dict[str, Any],
        source_row_payload: dict[str, Any] | None,
        existing_payload: dict[str, Any] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_payload(
            case_payload=case_payload,
            source_row_payload=source_row_payload,
            ocr_payload=existing_payload,
        )
        request = OcrRunInput(
            text_cn=normalized["text_cn"],
            source_description=normalized["source_description"],
            image_paths=self._collect_image_paths(case_dir=case_dir, case_payload=case_payload),
            existing_text_ru=normalized["text_ru"],
            existing_payload=normalized,
        )
        try:
            self._write_payload(case_dir=case_dir, payload={**normalized, "status": "running", "error_text": ""})
            payload = self.run_input_ocr(request, should_stop=should_stop)
            self._write_payload(case_dir=case_dir, payload=payload)
            self._update_status(case_dir=case_dir, success=True)
            return payload
        except Exception as exc:
            is_cancelled = "остановлен оператором" in str(exc).lower()
            payload = {
                **normalized,
                "status": "cancelled" if is_cancelled else "error",
                "error_text": str(exc),
            }
            self._write_payload(case_dir=case_dir, payload=payload)
            self._update_status(case_dir=case_dir, success=None if is_cancelled else False, error_text=str(exc))
            return payload


__all__ = ["OcrProcessingService"]
