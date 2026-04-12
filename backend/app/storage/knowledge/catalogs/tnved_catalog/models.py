from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TnvedCatalogRecord:
    code: str
    description: str
    duty_rate: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TnvedWorkbookParseResult:
    workbook_path: str
    sheet_name: str
    scanned_rows: int
    valid_unique_records: int
    records: tuple[TnvedCatalogRecord, ...]

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["records"] = [record.to_payload() for record in self.records]
        return payload


@dataclass(frozen=True)
class TnvedDownloadResult:
    source_url: str
    destination_path: str
    size_bytes: int
    content_type: str | None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TnvedCatalogUpdateResult:
    status: str
    workbook_path: str
    catalog_json_path: str
    state_json_path: str
    backup_json_path: str
    sheet_name: str
    previous_rows: int
    scanned_rows: int
    imported_rows: int
    active_rows: int
    source_url: str
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TnvedCatalogState:
    status: str = "empty"
    active_catalog_path: str = ""
    backup_catalog_path: str = ""
    source_url: str = ""
    workbook_path: str = ""
    sheet_name: str = ""
    active_rows: int = 0
    scanned_rows: int = 0
    imported_rows: int = 0
    updated_at: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)
