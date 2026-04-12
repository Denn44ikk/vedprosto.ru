from __future__ import annotations

from .service import TgBotRuntimeSettings


def is_settings_admin(*, runtime_settings: TgBotRuntimeSettings, user_id: int | None) -> bool:
    if user_id is None:
        return False
    if not runtime_settings.settings_admin_ids:
        return True
    return user_id in runtime_settings.settings_admin_ids


__all__ = ["is_settings_admin"]
