from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ...calculations.customs import CustomsCalculationService
from ...calculations.eco_fee.service import EcoFeeService
from ...integrations.ifcg import IfcgDiscoveryOutput, IfcgInput, IfcgOutput, IfcgService
from ...integrations.its.models import ITSFetchResult
from ...integrations.its.service import ITSService
from ...integrations.sigma.models import SigmaPaycalcResult
from ...integrations.sigma.service import SigmaService
from ...processing.semantic import SemanticInput, SemanticOutput, SemanticService
from ...processing.tnved.models import (
    TnvedClarificationQuestion,
    TnvedIfcgDiscoveryHint,
    TnvedInput,
    TnvedObservedAttributes,
    TnvedOutput,
)
from ...processing.tnved.service import TnvedService
from ...processing.tnved_vbd import TnvedVbdInput, TnvedVbdOutput, TnvedVbdService
from ...processing.verification import VerificationInput, VerificationOutput, VerificationService
from ...storage.knowledge.catalogs import TnvedCatalogService, TnvedCatalogSnapshot, normalize_code_10

_FALLBACK_NDS_RATE = 0.22
_FALLBACK_NDS_RATE_TEXT = "22%"


_MATERIAL_FACT_KEYS = frozenset(
    {
        "material",
        "materials",
        "material_ru",
        "composition",
        "состав",
        "материал",
        "материалы",
    }
)


def _collapse_spaces(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_string_list(value: object, *, limit: int = 12) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, tuple):
        raw_items = list(value)
    elif value is None:
        raw_items = []
    else:
        raw_items = [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = _collapse_spaces(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized[:240])
        if len(out) >= limit:
            break
    return out


def _normalize_product_facts(structured_attributes: object) -> dict[str, list[str]]:
    if not isinstance(structured_attributes, dict):
        return {}
    result: dict[str, list[str]] = {}
    for raw_key, raw_value in structured_attributes.items():
        key = _collapse_spaces(raw_key)
        if not key:
            continue
        normalized_values = _normalize_string_list(raw_value)
        if normalized_values:
            result[key] = normalized_values
    return result


def _build_observed_attributes(product_facts: dict[str, list[str]]) -> TnvedObservedAttributes:
    materials: list[str] = []
    material_evidence: list[str] = []
    seen_materials: set[str] = set()
    for key, values in product_facts.items():
        if _collapse_spaces(key).lower() not in _MATERIAL_FACT_KEYS:
            continue
        for value in values:
            if value not in seen_materials:
                seen_materials.add(value)
                materials.append(value)
            material_evidence.append(f"{key}: {value}"[:240])
    return TnvedObservedAttributes(
        materials=tuple(materials[:8]),
        material_evidence=tuple(material_evidence[:8]),
        uncertain_materials=tuple(),
    )


def _build_input_snapshot(ocr_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = ocr_payload if isinstance(ocr_payload, dict) else {}
    image_paths = payload.get("image_paths") if isinstance(payload.get("image_paths"), list) else []
    structured_attributes = _normalize_product_facts(payload.get("structured_attributes"))
    return {
        "item_name": _collapse_spaces(payload.get("text_ru"))
        or _collapse_spaces(payload.get("text_cn"))
        or _collapse_spaces(payload.get("source_description")),
        "text_cn": _collapse_spaces(payload.get("text_cn")),
        "text_ru": _collapse_spaces(payload.get("text_ru")),
        "ocr_text": _collapse_spaces(payload.get("ocr_text")),
        "image_description": _collapse_spaces(payload.get("image_description")),
        "source_description": _collapse_spaces(payload.get("source_description")),
        "image_paths": [str(item).strip() for item in image_paths if str(item).strip()],
        "triage": payload.get("triage") if isinstance(payload.get("triage"), dict) else {},
        "structured_attributes": structured_attributes,
    }


def build_tnved_input_from_ocr_payload(
    ocr_payload: dict[str, Any] | None,
    *,
    web_hint_text: str = "",
) -> TnvedInput:
    payload = ocr_payload if isinstance(ocr_payload, dict) else {}
    text_cn = _collapse_spaces(payload.get("text_cn"))
    text_ru = _collapse_spaces(payload.get("text_ru"))
    ocr_text = _collapse_spaces(payload.get("ocr_text"))
    image_description = _collapse_spaces(payload.get("image_description")) or ocr_text
    source_description = _collapse_spaces(payload.get("source_description"))
    product_facts = _normalize_product_facts(payload.get("structured_attributes"))
    observed_attributes = _build_observed_attributes(product_facts)
    item_name = text_ru or text_cn or source_description
    user_text = "\n".join(
        part for part in (text_cn, text_ru, source_description, ocr_text, image_description) if part
    ).strip()
    triage_payload = payload.get("triage") if isinstance(payload.get("triage"), dict) else {}
    return TnvedInput(
        item_name=item_name,
        image_description=image_description,
        user_text=user_text,
        triage_payload=triage_payload,
        web_hint_text=_collapse_spaces(web_hint_text),
        product_facts=product_facts,
        observed_attributes=observed_attributes,
        ifcg_discovery=None,
    )


def _build_evidence_summary(run_input: TnvedInput, tnved_output: TnvedOutput) -> str:
    lines: list[str] = []
    if run_input.item_name:
        lines.append(f"Товар: {run_input.item_name}")
    if run_input.user_text:
        lines.append(f"Контекст: {run_input.user_text[:1600]}")
    if tnved_output.compacted_image_description:
        lines.append(f"Compacted OCR: {tnved_output.compacted_image_description[:1400]}")
    if tnved_output.selection_rationale:
        lines.append(f"Предварительная логика выбора: {tnved_output.selection_rationale[:900]}")
    if tnved_output.candidates:
        candidate_lines = []
        for candidate in tnved_output.candidates[:6]:
            probability = (
                f", вероятность={candidate.probability_percent:g}%"
                if candidate.probability_percent is not None
                else ""
            )
            reason = f", why={candidate.reason[:180]}" if candidate.reason else ""
            candidate_lines.append(f"{candidate.code}{probability}{reason}")
        if candidate_lines:
            lines.append("Кандидаты: " + "; ".join(candidate_lines))
    return "\n".join(line for line in lines if line).strip()


def _candidate_codes(tnved_output: TnvedOutput) -> list[str]:
    ordered = [tnved_output.selected_code] + [candidate.code for candidate in tnved_output.candidates]
    out: list[str] = []
    seen: set[str] = set()
    for code in ordered:
        normalized = normalize_code_10(code)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _merge_unique_codes(*groups: object, limit: int = 8) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if isinstance(group, (list, tuple)):
            raw_items = group
        elif group is None:
            raw_items = ()
        else:
            raw_items = (group,)
        for item in raw_items:
            normalized = normalize_code_10(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
            if len(out) >= limit:
                return out
    return out


def _build_descriptions(
    *,
    codes: list[str],
    tnved_output: TnvedOutput,
    catalog: TnvedCatalogSnapshot | None,
) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    if catalog is not None:
        for code in codes:
            description = _collapse_spaces(catalog.descriptions.get(code))
            if description:
                descriptions[code] = description
    if tnved_output.selected_code and tnved_output.selected_description:
        descriptions.setdefault(tnved_output.selected_code, tnved_output.selected_description)
    return descriptions


def _today_sigma_query_date() -> str:
    return datetime.now().strftime("%d.%m.%y")


def _normalize_question_id(value: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9а-яА-Я_]+", "_", value.strip())
    compact = compact.strip("_").lower()
    return compact[:48] or "question"


def _normalize_question_text(value: object) -> str:
    text = _collapse_spaces(value)
    text = re.sub(r"^(не подтверждено:|требуется подтверждение,?)+\s*", "", text, flags=re.IGNORECASE)
    if not text:
        return ""
    if text.endswith("?"):
        return text
    lowered = text.casefold()
    if lowered.startswith(("какой ", "какая ", "какие ", "каково ", "из ", "есть ли ", "это ", "подтвердите ")):
        return text + "?"
    return f"Уточните: {text}?"


def _question_from_fact(fact: object) -> str:
    return _normalize_question_text(fact)


def _append_question_item(
    out: list[dict[str, Any]],
    *,
    seen: set[str],
    question: object,
    why: object = "",
    source_stage: str,
    priority: int,
    related_codes: list[str] | tuple[str, ...] = (),
    max_items: int = 3,
) -> None:
    text = _normalize_question_text(question)
    if not text:
        return
    key = text.casefold()
    if key in seen:
        return
    seen.add(key)
    normalized_codes = [code for code in (_merge_unique_codes(related_codes, limit=4)) if code]
    item = {
        "id": f"{source_stage}_{priority}_{_normalize_question_id(text)}",
        "question": text[:240],
        "why": _collapse_spaces(why)[:280],
        "source_stage": source_stage,
        "priority": max(1, int(priority)),
        "related_codes": normalized_codes,
        "status": "open",
        "answer": "",
    }
    out.append(item)
    out.sort(key=lambda row: (int(row.get("priority", 99)), str(row.get("question", "")).casefold()))
    del out[max_items:]


def _build_questions_payload(
    *,
    tnved_output: TnvedOutput | None,
    semantic_output: SemanticOutput | None,
    verification_output: VerificationOutput | None,
    final_code: str,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    related_codes = [final_code] + [candidate.code for candidate in (tnved_output.candidates if tnved_output is not None else ())]
    if tnved_output is not None:
        for index, question in enumerate(tnved_output.clarification_questions, start=1):
            _append_question_item(
                items,
                seen=seen,
                question=question.question,
                why=question.why or question.missing_fact,
                source_stage=question.source_stage or "tnved",
                priority=question.priority or index,
                related_codes=related_codes,
            )
    if semantic_output is not None:
        preferred_evaluations = [
            item for item in semantic_output.evaluations if item.code == (semantic_output.selected_code or final_code)
        ] or list(semantic_output.evaluations)
        for evaluation in preferred_evaluations[:2]:
            for index, fact in enumerate(evaluation.missing_facts[:2], start=1):
                _append_question_item(
                    items,
                    seen=seen,
                    question=_question_from_fact(fact),
                    why=evaluation.difference_for_operator or evaluation.why or semantic_output.reason,
                    source_stage="semantic",
                    priority=10 + index,
                    related_codes=[evaluation.code],
                )
            for index, fact in enumerate(evaluation.contradictions[:1], start=1):
                _append_question_item(
                    items,
                    seen=seen,
                    question=_question_from_fact(fact),
                    why=evaluation.why or semantic_output.reason,
                    source_stage="semantic",
                    priority=20 + index,
                    related_codes=[evaluation.code],
                )
    if verification_output is not None and len(items) < 3:
        verification_prompts = {
            "NOT_LEAF": "Какая именно подкатегория или модификация товара указана в документах?",
            "NOT_FOUND": "Есть ли в документах более точное коммерческое наименование или артикул товара?",
            "OBSOLETE_OR_MISSING": "Есть ли точный артикул, модель или спецификация, чтобы выбрать актуальный код?",
            "NOT_10_DIGIT": "Какой точный 10-значный код или официальное описание товара указаны в документах?",
        }
        question_text = verification_prompts.get(verification_output.error_code)
        if question_text:
            _append_question_item(
                items,
                seen=seen,
                question=question_text,
                why=verification_output.error or verification_output.repair_reason_text,
                source_stage="verification",
                priority=30,
                related_codes=[final_code] + list(verification_output.candidate_pool_fixed),
            )
    return {
        "status": "ready" if items else "empty",
        "count": len(items),
        "top": items[:3],
        "short": [str(item.get("question", "")).strip() for item in items[:3] if str(item.get("question", "")).strip()],
        "answers": [],
    }


@dataclass(frozen=True)
class CasePipelineResult:
    status: str
    final_code: str
    final_description: str
    final_status: str
    operator_summary: str
    warnings: tuple[str, ...] = ()
    error_text: str = ""
    input_snapshot: dict[str, Any] = field(default_factory=dict)
    questions_payload: dict[str, Any] = field(default_factory=dict)
    tnved: TnvedOutput | None = None
    semantic: SemanticOutput | None = None
    verification: VerificationOutput | None = None
    tnved_vbd: TnvedVbdOutput | None = None
    ifcg_discovery: IfcgDiscoveryOutput | None = None
    ifcg_verification: IfcgOutput | None = None
    sigma_payload: dict[str, Any] = field(default_factory=dict)
    its_payload: dict[str, Any] = field(default_factory=dict)
    customs_payload: dict[str, Any] = field(default_factory=dict)
    eco_fee_payload: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class PipelineCancelledError(RuntimeError):
    pass


ProgressCallback = Callable[[str, CasePipelineResult], None]


class CasePipelineService:
    def __init__(
        self,
        *,
        tnved_service: TnvedService,
        semantic_service: SemanticService,
        verification_service: VerificationService,
        tnved_vbd_service: TnvedVbdService | None = None,
        catalog_service: TnvedCatalogService,
        ifcg_service: IfcgService | None = None,
        sigma_service: SigmaService | None = None,
        its_service: ITSService | None = None,
        customs_service: CustomsCalculationService | None = None,
        eco_fee_service: EcoFeeService | None = None,
        prefer_catalog_db: bool = True,
    ) -> None:
        self._tnved_service = tnved_service
        self._semantic_service = semantic_service
        self._verification_service = verification_service
        self._tnved_vbd_service = tnved_vbd_service
        self._catalog_service = catalog_service
        self._ifcg_service = ifcg_service
        self._sigma_service = sigma_service
        self._its_service = its_service
        self._customs_service = customs_service
        self._eco_fee_service = eco_fee_service
        self._prefer_catalog_db = prefer_catalog_db

    @staticmethod
    def _run_sync(awaitable: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("Use async case pipeline methods inside an active event loop.")

    @staticmethod
    def _is_stop_requested(should_stop: Callable[[], bool] | None) -> bool:
        if should_stop is None:
            return False
        try:
            return bool(should_stop())
        except Exception:
            return False

    def _raise_if_stop_requested(self, should_stop: Callable[[], bool] | None) -> None:
        if self._is_stop_requested(should_stop):
            raise PipelineCancelledError("Pipeline stopped by operator.")

    @staticmethod
    def _external_stage_timeout_sec(name: str, default: float) -> float:
        raw = str(os.getenv(name, "") or "").strip()
        if not raw:
            return float(default)
        try:
            return max(5.0, float(raw.replace(",", ".")))
        except Exception:
            return float(default)

    def _ifcg_timeout_sec(self) -> float:
        client = getattr(self._ifcg_service, "_client", None)
        client_timeout = float(getattr(client, "_timeout_sec", 20) or 20) if client is not None else 20.0
        return self._external_stage_timeout_sec("PIPELINE_IFCG_TIMEOUT_SEC", min(90.0, max(20.0, client_timeout * 3.0)))

    def _sigma_timeout_sec(self) -> float:
        config = getattr(self._sigma_service, "config", None)
        timeout_sec = float(getattr(config, "timeout_sec", 30) or 30) if config is not None else 30.0
        retries = int(getattr(config, "max_retries", 3) or 3) if config is not None else 3
        delay_sec = float(getattr(config, "delay_sec", 1.0) or 1.0) if config is not None else 1.0
        computed = (timeout_sec * max(1, min(retries, 2))) + (delay_sec * max(0, retries - 1)) + 5.0
        return self._external_stage_timeout_sec("PIPELINE_SIGMA_TIMEOUT_SEC", min(90.0, max(15.0, computed)))

    def _its_timeout_sec(self) -> float:
        config = getattr(self._its_service, "config", None)
        timeout_sec = float(getattr(config, "timeout_sec", 10) or 10) if config is not None else 10.0
        retries = int(getattr(config, "max_retries", 3) or 3) if config is not None else 3
        delay_sec = float(getattr(config, "delay_sec", 3.0) or 3.0) if config is not None else 3.0
        computed = (timeout_sec * max(1, min(retries, 2))) + (delay_sec * max(0, retries - 1)) + 10.0
        return self._external_stage_timeout_sec("PIPELINE_ITS_TIMEOUT_SEC", min(120.0, max(60.0, computed)))

    @staticmethod
    def _emit_progress(
        stage: str,
        result: CasePipelineResult,
        progress_callback: ProgressCallback | None,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(stage, result)

    async def analyze_ocr_payload(
        self,
        ocr_payload: dict[str, Any] | None,
        *,
        web_hint_text: str = "",
        progress_callback: ProgressCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> CasePipelineResult:
        run_input = build_tnved_input_from_ocr_payload(ocr_payload, web_hint_text=web_hint_text)
        input_snapshot = _build_input_snapshot(ocr_payload)
        if not (run_input.item_name or run_input.user_text or run_input.image_description):
            return CasePipelineResult(
                status="skipped",
                final_code="",
                final_description="",
                final_status="empty_input",
                operator_summary="",
                warnings=("empty_ocr_payload",),
                error_text="Нет данных OCR для подбора ТН ВЭД.",
                input_snapshot=input_snapshot,
                questions_payload={"status": "empty", "count": 0, "top": [], "short": [], "answers": []},
                trace={"skipped": True},
            )

        self._raise_if_stop_requested(should_stop)
        catalog_snapshot, catalog_trace = self._catalog_service.build_runtime_snapshot(
            prefer_database=self._prefer_catalog_db
        )
        ifcg_discovery: IfcgDiscoveryOutput | None = None
        discovery_warnings: list[str] = []
        if self._ifcg_service is not None:
            try:
                discovery_input = self._ifcg_service.build_discovery_input_from_ocr_payload(ocr_payload)
                ifcg_discovery = await asyncio.wait_for(
                    self._ifcg_service.analyze_discovery(discovery_input),
                    timeout=self._ifcg_timeout_sec(),
                )
                if ifcg_discovery.status != "empty":
                    run_input.ifcg_discovery = TnvedIfcgDiscoveryHint(
                        summary=ifcg_discovery.summary,
                        suggested_groups=ifcg_discovery.suggested_groups,
                        suggested_codes=ifcg_discovery.suggested_codes,
                        broad_queries=ifcg_discovery.broad_queries,
                        warnings=ifcg_discovery.warnings,
                        raw=ifcg_discovery.to_payload(),
                    )
                if ifcg_discovery.error:
                    discovery_warnings.append(f"ifcg_discovery:{ifcg_discovery.error}")
            except asyncio.TimeoutError:
                ifcg_discovery = IfcgDiscoveryOutput(
                    status="error",
                    summary="IFCG discovery превысил лимит времени.",
                    suggested_groups=(),
                    suggested_codes=(),
                    broad_queries=(),
                    top_codes=(),
                    operator_short_line="IFCG discovery: timeout",
                    operator_long_lines=("IFCG discovery не завершился вовремя.",),
                    used=False,
                    warnings=("timeout",),
                    error=f"timeout_after_{int(self._ifcg_timeout_sec())}_sec",
                    trace={"timeout_sec": self._ifcg_timeout_sec()},
                )
                discovery_warnings.append("ifcg_discovery:timeout")
            except asyncio.CancelledError:
                ifcg_discovery = IfcgDiscoveryOutput(
                    status="error",
                    summary="IFCG discovery was cancelled.",
                    suggested_groups=(),
                    suggested_codes=(),
                    broad_queries=(),
                    top_codes=(),
                    operator_short_line="IFCG discovery: cancelled",
                    operator_long_lines=("IFCG discovery was cancelled before it completed.",),
                    used=False,
                    warnings=("cancelled",),
                    error="cancelled",
                    trace={"cancelled": True},
                )
                discovery_warnings.append("ifcg_discovery:cancelled")
            except Exception as exc:
                discovery_warnings.append(f"ifcg_discovery_failed:{type(exc).__name__}")

        self._raise_if_stop_requested(should_stop)
        tnved_output = await self._tnved_service.analyze(run_input)
        candidate_codes = _candidate_codes(tnved_output)
        descriptions = _build_descriptions(
            codes=candidate_codes,
            tnved_output=tnved_output,
            catalog=catalog_snapshot,
        )
        base_trace = {
            "catalog_trace": catalog_trace,
            "candidate_codes": candidate_codes,
            "ifcg_discovery_status": ifcg_discovery.status if ifcg_discovery is not None else "skipped",
        }
        tnved_partial_result = CasePipelineResult(
            status="running",
            final_code=tnved_output.selected_code,
            final_description=tnved_output.selected_description,
            final_status="tnved_ready" if tnved_output.selected_code else "tnved_pending",
            operator_summary=tnved_output.selection_rationale,
            warnings=tuple(discovery_warnings),
            input_snapshot=input_snapshot,
            questions_payload=_build_questions_payload(
                tnved_output=tnved_output,
                semantic_output=None,
                verification_output=None,
                final_code=tnved_output.selected_code,
            ),
            tnved=tnved_output,
            ifcg_discovery=ifcg_discovery,
            trace=base_trace,
        )
        self._emit_progress("tnved", tnved_partial_result, progress_callback)

        self._raise_if_stop_requested(should_stop)
        probability_map = {
            candidate.code: candidate.probability_percent
            for candidate in tnved_output.candidates
            if candidate.probability_percent is not None
        }
        evidence_summary = _build_evidence_summary(run_input, tnved_output)
        semantic_output = await self._semantic_service.analyze(
            SemanticInput(
                evidence_summary=evidence_summary,
                selected_code=tnved_output.selected_code,
                selected_description=tnved_output.selected_description,
                llm_rationale=tnved_output.selection_rationale,
                candidate_codes=tuple(candidate_codes),
                descriptions=descriptions,
                probability_map=probability_map,
            )
        )
        verification_seed_code = semantic_output.selected_code or tnved_output.selected_code
        verification_output = await self._verification_service.analyze(
            VerificationInput(
                selected_code=verification_seed_code,
                candidate_codes=tuple(candidate_codes),
                item_context=evidence_summary,
                descriptions=descriptions,
                catalog=catalog_snapshot,
                enable_repair=True,
            )
        )
        final_code = verification_output.final_code or verification_seed_code or tnved_output.selected_code
        final_description = descriptions.get(final_code, "")
        operator_summary = (
            semantic_output.selected_operator_summary
            or tnved_output.selection_rationale
            or verification_output.repair_reason_text
        )
        verification_warnings: list[str] = []
        verification_warnings.extend(discovery_warnings)
        if semantic_output.recommended_review:
            verification_warnings.append("semantic_review_recommended")
        if verification_output.error_code:
            verification_warnings.append(verification_output.error_code.lower())
        verification_partial_result = CasePipelineResult(
            status="running",
            final_code=final_code,
            final_description=final_description,
            final_status=verification_output.final_status or semantic_output.selected_status or "needs_review",
            operator_summary=operator_summary,
            warnings=tuple(verification_warnings),
            input_snapshot=input_snapshot,
            questions_payload=_build_questions_payload(
                tnved_output=tnved_output,
                semantic_output=semantic_output,
                verification_output=verification_output,
                final_code=final_code,
            ),
            tnved=tnved_output,
            semantic=semantic_output,
            verification=verification_output,
            ifcg_discovery=ifcg_discovery,
            trace={
                **base_trace,
                "evidence_summary_chars": len(evidence_summary),
                "semantic_status": semantic_output.selected_status,
                "verification_status": verification_output.final_status,
            },
        )
        self._emit_progress("verification", verification_partial_result, progress_callback)

        self._raise_if_stop_requested(should_stop)
        tnved_vbd_payload, tnved_vbd_output = await self._fetch_tnved_vbd_payload(
            final_code=final_code,
            final_description=final_description,
            run_input=run_input,
            evidence_summary=evidence_summary,
            candidate_codes=candidate_codes,
        )
        tnved_vbd_partial_result = CasePipelineResult(
            status="running",
            final_code=final_code,
            final_description=final_description,
            final_status=verification_output.final_status or semantic_output.selected_status or "needs_review",
            operator_summary=operator_summary,
            warnings=verification_partial_result.warnings,
            input_snapshot=input_snapshot,
            questions_payload=verification_partial_result.questions_payload,
            tnved=tnved_output,
            semantic=semantic_output,
            verification=verification_output,
            tnved_vbd=tnved_vbd_output,
            ifcg_discovery=ifcg_discovery,
            trace={
                **verification_partial_result.trace,
                "tnved_vbd_status": str(tnved_vbd_payload.get("verification_status") or tnved_vbd_payload.get("status") or "pending"),
            },
        )
        self._emit_progress("tnved_vbd", tnved_vbd_partial_result, progress_callback)

        self._raise_if_stop_requested(should_stop)
        self._emit_progress("enrichment", tnved_vbd_partial_result, progress_callback)
        ifcg_verification_payload, ifcg_verification_output = await self._fetch_ifcg_verification_payload(
            final_code=final_code,
            candidate_codes=candidate_codes,
            run_input=run_input,
            tnved_output=tnved_output,
            evidence_summary=evidence_summary,
            decision_rationale=operator_summary,
        )
        sigma_payload, sigma_result = await self._fetch_sigma_payload(final_code=final_code)
        meta_codes = _merge_unique_codes(
            final_code,
            candidate_codes,
            tuple(item.code for item in (ifcg_verification_output.top_codes if ifcg_verification_output is not None else ())[:3]),
            tuple(item.code for item in (ifcg_discovery.top_codes if ifcg_discovery is not None else ())[:2]),
            limit=8,
        )
        its_payload, its_result = await self._fetch_its_payload(
            final_code=final_code,
            related_codes=meta_codes,
        )
        customs_payload = self._build_customs_payload(
            final_code=final_code,
            catalog_snapshot=catalog_snapshot,
            its_payload=its_payload,
            its_result=its_result,
            sigma_result=sigma_result,
        )
        eco_fee_payload = self._build_eco_fee_payload(final_code=final_code)
        warnings: list[str] = []
        warnings.extend(discovery_warnings)
        if semantic_output.recommended_review:
            warnings.append("semantic_review_recommended")
        if verification_output.error_code:
            warnings.append(verification_output.error_code.lower())
        for item in tnved_vbd_payload.get("warnings", []) if isinstance(tnved_vbd_payload.get("warnings"), list) else []:
            text = str(item).strip()
            if text:
                warnings.append(text)
        ifcg_verification_status = str(ifcg_verification_payload.get("status", "")).strip()
        if ifcg_verification_status in {"branch", "error"}:
            warnings.append(f"ifcg_verification:{ifcg_verification_status}")
        sigma_status = str(sigma_payload.get("status", "")).strip()
        if sigma_status in {"error", "fetch_error", "timeout", "http_error", "transport_error", "parse_error"}:
            warnings.append(f"sigma:{sigma_status}")
        its_status = str(its_payload.get("status", "")).strip()
        if its_status in {
            "error",
            "worker_not_running",
            "not_configured",
            "session_invalid",
            "transport_error",
            "timeout",
            "its_error",
        }:
            warnings.append(f"its:{its_status}")
        return CasePipelineResult(
            status="completed",
            final_code=final_code,
            final_description=final_description,
            final_status=verification_output.final_status or semantic_output.selected_status or "needs_review",
            operator_summary=operator_summary,
            warnings=tuple(warnings),
            input_snapshot=input_snapshot,
            questions_payload=_build_questions_payload(
                tnved_output=tnved_output,
                semantic_output=semantic_output,
                verification_output=verification_output,
                final_code=final_code,
            ),
            tnved=tnved_output,
            semantic=semantic_output,
            verification=verification_output,
            tnved_vbd=tnved_vbd_output,
            ifcg_discovery=ifcg_discovery,
            ifcg_verification=ifcg_verification_output,
            sigma_payload=sigma_payload,
            its_payload=its_payload,
            customs_payload=customs_payload,
            eco_fee_payload=eco_fee_payload,
            trace={
                **base_trace,
                "evidence_summary_chars": len(evidence_summary),
                "tnved_vbd_status": str(
                    tnved_vbd_payload.get("verification_status") or tnved_vbd_payload.get("status") or "pending"
                ),
                "ifcg_verification_status": ifcg_verification_status or "pending",
                "sigma_status": sigma_status or "pending",
                "its_status": its_status or "pending",
                "customs_status": customs_payload.get("status", "pending"),
                "eco_fee_status": eco_fee_payload.get("status", "pending"),
            },
        )

    def analyze_ocr_payload_sync(
        self,
        ocr_payload: dict[str, Any] | None,
        *,
        web_hint_text: str = "",
        progress_callback: ProgressCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> CasePipelineResult:
        return self._run_sync(
            self.analyze_ocr_payload(
                ocr_payload,
                web_hint_text=web_hint_text,
                progress_callback=progress_callback,
                should_stop=should_stop,
            )
        )

    def _write_json(self, *, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _fetch_tnved_vbd_payload(
        self,
        *,
        final_code: str,
        final_description: str,
        run_input: TnvedInput,
        evidence_summary: str,
        candidate_codes: list[str],
    ) -> tuple[dict[str, Any], TnvedVbdOutput | None]:
        normalized_code = normalize_code_10(final_code)
        if not normalized_code:
            return {"status": "skipped", "verification_status": "skipped", "selected_code": ""}, None
        if self._tnved_vbd_service is None:
            return {
                "status": "pending",
                "verification_status": "pending",
                "selected_code": normalized_code,
                "summary": "",
                "note": "tnved_vbd_service_not_configured",
            }, None
        try:
            result = await asyncio.to_thread(
                self._tnved_vbd_service.analyze,
                TnvedVbdInput(
                    selected_code=normalized_code,
                    selected_description=final_description,
                    item_name=run_input.item_name,
                    context_text=evidence_summary,
                    candidate_codes=tuple(candidate_codes),
                    product_facts=dict(run_input.product_facts),
                ),
            )
        except Exception as exc:
            return {
                "status": "error",
                "verification_status": "error",
                "selected_code": normalized_code,
                "summary": "",
                "note": _collapse_spaces(exc),
                "warnings": ["tnved_vbd_error"],
            }, None
        return result.to_payload(), result

    async def _fetch_sigma_payload(self, *, final_code: str) -> tuple[dict[str, Any], SigmaPaycalcResult | None]:
        normalized_code = normalize_code_10(final_code)
        if not normalized_code:
            return {"status": "skipped", "error_text": "empty_final_code"}, None
        if self._sigma_service is None:
            return {"status": "pending", "error_text": "sigma_service_not_configured"}, None
        if not self._sigma_service.enabled:
            return {"status": "disabled", "error_text": "sigma_disabled"}, None
        try:
            result = await asyncio.wait_for(
                self._sigma_service.get(normalized_code, query_date=_today_sigma_query_date()),
                timeout=self._sigma_timeout_sec(),
            )
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "error_text": f"Sigma timeout after {int(self._sigma_timeout_sec())} sec",
            }, None
        except asyncio.CancelledError:
            return {"status": "cancelled", "error_text": "Sigma request was cancelled"}, None
        except Exception as exc:
            return {"status": "error", "error_text": _collapse_spaces(exc)}, None
        payload = result.to_dict()
        payload.update(
            {
                "emoji_flags": list(result.emoji_flags),
                "raw_text_lines": list(result.raw_text_lines),
                "eco_attention_prefix": result.eco_attention_prefix,
            }
        )
        return payload, result

    async def _fetch_ifcg_verification_payload(
        self,
        *,
        final_code: str,
        candidate_codes: list[str],
        run_input: TnvedInput,
        tnved_output: TnvedOutput,
        evidence_summary: str,
        decision_rationale: str,
    ) -> tuple[dict[str, Any], IfcgOutput | None]:
        normalized_code = normalize_code_10(final_code)
        if not normalized_code:
            return {"status": "skipped", "error": "empty_final_code"}, None
        if self._ifcg_service is None:
            return {"status": "pending", "error": "ifcg_service_not_configured"}, None
        ifcg_input = IfcgInput(
            item_name=run_input.item_name,
            selected_code=normalized_code,
            candidate_codes=tuple(candidate_codes),
            context_text=evidence_summary,
            decision_rationale=decision_rationale,
            observed_materials=tuple(
                item
                for item in (
                    tuple(tnved_output.observed_attributes.materials)
                    or tuple(run_input.observed_attributes.materials)
                )
                if item
            ),
            product_facts=tnved_output.product_facts or run_input.product_facts,
        )
        try:
            result = await asyncio.wait_for(
                self._ifcg_service.analyze(ifcg_input),
                timeout=self._ifcg_timeout_sec(),
            )
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "summary": "IFCG verification превысил лимит времени.",
                "selected_code": normalized_code,
                "candidate_codes": list(candidate_codes),
                "top_codes": [],
                "operator_short_line": "IFCG verification: timeout",
                "operator_long_lines": ["IFCG verification не завершился вовремя."],
                "dangerous_signal": False,
                "rerun_recommended": True,
                "used": False,
                "query_plan": {},
                "judge_result": {},
                "error": f"timeout_after_{int(self._ifcg_timeout_sec())}_sec",
                "trace": {"timeout_sec": self._ifcg_timeout_sec()},
            }, None
        except asyncio.CancelledError:
            return {
                "status": "error",
                "summary": "IFCG verification was cancelled.",
                "selected_code": normalized_code,
                "candidate_codes": list(candidate_codes),
                "top_codes": [],
                "operator_short_line": "IFCG verification: cancelled",
                "operator_long_lines": ["IFCG verification was cancelled before it completed."],
                "dangerous_signal": False,
                "rerun_recommended": True,
                "used": False,
                "query_plan": {},
                "judge_result": {},
                "error": "cancelled",
                "trace": {"cancelled": True},
            }, None
        except Exception as exc:
            return {"status": "error", "error": _collapse_spaces(exc)}, None
        return result.to_payload(), result

    async def _fetch_its_payload(
        self,
        *,
        final_code: str,
        related_codes: list[str] | tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], ITSFetchResult | None]:
        normalized_code = normalize_code_10(final_code)
        codes = _merge_unique_codes(normalized_code, related_codes, limit=8)
        if not codes:
            return {"status": "skipped", "error_text": "empty_final_code", "by_code": {}}, None
        if self._its_service is None:
            return {"status": "pending", "error_text": "its_service_not_configured", "by_code": {}}, None
        try:
            results = await asyncio.wait_for(
                self._its_service.get_its_many(codes),
                timeout=self._its_timeout_sec(),
            )
        except asyncio.TimeoutError:
            return {
                "code": normalized_code,
                "status": "timeout",
                "its_value": None,
                "its_bracket_value": None,
                "reply_variant": None,
                "date_text": None,
                "error_text": f"ITS timeout after {int(self._its_timeout_sec())} sec",
                "reply_code_match_status": "",
                "reply_code_candidates": [],
                "requested_codes": codes,
                "by_code": {},
            }, None
        except asyncio.CancelledError:
            return {
                "code": normalized_code,
                "status": "cancelled",
                "its_value": None,
                "its_bracket_value": None,
                "reply_variant": None,
                "date_text": None,
                "error_text": "ITS request was cancelled",
                "reply_code_match_status": "",
                "reply_code_candidates": [],
                "requested_codes": codes,
                "by_code": {},
            }, None
        except Exception as exc:
            return {"status": "error", "error_text": _collapse_spaces(exc), "by_code": {}}, None
        result = results.get(normalized_code) if normalized_code else None
        by_code: dict[str, Any] = {}
        for code in codes:
            item = results.get(code)
            if item is None:
                continue
            by_code[code] = {
                "code": item.code,
                "status": item.status,
                "its_value": item.its_value,
                "its_bracket_value": item.its_bracket_value,
                "reply_variant": item.reply_variant,
                "date_text": item.date_text,
                "error_text": item.error_text,
                "reply_code_match_status": item.reply_code_match_status,
                "reply_code_candidates": list(item.reply_code_candidates),
            }
        return {
            "code": result.code if result is not None else normalized_code,
            "status": result.status if result is not None else "pending",
            "its_value": result.its_value if result is not None else None,
            "its_bracket_value": result.its_bracket_value if result is not None else None,
            "reply_variant": result.reply_variant if result is not None else None,
            "date_text": result.date_text if result is not None else None,
            "error_text": result.error_text if result is not None else "",
            "reply_code_match_status": result.reply_code_match_status if result is not None else "",
            "reply_code_candidates": list(result.reply_code_candidates) if result is not None else [],
            "requested_codes": codes,
            "by_code": by_code,
        }, result

    def _build_customs_payload(
        self,
        *,
        final_code: str,
        catalog_snapshot: TnvedCatalogSnapshot | None,
        its_payload: dict[str, Any] | None,
        its_result: ITSFetchResult | None,
        sigma_result: SigmaPaycalcResult | None,
    ) -> dict[str, Any]:
        normalized_code = normalize_code_10(final_code)
        if not normalized_code:
            return {"status": "skipped", "error_text": "empty_final_code"}
        if self._customs_service is None:
            return {"status": "pending", "error_text": "customs_service_not_configured"}
        fallback_duty_rate_text = catalog_snapshot.duty_rate_for(normalized_code) if catalog_snapshot is not None else ""
        effective_its_result = its_result
        if effective_its_result is None and isinstance(its_payload, dict) and str(its_payload.get("status", "")).strip():
            effective_its_result = ITSFetchResult(
                code=normalized_code,
                status=str(its_payload.get("status", "")).strip() or "its_missing",
                its_value=its_payload.get("its_value"),
                its_bracket_value=its_payload.get("its_bracket_value"),
                reply_variant=its_payload.get("reply_variant"),
                date_text=its_payload.get("date_text"),
                raw_reply="",
                error_text=str(its_payload.get("error_text", "")).strip() or None,
                reply_code_match_status=str(its_payload.get("reply_code_match_status", "")).strip() or "not_checked",
                reply_code_candidates=tuple(
                    str(item).strip()
                    for item in (its_payload.get("reply_code_candidates") if isinstance(its_payload.get("reply_code_candidates"), list) else [])
                    if str(item).strip()
                ),
            )
        try:
            result = self._customs_service.build_from_sources(
                code=normalized_code,
                its_result=effective_its_result,
                sigma_result=sigma_result,
                fallback_duty_rate_text=fallback_duty_rate_text,
                fallback_nds_rate=_FALLBACK_NDS_RATE,
                fallback_nds_rate_text=_FALLBACK_NDS_RATE_TEXT,
            )
        except Exception as exc:
            return {"status": "error", "error_text": _collapse_spaces(exc)}
        payload = result.to_dict()
        payload["status"] = "ready"
        return payload

    def _build_eco_fee_payload(self, *, final_code: str) -> dict[str, Any]:
        normalized_code = normalize_code_10(final_code)
        if not normalized_code:
            return {"status": "skipped", "error_text": "empty_final_code"}
        if self._eco_fee_service is None:
            return {"status": "pending", "error_text": "eco_fee_service_not_configured"}
        try:
            return self._eco_fee_service.build_code_packet(code=normalized_code, preferred_year=2026)
        except Exception as exc:
            return {"status": "error", "error_text": _collapse_spaces(exc)}

    @staticmethod
    def _build_stp_payload(customs_payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(customs_payload, dict) or not customs_payload:
            return {"status": "pending", "value": None}
        status = str(customs_payload.get("stp_status") or customs_payload.get("status") or "pending")
        return {
            "status": status,
            "value": customs_payload.get("stp_value"),
            "notice_text": customs_payload.get("notice_text", ""),
        }

    def _load_case_context(self, *, case_dir: Path) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        case_json_path = case_dir / "case.json"
        if case_json_path.exists():
            try:
                parsed = json.loads(case_json_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
        return {
            "case_id": str(payload.get("case_id") or case_dir.name),
            "row_number": payload.get("row_number"),
            "title": _collapse_spaces(
                payload.get("raw_name")
                or (payload.get("product") or {}).get("raw_name")
                or case_dir.name
            ),
        }

    def _write_running_status(
        self,
        *,
        case_dir: Path,
        current_stage: str,
        last_completed_stage: str,
        error_text: str = "",
    ) -> None:
        status_path = case_dir / "work" / "status.json"
        payload: dict[str, Any] = {}
        if status_path.exists():
            try:
                parsed = json.loads(status_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
        payload["current_stage"] = current_stage
        payload["last_completed_stage"] = last_completed_stage
        payload["failed_stage"] = ""
        payload["status"] = "pipeline_running"
        payload["error_text"] = error_text
        self._write_json(path=status_path, payload=payload)

    def _write_status(self, *, case_dir: Path, status: str, error_text: str = "") -> None:
        status_path = case_dir / "work" / "status.json"
        payload: dict[str, Any] = {}
        if status_path.exists():
            try:
                parsed = json.loads(status_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
        payload["current_stage"] = "result"
        if status == "completed":
            payload["last_completed_stage"] = "result"
            payload["status"] = "pipeline_completed"
            payload["failed_stage"] = ""
            payload["error_text"] = ""
        elif status == "cancelled":
            payload["status"] = "pipeline_cancelled"
            payload["failed_stage"] = ""
            payload["error_text"] = error_text
        elif status == "skipped":
            payload["status"] = "pipeline_skipped"
            payload["failed_stage"] = ""
            payload["error_text"] = error_text
        else:
            payload["status"] = "pipeline_error"
            payload["failed_stage"] = "case_pipeline"
            payload["error_text"] = error_text
        self._write_json(path=status_path, payload=payload)

    def _build_tnved_work_payload(self, result: CasePipelineResult) -> dict[str, Any]:
        tnved_output = result.tnved
        verification = result.verification
        candidate_rows: list[dict[str, Any]] = []
        if tnved_output is not None:
            for index, candidate in enumerate(tnved_output.candidates, start=1):
                title = ""
                if verification is not None:
                    title = str(verification.descriptions.get(candidate.code, "")).strip()
                if not title and candidate.code == tnved_output.selected_code:
                    title = tnved_output.selected_description
                candidate_rows.append(
                    {
                        "code": candidate.code,
                        "title": title,
                        "priority": index,
                        "probability_percent": candidate.probability_percent,
                        "reason": candidate.reason,
                        "source": candidate.source,
                    }
                )
        return {
            "status": result.status,
            "long_description": result.operator_summary,
            "selected_code": result.final_code,
            "selected_description": result.final_description,
            "selection_rationale": tnved_output.selection_rationale if tnved_output is not None else "",
            "confidence_percent": tnved_output.confidence_percent if tnved_output is not None else None,
            "candidates": candidate_rows,
            "final_status": result.final_status,
            "warnings": list(result.warnings),
            "semantic": result.semantic.to_payload() if result.semantic is not None else None,
            "verification": result.verification.to_payload() if result.verification is not None else None,
            "trace": result.trace,
            "error_text": result.error_text,
        }

    def _build_verification_work_payload(self, result: CasePipelineResult) -> dict[str, Any]:
        verification = result.verification
        semantic = result.semantic
        notes = [item for item in result.warnings if item]
        if result.error_text:
            notes.append(result.error_text)
        return {
            "status": result.status,
            "validation_status": verification.final_status if verification is not None else result.final_status,
            "semantic_status": semantic.selected_status if semantic is not None else "skipped",
            "ifcg_status": result.ifcg_verification.status if result.ifcg_verification is not None else "pending",
            "final_code": result.final_code,
            "repaired_code": verification.repaired_code if verification is not None else "",
            "repair_note": verification.repair_note if verification is not None else "",
            "error": verification.error if verification is not None else result.error_text,
            "error_code": verification.error_code if verification is not None else "",
            "notes": notes,
            "trace": result.trace,
        }

    def _build_tnved_vbd_work_payload(self, result: CasePipelineResult) -> dict[str, Any]:
        tnved_vbd = result.tnved_vbd
        if tnved_vbd is not None:
            return tnved_vbd.to_payload()
        if result.final_code:
            return {
                "status": "pending",
                "verification_status": "pending",
                "selected_code": result.final_code,
                "summary": "",
                "note": "",
                "product_facts": [],
                "reference_hits": [],
                "example_hits": [],
                "alternative_codes": [],
                "warnings": [],
                "index_status": "pending",
                "trace": result.trace,
            }
        return {
            "status": result.status if result.status in {"error", "cancelled", "skipped"} else "pending",
            "verification_status": result.final_status if result.final_status in {"error", "cancelled"} else "pending",
            "selected_code": "",
            "summary": "",
            "note": result.error_text,
            "product_facts": [],
            "reference_hits": [],
            "example_hits": [],
            "alternative_codes": [],
            "warnings": [],
            "index_status": "pending",
            "trace": result.trace,
        }

    def _build_enrichment_work_payload(self, result: CasePipelineResult) -> dict[str, Any]:
        ifcg_discovery_payload = (
            result.ifcg_discovery.to_payload()
            if result.ifcg_discovery is not None
            else {"status": "pending", "summary": "", "suggested_groups": [], "suggested_codes": []}
        )
        return {
            "status": "partial" if result.status == "completed" else result.status,
            "ifcg_discovery": ifcg_discovery_payload,
            "tnved_vbd": self._build_tnved_vbd_work_payload(result),
            "ifcg_verification": result.ifcg_verification.to_payload() if result.ifcg_verification is not None else {"status": "pending"},
            "its": result.its_payload or {"status": "pending"},
            "sigma": result.sigma_payload or {"status": "pending"},
            "trace": {
                "final_code": result.final_code,
                "warnings": list(result.warnings),
            },
        }

    def _build_calculations_work_payload(self, result: CasePipelineResult) -> dict[str, Any]:
        return {
            "status": "partial" if result.status == "completed" else result.status,
            "customs": result.customs_payload or {"status": "pending"},
            "stp": self._build_stp_payload(result.customs_payload),
            "eco_fee": result.eco_fee_payload or {"status": "pending"},
            "trace": {
                "final_code": result.final_code,
                "warnings": list(result.warnings),
            },
        }

    @staticmethod
    def _read_existing_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _build_questions_work_payload(self, result: CasePipelineResult, *, case_dir: Path) -> dict[str, Any]:
        payload = dict(result.questions_payload or {})
        payload.setdefault("status", "pending")
        payload.setdefault("count", 0)
        payload.setdefault("top", [])
        payload.setdefault("short", [])
        payload.setdefault("answers", [])
        existing_payload = self._read_existing_json(case_dir / "work" / "questions.json")
        existing_answers = existing_payload.get("answers") if isinstance(existing_payload.get("answers"), list) else []
        payload["answers"] = existing_answers
        existing_items: dict[str, dict[str, Any]] = {}
        for item in existing_payload.get("top", []) if isinstance(existing_payload.get("top"), list) else []:
            if not isinstance(item, dict):
                continue
            question_id = str(item.get("id", "")).strip()
            question_text = str(item.get("question", "")).strip()
            if question_id:
                existing_items[question_id] = item
            elif question_text:
                existing_items[question_text.casefold()] = item
        merged_top: list[dict[str, Any]] = []
        for item in payload.get("top", []) if isinstance(payload.get("top"), list) else []:
            if not isinstance(item, dict):
                continue
            question_id = str(item.get("id", "")).strip()
            question_text = str(item.get("question", "")).strip()
            existing_item = existing_items.get(question_id) or existing_items.get(question_text.casefold())
            merged_item = dict(item)
            if isinstance(existing_item, dict):
                existing_answer = str(existing_item.get("answer", "")).strip()
                existing_status = str(existing_item.get("status", "")).strip()
                if existing_answer:
                    merged_item["answer"] = existing_answer
                if existing_status:
                    merged_item["status"] = existing_status
            merged_top.append(merged_item)
        payload["top"] = merged_top
        payload["final_code"] = result.final_code
        payload["final_status"] = result.final_status
        return payload

    def _build_pipeline_result_payload(self, result: CasePipelineResult, *, case_context: dict[str, Any]) -> dict[str, Any]:
        tnved_output = result.tnved
        return {
            "schema_version": "case_pipeline.v1",
            "status": result.status,
            "case": case_context,
            "input": result.input_snapshot,
            "questions": result.questions_payload or None,
            "decision": {
                "selected_code": result.final_code,
                "selected_description": result.final_description,
                "confidence_percent": tnved_output.confidence_percent if tnved_output is not None else None,
                "selection_rationale": result.operator_summary,
                "final_status": result.final_status,
            },
            "enrichment": {
                "ifcg_discovery": result.ifcg_discovery.to_payload() if result.ifcg_discovery is not None else None,
                "tnved_vbd": self._build_tnved_vbd_work_payload(result),
                "ifcg_verification": result.ifcg_verification.to_payload() if result.ifcg_verification is not None else None,
                "its": result.its_payload or None,
                "sigma": result.sigma_payload or None,
            },
            "calculations": {
                "customs": result.customs_payload or None,
                "stp": self._build_stp_payload(result.customs_payload),
                "eco_fee": result.eco_fee_payload or None,
            },
            "stages": {
                "ifcg_discovery": result.ifcg_discovery.to_payload() if result.ifcg_discovery is not None else None,
                "tnved": result.tnved.to_payload() if result.tnved is not None else None,
                "semantic": result.semantic.to_payload() if result.semantic is not None else None,
                "verification": result.verification.to_payload() if result.verification is not None else None,
                "tnved_vbd": self._build_tnved_vbd_work_payload(result),
                "ifcg_verification": result.ifcg_verification.to_payload() if result.ifcg_verification is not None else None,
            },
            "warnings": list(result.warnings),
            "error_text": result.error_text,
            "trace": result.trace,
        }

    def _build_ui_response_payload(self, result: CasePipelineResult, *, case_context: dict[str, Any]) -> dict[str, Any]:
        customs_payload = result.customs_payload if isinstance(result.customs_payload, dict) else {}
        eco_fee_payload = result.eco_fee_payload if isinstance(result.eco_fee_payload, dict) else {}
        tnved_vbd_payload = self._build_tnved_vbd_work_payload(result)
        return {
            "workspace": {
                "case_id": case_context.get("case_id", ""),
                "row_number": case_context.get("row_number"),
                "title": case_context.get("title") or result.input_snapshot.get("item_name", ""),
            },
            "input": {
                "raw_name": result.input_snapshot.get("item_name", ""),
                "ocr_text": result.input_snapshot.get("ocr_text", ""),
                "image_description": result.input_snapshot.get("image_description", ""),
            },
            "questions": result.questions_payload or None,
            "decision": {
                "selected_code": result.final_code,
                "selected_description": result.final_description,
                "confidence_percent": result.tnved.confidence_percent if result.tnved is not None else None,
                "selection_rationale": result.operator_summary,
                "final_status": result.final_status,
            },
            "enrichment": {
                "ifcg_discovery_status": result.ifcg_discovery.status if result.ifcg_discovery is not None else "pending",
                "tnved_vbd_status": str(tnved_vbd_payload.get("verification_status") or tnved_vbd_payload.get("status") or "pending"),
                "ifcg_verification_status": result.ifcg_verification.status if result.ifcg_verification is not None else "pending",
                "its_status": result.its_payload.get("status", "pending") if isinstance(result.its_payload, dict) else "pending",
                "sigma_status": result.sigma_payload.get("status", "pending") if isinstance(result.sigma_payload, dict) else "pending",
            },
            "calculations": {
                "eco_fee": eco_fee_payload.get("short_text"),
                "stp": customs_payload.get("stp_value"),
                "its_value": result.its_payload.get("its_value") if isinstance(result.its_payload, dict) else None,
                "duty_rate": customs_payload.get("effective_duty_rate_text", ""),
                "nds_rate": customs_payload.get("effective_nds_rate_text", ""),
            },
        }

    def _build_export_payload(self, result: CasePipelineResult, *, case_context: dict[str, Any]) -> dict[str, Any]:
        verification = result.verification
        duty_rates = verification.duty_rates if verification is not None else {}
        customs_payload = result.customs_payload if isinstance(result.customs_payload, dict) else {}
        tnved_vbd_payload = self._build_tnved_vbd_work_payload(result)
        return {
            "case_id": case_context.get("case_id", ""),
            "selected_code": result.final_code,
            "selected_description": result.final_description,
            "duty_rate": customs_payload.get("effective_duty_rate_text") or duty_rates.get(result.final_code, ""),
            "nds_rate": customs_payload.get("effective_nds_rate_text", ""),
            "stp_value": customs_payload.get("stp_value"),
            "operator_comment": result.operator_summary,
            "final_status": result.final_status,
            "tnved_vbd_status": tnved_vbd_payload.get("verification_status") or tnved_vbd_payload.get("status") or "",
            "tnved_vbd_summary": tnved_vbd_payload.get("summary", ""),
        }

    def _write_runtime_snapshot(
        self,
        *,
        case_dir: Path,
        case_context: dict[str, Any],
        result: CasePipelineResult,
        current_stage: str,
        last_completed_stage: str,
    ) -> None:
        self._write_json(path=case_dir / "work" / "tnved.json", payload=self._build_tnved_work_payload(result))
        self._write_json(
            path=case_dir / "work" / "verification.json",
            payload=self._build_verification_work_payload(result),
        )
        self._write_json(
            path=case_dir / "work" / "tnved_vbd.json",
            payload=self._build_tnved_vbd_work_payload(result),
        )
        self._write_json(
            path=case_dir / "work" / "enrichment.json",
            payload=self._build_enrichment_work_payload(result),
        )
        self._write_json(
            path=case_dir / "work" / "calculations.json",
            payload=self._build_calculations_work_payload(result),
        )
        self._write_json(
            path=case_dir / "work" / "questions.json",
            payload=self._build_questions_work_payload(result, case_dir=case_dir),
        )
        self._write_json(
            path=case_dir / "result" / "pipeline_result.json",
            payload=self._build_pipeline_result_payload(result, case_context=case_context),
        )
        self._write_json(
            path=case_dir / "result" / "ui_response.json",
            payload=self._build_ui_response_payload(result, case_context=case_context),
        )
        self._write_json(
            path=case_dir / "result" / "export.json",
            payload=self._build_export_payload(result, case_context=case_context),
        )
        self._write_running_status(
            case_dir=case_dir,
            current_stage=current_stage,
            last_completed_stage=last_completed_stage,
            error_text=result.error_text,
        )

    def run_case_pipeline(
        self,
        *,
        case_dir: Path,
        ocr_payload: dict[str, Any] | None,
        web_hint_text: str = "",
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        try:
            case_context = self._load_case_context(case_dir=case_dir)
            stage_to_completed = {
                "tnved": "tnved",
                "verification": "verification",
                "tnved_vbd": "tnved_vbd",
                "enrichment": "tnved_vbd",
            }

            def _progress(stage: str, partial_result: CasePipelineResult) -> None:
                self._write_runtime_snapshot(
                    case_dir=case_dir,
                    case_context=case_context,
                    result=partial_result,
                    current_stage=stage,
                    last_completed_stage=stage_to_completed.get(stage, stage),
                )

            result = self.analyze_ocr_payload_sync(
                ocr_payload,
                web_hint_text=web_hint_text,
                progress_callback=_progress,
                should_stop=should_stop,
            )
            self._write_runtime_snapshot(
                case_dir=case_dir,
                case_context=case_context,
                result=result,
                current_stage="result",
                last_completed_stage="result",
            )
            self._write_status(case_dir=case_dir, status=result.status, error_text=result.error_text)
            return {
                "status": result.status,
                "error_text": result.error_text,
                "final_code": result.final_code,
                "final_status": result.final_status,
            }
        except PipelineCancelledError as exc:
            error_text = _collapse_spaces(exc)
            case_context = self._load_case_context(case_dir=case_dir)
            cancelled_result = CasePipelineResult(
                status="cancelled",
                final_code="",
                final_description="",
                final_status="cancelled",
                operator_summary="",
                error_text=error_text,
                input_snapshot=_build_input_snapshot(ocr_payload),
                questions_payload={"status": "cancelled", "count": 0, "top": [], "short": [], "answers": []},
                trace={"cancelled": True},
            )
            self._write_runtime_snapshot(
                case_dir=case_dir,
                case_context=case_context,
                result=cancelled_result,
                current_stage="cancelled",
                last_completed_stage="cancelled",
            )
            self._write_status(case_dir=case_dir, status="cancelled", error_text=error_text)
            return {
                "status": "cancelled",
                "error_text": error_text,
                "final_code": "",
                "final_status": "cancelled",
            }
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            error_text = _collapse_spaces(exc) or exc.__class__.__name__
            case_context = self._load_case_context(case_dir=case_dir)
            self._write_json(
                path=case_dir / "work" / "tnved.json",
                payload={
                    "status": "error",
                    "long_description": "",
                    "selected_code": "",
                    "selected_description": "",
                    "selection_rationale": "",
                    "confidence_percent": None,
                    "candidates": [],
                    "final_status": "error",
                    "warnings": [],
                    "semantic": None,
                    "verification": None,
                    "trace": {},
                    "error_text": error_text,
                },
            )
            self._write_json(
                path=case_dir / "work" / "verification.json",
                payload={
                    "status": "error",
                    "validation_status": "error",
                    "semantic_status": "error",
                    "ifcg_status": "pending",
                    "notes": [error_text],
                    "trace": {},
                    "error": error_text,
                    "error_code": "PIPELINE_ERROR",
                },
            )
            self._write_json(
                path=case_dir / "work" / "tnved_vbd.json",
                payload={
                    "status": "error",
                    "verification_status": "error",
                    "selected_code": "",
                    "summary": "",
                    "note": error_text,
                    "product_facts": [],
                    "reference_hits": [],
                    "example_hits": [],
                    "alternative_codes": [],
                    "warnings": ["tnved_vbd_error"],
                    "index_status": "error",
                    "trace": {},
                },
            )
            self._write_json(
                path=case_dir / "work" / "enrichment.json",
                payload={
                    "status": "error",
                    "ifcg_discovery": {"status": "error", "summary": "", "error": error_text},
                    "tnved_vbd": {
                        "status": "error",
                        "verification_status": "error",
                        "selected_code": "",
                        "summary": "",
                        "note": error_text,
                        "product_facts": [],
                        "reference_hits": [],
                        "example_hits": [],
                        "alternative_codes": [],
                        "warnings": ["tnved_vbd_error"],
                        "index_status": "error",
                        "trace": {},
                    },
                    "ifcg_verification": {"status": "pending"},
                    "its": {"status": "pending"},
                    "sigma": {"status": "pending"},
                    "trace": {},
                },
            )
            self._write_json(
                path=case_dir / "work" / "calculations.json",
                payload={
                    "status": "error",
                    "customs": {"status": "error", "error_text": error_text},
                    "stp": {"status": "error", "value": None, "notice_text": error_text},
                    "eco_fee": {"status": "error", "error_text": error_text},
                    "trace": {},
                },
            )
            existing_questions_payload = self._read_existing_json(case_dir / "work" / "questions.json")
            self._write_json(
                path=case_dir / "work" / "questions.json",
                payload={
                    "status": "error",
                    "count": 0,
                    "top": [],
                    "short": [],
                    "answers": existing_questions_payload.get("answers")
                    if isinstance(existing_questions_payload.get("answers"), list)
                    else [],
                    "final_code": "",
                    "final_status": "error",
                },
            )
            self._write_json(
                path=case_dir / "result" / "pipeline_result.json",
                payload={
                    "schema_version": "case_pipeline.v1",
                    "status": "error",
                    "case": case_context,
                    "input": _build_input_snapshot(ocr_payload),
                    "questions": {"status": "error", "count": 0, "top": [], "short": [], "answers": []},
                    "decision": {
                        "selected_code": "",
                        "selected_description": "",
                        "confidence_percent": None,
                        "selection_rationale": "",
                        "final_status": "error",
                    },
                    "enrichment": {
                        "ifcg_discovery": None,
                        "tnved_vbd": None,
                        "ifcg_verification": None,
                        "its": None,
                        "sigma": None,
                    },
                    "calculations": {
                        "customs": None,
                        "stp": None,
                        "eco_fee": None,
                    },
                    "stages": {
                        "ifcg_discovery": None,
                        "tnved": None,
                        "semantic": None,
                        "verification": None,
                        "tnved_vbd": None,
                        "ifcg_verification": None,
                    },
                    "warnings": [],
                    "error_text": error_text,
                    "trace": {},
                },
            )
            self._write_json(
                path=case_dir / "result" / "ui_response.json",
                payload={
                    "workspace": {
                        "case_id": case_context.get("case_id", ""),
                        "row_number": case_context.get("row_number"),
                        "title": case_context.get("title", ""),
                    },
                    "input": {},
                    "questions": {"status": "error", "count": 0, "top": [], "short": [], "answers": []},
                    "decision": {},
                    "enrichment": {"tnved_vbd_status": "error"},
                    "calculations": {},
                },
            )
            self._write_json(
                path=case_dir / "result" / "export.json",
                payload={
                    "case_id": case_context.get("case_id", ""),
                    "selected_code": "",
                    "selected_description": "",
                    "operator_comment": "",
                    "final_status": "error",
                    "tnved_vbd_status": "error",
                    "tnved_vbd_summary": "",
                },
            )
            self._write_status(case_dir=case_dir, status="error", error_text=error_text)
            return {
                "status": "error",
                "error_text": error_text,
                "final_code": "",
                "final_status": "error",
            }


__all__ = [
    "CasePipelineResult",
    "CasePipelineService",
    "build_tnved_input_from_ocr_payload",
]
