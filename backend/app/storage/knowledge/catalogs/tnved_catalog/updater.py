from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import DEFAULT_TNVED_DOWNLOAD_URL, DEFAULT_TNVED_SHEET_NAME, TnvedCatalogService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update TNVED catalog JSON snapshot.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--xlsx", help="Path to local .xlsx workbook")
    source_group.add_argument("--download", action="store_true", help="Download workbook from source URL and update")
    parser.add_argument("--source-url", default=DEFAULT_TNVED_DOWNLOAD_URL, help="Download source URL")
    parser.add_argument("--sheet-name", default=DEFAULT_TNVED_SHEET_NAME, help="Preferred worksheet name")
    parser.add_argument("--timeout-sec", type=int, default=60, help="Download timeout in seconds")
    parser.add_argument("--sync-db", action="store_true", help="After update, replace tnved_catalog in PostgreSQL")
    parser.add_argument("--database-url", default="", help="Optional explicit PostgreSQL URL")
    parser.add_argument("--state-json", default="", help="Optional custom state.json path")
    parser.add_argument("--catalog-json", default="", help="Optional custom catalog.json path")
    parser.add_argument("--downloads-dir", default="", help="Optional custom downloads directory")
    parser.add_argument("--backups-dir", default="", help="Optional custom backups directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    service = TnvedCatalogService(
        state_json_path=Path(args.state_json).expanduser() if args.state_json else None,
        catalog_json_path=Path(args.catalog_json).expanduser() if args.catalog_json else None,
        downloads_dir=Path(args.downloads_dir).expanduser() if args.downloads_dir else None,
        backups_dir=Path(args.backups_dir).expanduser() if args.backups_dir else None,
    )
    if args.download:
        result = service.download_and_update(
            source_url=args.source_url,
            preferred_sheet_name=args.sheet_name,
            timeout_sec=args.timeout_sec,
        )
    else:
        result = service.update_from_workbook(
            workbook_path=args.xlsx,
            source_url=args.source_url if args.source_url else "",
            preferred_sheet_name=args.sheet_name,
        )
    payload: dict[str, object] = {"update": result.to_payload()}
    if args.sync_db:
        payload["db_sync"] = service.sync_to_postgres(database_url=args.database_url or None).to_payload()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
