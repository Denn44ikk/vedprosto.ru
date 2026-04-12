from __future__ import annotations

from datetime import datetime
from typing import Any

from ...integrations.sigma import SigmaService


class SigmaTool:
    def __init__(self, *, sigma_service: SigmaService | None) -> None:
        self._sigma_service = sigma_service

    @staticmethod
    def _today_query_date() -> str:
        return datetime.now().strftime("%d.%m.%y")

    async def fetch_codes_async(self, codes: list[str]) -> dict[str, Any]:
        service = self._sigma_service
        if service is None:
            return {"status": "unavailable", "reason": "sigma service not configured", "results": []}
        if not service.enabled:
            return {"status": "disabled", "reason": "sigma disabled", "results": []}
        try:
            results = await service.get_many(codes, query_date=self._today_query_date())
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "results": []}
        payload = []
        for code, result in results.items():
            payload.append(
                {
                    "code": code,
                    "status": result.status,
                    "duty_text": result.duty_text,
                    "vat_text": result.vat_text,
                    "source_url": result.source_url,
                    "customs_fee": result.customs_fee.to_dict(),
                    "protective": result.protective.to_dict(),
                    "excise": result.excise.to_dict(),
                    "mandatory_marking": result.mandatory_marking.to_dict(),
                    "eco": result.eco.to_dict(),
                    "error_text": result.error_text,
                }
            )
        return {"status": "ok", "query_date": self._today_query_date(), "results": payload}

    def fetch_codes(self, codes: list[str]) -> dict[str, Any]:
        return {
            "status": "deferred",
            "reason": "sigma live fetch should run from async agent runtime; sync advisor uses case/result payloads",
            "codes": codes,
        }
