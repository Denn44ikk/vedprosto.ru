from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse, urlunparse

import psycopg

from .....config import load_env_file
from ..repository import TnvedCatalogSnapshot, build_tnved_catalog_snapshot
from .models import TnvedCatalogRecord, TnvedCatalogState


def normalize_database_url(database_url: str | None = None) -> str:
    load_env_file()
    raw = (database_url or os.getenv("TG_DB_URL", "")).strip()
    if not raw:
        raise RuntimeError("Database URL is not configured. Set TG_DB_URL or pass database_url explicitly.")
    if raw.startswith("postgresql+asyncpg://"):
        raw = "postgresql://" + raw.removeprefix("postgresql+asyncpg://")
    return raw


@dataclass(frozen=True)
class TnvedCatalogDbSyncResult:
    database_url: str
    inserted_rows: int
    meta_updated: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "database_url": self.database_url,
            "inserted_rows": self.inserted_rows,
            "meta_updated": self.meta_updated,
        }


@dataclass(frozen=True)
class TnvedCatalogDbLoadResult:
    database_url: str
    loaded_rows: int

    def to_payload(self) -> dict[str, object]:
        return {
            "database_url": self.database_url,
            "loaded_rows": self.loaded_rows,
        }


def _redact_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if not parsed.password:
        return database_url
    netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
    return urlunparse(parsed._replace(netloc=netloc))


def ensure_tnved_catalog_tables(database_url: str | None = None) -> str:
    dsn = normalize_database_url(database_url)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tnved_catalog (
                    tnved_code VARCHAR(32) PRIMARY KEY,
                    description TEXT NOT NULL,
                    duty_rate TEXT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tnved_catalog_meta (
                    id INTEGER PRIMARY KEY,
                    source_url TEXT NULL,
                    workbook_path TEXT NULL,
                    sheet_name TEXT NULL,
                    active_rows INTEGER NOT NULL DEFAULT 0,
                    scanned_rows INTEGER NOT NULL DEFAULT 0,
                    imported_rows INTEGER NOT NULL DEFAULT 0,
                    notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_tnved_catalog_meta_singleton CHECK (id = 1)
                )
                """
            )
        conn.commit()
    return _redact_database_url(dsn)


def replace_tnved_catalog(
    *,
    records: Iterable[TnvedCatalogRecord],
    state: TnvedCatalogState,
    database_url: str | None = None,
) -> TnvedCatalogDbSyncResult:
    dsn = normalize_database_url(database_url)
    rows = [(record.code, record.description, record.duty_rate) for record in records]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tnved_catalog (
                    tnved_code VARCHAR(32) PRIMARY KEY,
                    description TEXT NOT NULL,
                    duty_rate TEXT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tnved_catalog_meta (
                    id INTEGER PRIMARY KEY,
                    source_url TEXT NULL,
                    workbook_path TEXT NULL,
                    sheet_name TEXT NULL,
                    active_rows INTEGER NOT NULL DEFAULT 0,
                    scanned_rows INTEGER NOT NULL DEFAULT 0,
                    imported_rows INTEGER NOT NULL DEFAULT 0,
                    notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_tnved_catalog_meta_singleton CHECK (id = 1)
                )
                """
            )
            cur.execute("DELETE FROM tnved_catalog")
            if rows:
                cur.executemany(
                    """
                    INSERT INTO tnved_catalog (tnved_code, description, duty_rate, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    rows,
                )
            cur.execute(
                """
                INSERT INTO tnved_catalog_meta (
                    id,
                    source_url,
                    workbook_path,
                    sheet_name,
                    active_rows,
                    scanned_rows,
                    imported_rows,
                    notes_json,
                    updated_at
                )
                VALUES (1, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    source_url = EXCLUDED.source_url,
                    workbook_path = EXCLUDED.workbook_path,
                    sheet_name = EXCLUDED.sheet_name,
                    active_rows = EXCLUDED.active_rows,
                    scanned_rows = EXCLUDED.scanned_rows,
                    imported_rows = EXCLUDED.imported_rows,
                    notes_json = EXCLUDED.notes_json,
                    updated_at = NOW()
                """,
                (
                    state.source_url,
                    state.workbook_path,
                    state.sheet_name,
                    state.active_rows,
                    state.scanned_rows,
                    state.imported_rows,
                    json.dumps(list(state.notes), ensure_ascii=False),
                ),
            )
        conn.commit()
    return TnvedCatalogDbSyncResult(
        database_url=_redact_database_url(dsn),
        inserted_rows=len(rows),
        meta_updated=True,
    )


def read_tnved_catalog_snapshot(
    database_url: str | None = None,
) -> tuple[TnvedCatalogSnapshot, TnvedCatalogDbLoadResult]:
    dsn = normalize_database_url(database_url)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tnved_code, description, duty_rate
                FROM tnved_catalog
                ORDER BY tnved_code
                """
            )
            rows = cur.fetchall()
    snapshot = build_tnved_catalog_snapshot(
        [
            (
                str(code),
                str(description),
                str(duty_rate) if duty_rate is not None else None,
            )
            for code, description, duty_rate in rows
        ]
    )
    return snapshot, TnvedCatalogDbLoadResult(
        database_url=_redact_database_url(dsn),
        loaded_rows=len(rows),
    )


__all__ = [
    "TnvedCatalogDbLoadResult",
    "TnvedCatalogDbSyncResult",
    "ensure_tnved_catalog_tables",
    "normalize_database_url",
    "read_tnved_catalog_snapshot",
    "replace_tnved_catalog",
]
