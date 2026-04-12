from __future__ import annotations

from typing import Any

from ...integrations.its import ITSService


class ItsTool:
    def __init__(self, *, its_service: ITSService | None) -> None:
        self._its_service = its_service

    async def fetch_codes_async(self, codes: list[str]) -> dict[str, Any]:
        service = self._its_service
        if service is None:
            return {"status": "unavailable", "reason": "its service not configured", "results": []}
        try:
            results = await service.get_its_many(codes)
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "results": []}
        payload = []
        for code, result in results.items():
            payload.append(
                {
                    "code": code,
                    "status": result.status,
                    "its_value": result.its_value,
                    "its_bracket_value": result.its_bracket_value,
                    "date_text": result.date_text,
                    "reply_variant": result.reply_variant,
                    "reply_code_match_status": result.reply_code_match_status,
                    "reply_code_candidates": list(result.reply_code_candidates),
                    "error_text": result.error_text,
                    "raw_reply": (result.raw_reply or "")[:1200],
                }
            )
        return {"status": "ok", "results": payload}

    def fetch_codes(self, codes: list[str]) -> dict[str, Any]:
        return {
            "status": "deferred",
            "reason": "its live fetch should run from async agent runtime; sync advisor uses case/result payloads",
            "codes": codes,
        }
