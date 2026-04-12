from __future__ import annotations

import argparse
import json

from .service import DEFAULT_WORKBOOK_PATH, EcoFeeKnowledgeCatalogService


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync eco fee workbook into PostgreSQL")
    parser.add_argument("--xlsx", dest="xlsx_path", default=str(DEFAULT_WORKBOOK_PATH), help="Path to eco fee workbook")
    parser.add_argument("--database-url", default=None, help="Override database URL")
    args = parser.parse_args()

    service = EcoFeeKnowledgeCatalogService()
    payload = {
        "parse": service.parse_workbook(workbook_path=args.xlsx_path)[1].to_payload(),
        "db_sync": service.sync_to_postgres(workbook_path=args.xlsx_path, database_url=args.database_url).to_payload(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
