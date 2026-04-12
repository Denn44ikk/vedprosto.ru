from __future__ import annotations

from typing import Any

from ...storage.knowledge.catalogs import TnvedCatalogService


class TnvedCatalogTool:
    def __init__(self, *, catalog_service: TnvedCatalogService | None) -> None:
        self._catalog_service = catalog_service

    def describe_codes(self, codes: list[str]) -> dict[str, Any]:
        if self._catalog_service is None:
            return {"status": "unavailable", "reason": "tnved catalog service not configured", "codes": []}
        try:
            snapshot, load_meta = self._catalog_service.build_runtime_snapshot(prefer_database=True)
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "codes": []}
        if snapshot is None:
            return {"status": "empty", "reason": "tnved snapshot unavailable", "codes": []}
        return {
            "status": "ok",
            "loaded_rows": int(load_meta.get("loaded_rows") or load_meta.get("active_rows") or 0)
            if isinstance(load_meta, dict)
            else 0,
            "codes": [
                {
                    "code": code,
                    "exists": snapshot.has_code(code),
                    "description": snapshot.description_for(code),
                    "duty_rate": snapshot.duty_rate_for(code),
                }
                for code in codes
            ],
        }
