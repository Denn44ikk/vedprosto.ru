from __future__ import annotations

from ...config import AppSettings
from ...storage.knowledge.catalogs.eco_fee import (
    EcoFeeCatalog,
    EcoFeeKnowledgeCatalogService,
    EcoGroupYearValue,
    EcoMapEntry,
)


class EcoFeeCatalogService:
    def __init__(self, *, settings: AppSettings) -> None:
        self._settings = settings
        self._storage_service = EcoFeeKnowledgeCatalogService(settings=settings)

    def get_catalog(self) -> EcoFeeCatalog:
        return self._storage_service.get_catalog(prefer_database=True)

    def sync_to_postgres(self, *, workbook_path: str | None = None, database_url: str | None = None):
        return self._storage_service.sync_to_postgres(workbook_path=workbook_path, database_url=database_url)

    def parse_workbook(self, *, workbook_path: str | None = None):
        return self._storage_service.parse_workbook(workbook_path=workbook_path)


__all__ = [
    "EcoFeeCatalog",
    "EcoFeeCatalogService",
    "EcoGroupYearValue",
    "EcoMapEntry",
]
