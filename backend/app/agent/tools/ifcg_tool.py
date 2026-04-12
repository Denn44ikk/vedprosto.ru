from __future__ import annotations

import asyncio
from typing import Any

from ...integrations.ifcg import IfcgService


class IfcgTool:
    def __init__(self, *, ifcg_service: IfcgService | None) -> None:
        self._ifcg_service = ifcg_service

    @staticmethod
    def read_case_signal(runtime_context: dict[str, Any]) -> dict[str, Any]:
        enrichment_payload = runtime_context.get("enrichment_payload") if isinstance(runtime_context.get("enrichment_payload"), dict) else {}
        pipeline_result_payload = runtime_context.get("pipeline_result_payload") if isinstance(runtime_context.get("pipeline_result_payload"), dict) else {}
        calculations_payload = runtime_context.get("calculations_payload") if isinstance(runtime_context.get("calculations_payload"), dict) else {}
        return {
            "status": "ok",
            "ifcg_discovery": enrichment_payload.get("ifcg_discovery") if isinstance(enrichment_payload.get("ifcg_discovery"), dict) else {},
            "ifcg_verification": enrichment_payload.get("ifcg_verification") if isinstance(enrichment_payload.get("ifcg_verification"), dict) else {},
            "ifcg_panel": pipeline_result_payload.get("ifcg_panel") if isinstance(pipeline_result_payload.get("ifcg_panel"), dict) else {},
            "calculations": calculations_payload.get("customs") if isinstance(calculations_payload.get("customs"), dict) else {},
        }

    def run_discovery_from_case(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        service = self._ifcg_service
        if service is None:
            return {"status": "unavailable", "reason": "ifcg service not configured"}
        ocr_payload = runtime_context.get("ocr_payload") if isinstance(runtime_context.get("ocr_payload"), dict) else {}
        try:
            discovery_input = service.build_discovery_input_from_ocr_payload(ocr_payload)
            result = asyncio.run(service.analyze_discovery(discovery_input))
        except Exception as exc:
            return {"status": "error", "reason": str(exc)}
        return {"status": "ok", "payload": result.to_payload()}

    async def run_discovery_from_case_async(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        service = self._ifcg_service
        if service is None:
            return {"status": "unavailable", "reason": "ifcg service not configured"}
        ocr_payload = runtime_context.get("ocr_payload") if isinstance(runtime_context.get("ocr_payload"), dict) else {}
        try:
            discovery_input = service.build_discovery_input_from_ocr_payload(ocr_payload)
            result = await service.analyze_discovery(discovery_input)
        except Exception as exc:
            return {"status": "error", "reason": str(exc)}
        return {"status": "ok", "payload": result.to_payload()}
