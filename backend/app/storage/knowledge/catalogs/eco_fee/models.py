from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EcoGroupYearValue:
    eco_group_code: str
    eco_group_name: str
    year: int
    rate_rub_per_ton: float | None
    rate_rub_per_kg: float | None
    complexity_coeff: float | None
    utilization_norm: float | None


@dataclass(frozen=True)
class EcoMapEntry:
    source_row: int
    row_name: str
    okpd2: str
    tnved_raw: str
    tnved_digits: str
    tnved_name: str
    eco_group_code: str
    eco_group_name: str
    footnote_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class EcoFeeCatalog:
    supported_years: tuple[int, ...]
    default_year: int
    usd_rate: float | None
    packaging_norms: dict[int, float]
    groups_by_year: dict[int, dict[str, EcoGroupYearValue]]
    map_entries: tuple[EcoMapEntry, ...]
    footnotes: dict[str, str]


@dataclass(frozen=True)
class EcoFeeWorkbookParseResult:
    workbook_path: str
    source_hash: str
    sheet_names: tuple[str, ...]
    supported_years: tuple[int, ...]
    groups_count: int
    map_entries_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "workbook_path": self.workbook_path,
            "source_hash": self.source_hash,
            "sheet_names": list(self.sheet_names),
            "supported_years": list(self.supported_years),
            "groups_count": self.groups_count,
            "map_entries_count": self.map_entries_count,
        }


@dataclass(frozen=True)
class EcoFeeCatalogDbSyncResult:
    database_url: str
    groups_rows: int
    packaging_rows: int
    map_rows: int
    meta_updated: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "database_url": self.database_url,
            "groups_rows": self.groups_rows,
            "packaging_rows": self.packaging_rows,
            "map_rows": self.map_rows,
            "meta_updated": self.meta_updated,
        }


@dataclass(frozen=True)
class EcoFeeCatalogDbLoadResult:
    database_url: str
    groups_rows: int
    packaging_rows: int
    map_rows: int

    def to_payload(self) -> dict[str, object]:
        return {
            "database_url": self.database_url,
            "groups_rows": self.groups_rows,
            "packaging_rows": self.packaging_rows,
            "map_rows": self.map_rows,
        }
