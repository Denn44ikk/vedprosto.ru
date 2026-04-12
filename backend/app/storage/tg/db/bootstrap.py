from __future__ import annotations

from .connection import TgDbConnection, build_tg_db_config


async def init_tg_db_from_env() -> TgDbConnection | None:
    config = build_tg_db_config()
    if config is None:
        return None
    connection = TgDbConnection(config)
    await connection.create_schema()
    return connection


__all__ = ["init_tg_db_from_env"]
