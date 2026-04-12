from __future__ import annotations

import json
import os
import re
from typing import Iterable
from urllib.parse import urlparse, urlunparse

import psycopg

from .....config import load_env_file
from .models import (
    EcoFeeCatalog,
    EcoFeeCatalogDbLoadResult,
    EcoFeeCatalogDbSyncResult,
    EcoGroupYearValue,
    EcoMapEntry,
)

FOOTNOTE_RE = re.compile(r"<\s*(\d+)\s*>")


def normalize_database_url(database_url: str | None = None) -> str:
    load_env_file()
    raw = (database_url or os.getenv("ECO_FEE_DB_URL", "") or os.getenv("TG_DB_URL", "")).strip()
    if not raw:
        raise RuntimeError("Database URL is not configured. Set ECO_FEE_DB_URL or TG_DB_URL.")
    if raw.startswith("postgresql+asyncpg://"):
        raw = "postgresql://" + raw.removeprefix("postgresql+asyncpg://")
    return raw


def _redact_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if not parsed.password:
        return database_url
    netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
    return urlunparse(parsed._replace(netloc=netloc))


def _extract_footnote_refs(*values: object) -> tuple[str, ...]:
    refs: list[str] = []
    for value in values:
        text = str(value or "")
        for ref in FOOTNOTE_RE.findall(text):
            if ref not in refs:
                refs.append(ref)
    return tuple(refs)


def ensure_eco_fee_tables(database_url: str | None = None) -> str:
    dsn = normalize_database_url(database_url)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS eco_fee_meta (
                    id INTEGER PRIMARY KEY,
                    source_path TEXT NULL,
                    source_hash TEXT NULL,
                    sheet_names_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    supported_years_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    default_year INTEGER NULL,
                    usd_rate DOUBLE PRECISION NULL,
                    footnotes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_eco_fee_meta_singleton CHECK (id = 1)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS eco_fee_groups (
                    year INTEGER NOT NULL,
                    eco_group_code VARCHAR(32) NOT NULL,
                    eco_group_name TEXT NOT NULL,
                    rate_rub_per_ton DOUBLE PRECISION NULL,
                    rate_rub_per_kg DOUBLE PRECISION NULL,
                    complexity_coeff DOUBLE PRECISION NULL,
                    utilization_norm DOUBLE PRECISION NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (year, eco_group_code)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS eco_fee_packaging_norms (
                    year INTEGER PRIMARY KEY,
                    packaging_norm DOUBLE PRECISION NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS eco_fee_map_entries (
                    source_row INTEGER NOT NULL,
                    row_name TEXT NOT NULL,
                    okpd2 TEXT NULL,
                    tnved_raw TEXT NULL,
                    tnved_digits VARCHAR(32) NOT NULL,
                    tnved_name TEXT NULL,
                    eco_group_code VARCHAR(32) NOT NULL,
                    eco_group_name TEXT NOT NULL,
                    footnote_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (source_row, tnved_digits, eco_group_code)
                )
                """
            )
            cur.execute("ALTER TABLE eco_fee_meta ADD COLUMN IF NOT EXISTS footnotes_json JSONB NOT NULL DEFAULT '{}'::jsonb")
            cur.execute(
                "ALTER TABLE eco_fee_map_entries ADD COLUMN IF NOT EXISTS footnote_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS ix_eco_fee_map_entries_tnved_digits ON eco_fee_map_entries (tnved_digits)")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_eco_fee_map_entries_group_code ON eco_fee_map_entries (eco_group_code)")
        conn.commit()
    return _redact_database_url(dsn)


def replace_eco_fee_catalog(
    *,
    catalog: EcoFeeCatalog,
    source_path: str,
    source_hash: str,
    sheet_names: Iterable[str],
    database_url: str | None = None,
) -> EcoFeeCatalogDbSyncResult:
    dsn = normalize_database_url(database_url)
    group_rows = [
        (
            year,
            value.eco_group_code,
            value.eco_group_name,
            value.rate_rub_per_ton,
            value.rate_rub_per_kg,
            value.complexity_coeff,
            value.utilization_norm,
        )
        for year, groups in sorted(catalog.groups_by_year.items())
        for value in groups.values()
    ]
    packaging_rows = [(year, value) for year, value in sorted(catalog.packaging_norms.items())]
    map_rows = [
        (
            entry.source_row,
            entry.row_name,
            entry.okpd2,
            entry.tnved_raw,
            entry.tnved_digits,
            entry.tnved_name,
            entry.eco_group_code,
            entry.eco_group_name,
            json.dumps(list(entry.footnote_refs), ensure_ascii=False),
        )
        for entry in catalog.map_entries
    ]

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            ensure_eco_fee_tables(database_url=dsn)
            cur.execute("DELETE FROM eco_fee_groups")
            cur.execute("DELETE FROM eco_fee_packaging_norms")
            cur.execute("DELETE FROM eco_fee_map_entries")
            if group_rows:
                cur.executemany(
                    """
                    INSERT INTO eco_fee_groups (
                        year, eco_group_code, eco_group_name, rate_rub_per_ton, rate_rub_per_kg,
                        complexity_coeff, utilization_norm, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    group_rows,
                )
            if packaging_rows:
                cur.executemany(
                    """
                    INSERT INTO eco_fee_packaging_norms (year, packaging_norm, updated_at)
                    VALUES (%s, %s, NOW())
                    """,
                    packaging_rows,
                )
            if map_rows:
                cur.executemany(
                    """
                    INSERT INTO eco_fee_map_entries (
                        source_row, row_name, okpd2, tnved_raw, tnved_digits, tnved_name,
                        eco_group_code, eco_group_name, footnote_refs_json, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    """,
                    map_rows,
                )
            cur.execute(
                """
                INSERT INTO eco_fee_meta (
                    id, source_path, source_hash, sheet_names_json, supported_years_json, default_year, usd_rate, footnotes_json, updated_at
                )
                VALUES (1, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    source_path = EXCLUDED.source_path,
                    source_hash = EXCLUDED.source_hash,
                    sheet_names_json = EXCLUDED.sheet_names_json,
                    supported_years_json = EXCLUDED.supported_years_json,
                    default_year = EXCLUDED.default_year,
                    usd_rate = EXCLUDED.usd_rate,
                    footnotes_json = EXCLUDED.footnotes_json,
                    updated_at = NOW()
                """,
                (
                    source_path,
                    source_hash,
                    json.dumps(list(sheet_names), ensure_ascii=False),
                    json.dumps(list(catalog.supported_years), ensure_ascii=False),
                    catalog.default_year,
                    catalog.usd_rate,
                    json.dumps(catalog.footnotes, ensure_ascii=False),
                ),
            )
        conn.commit()

    return EcoFeeCatalogDbSyncResult(
        database_url=_redact_database_url(dsn),
        groups_rows=len(group_rows),
        packaging_rows=len(packaging_rows),
        map_rows=len(map_rows),
        meta_updated=True,
    )


def read_eco_fee_catalog(database_url: str | None = None) -> tuple[EcoFeeCatalog, EcoFeeCatalogDbLoadResult]:
    dsn = normalize_database_url(database_url)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT year, eco_group_code, eco_group_name, rate_rub_per_ton, rate_rub_per_kg, complexity_coeff, utilization_norm
                FROM eco_fee_groups
                ORDER BY year, eco_group_code
                """
            )
            group_rows = cur.fetchall()
            cur.execute(
                """
                SELECT year, packaging_norm
                FROM eco_fee_packaging_norms
                ORDER BY year
                """
            )
            packaging_rows = cur.fetchall()
            cur.execute(
                """
                SELECT source_row, row_name, okpd2, tnved_raw, tnved_digits, tnved_name, eco_group_code, eco_group_name, footnote_refs_json
                FROM eco_fee_map_entries
                ORDER BY source_row, tnved_digits, eco_group_code
                """
            )
            map_rows = cur.fetchall()
            cur.execute(
                """
                SELECT supported_years_json, default_year, usd_rate, footnotes_json
                FROM eco_fee_meta
                WHERE id = 1
                """
            )
            meta_row = cur.fetchone()

    groups_by_year: dict[int, dict[str, EcoGroupYearValue]] = {}
    for year, eco_group_code, eco_group_name, rate_rub_per_ton, rate_rub_per_kg, complexity_coeff, utilization_norm in group_rows:
        year_int = int(year)
        groups_by_year.setdefault(year_int, {})[str(eco_group_code)] = EcoGroupYearValue(
            eco_group_code=str(eco_group_code),
            eco_group_name=str(eco_group_name),
            year=year_int,
            rate_rub_per_ton=float(rate_rub_per_ton) if rate_rub_per_ton is not None else None,
            rate_rub_per_kg=float(rate_rub_per_kg) if rate_rub_per_kg is not None else None,
            complexity_coeff=float(complexity_coeff) if complexity_coeff is not None else None,
            utilization_norm=float(utilization_norm) if utilization_norm is not None else None,
        )
    packaging_norms = {int(year): (float(value) if value is not None else None) for year, value in packaging_rows}
    map_entries = tuple(
        EcoMapEntry(
            source_row=int(source_row),
            row_name=str(row_name or ""),
            okpd2=str(okpd2 or ""),
            tnved_raw=str(tnved_raw or ""),
            tnved_digits=str(tnved_digits or ""),
            tnved_name=str(tnved_name or ""),
            eco_group_code=str(eco_group_code or ""),
            eco_group_name=str(eco_group_name or ""),
            footnote_refs=tuple(str(item) for item in (footnote_refs_json or []))
            or _extract_footnote_refs(row_name, tnved_raw, tnved_name),
        )
        for source_row, row_name, okpd2, tnved_raw, tnved_digits, tnved_name, eco_group_code, eco_group_name, footnote_refs_json in map_rows
    )
    supported_years: tuple[int, ...]
    default_year: int
    usd_rate: float | None
    footnotes: dict[str, str]
    if meta_row is not None:
        meta_supported_years, meta_default_year, meta_usd_rate, meta_footnotes = meta_row
        supported_years = tuple(int(item) for item in (meta_supported_years or []))
        default_year = int(meta_default_year or (supported_years[0] if supported_years else 2026))
        usd_rate = float(meta_usd_rate) if meta_usd_rate is not None else None
        footnotes = {str(key): str(value or "") for key, value in dict(meta_footnotes or {}).items()}
    else:
        supported_years = tuple(sorted(groups_by_year))
        default_year = supported_years[0] if supported_years else 2026
        usd_rate = None
        footnotes = {}

    catalog = EcoFeeCatalog(
        supported_years=supported_years,
        default_year=default_year,
        usd_rate=usd_rate,
        packaging_norms={year: value for year, value in packaging_norms.items() if value is not None},
        groups_by_year=groups_by_year,
        map_entries=map_entries,
        footnotes=footnotes,
    )
    return catalog, EcoFeeCatalogDbLoadResult(
        database_url=_redact_database_url(dsn),
        groups_rows=len(group_rows),
        packaging_rows=len(packaging_rows),
        map_rows=len(map_rows),
    )


__all__ = [
    "ensure_eco_fee_tables",
    "normalize_database_url",
    "read_eco_fee_catalog",
    "replace_eco_fee_catalog",
]
