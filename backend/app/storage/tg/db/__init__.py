"""TG DB package with lazy exports to avoid import cycles."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "init_tg_db_from_env": ".bootstrap",
    "CacheItsRepo": ".cache_its_repo",
    "CacheSigmaRepo": ".cache_sigma_repo",
    "TgDbConfig": ".connection",
    "TgDbConnection": ".connection",
    "build_tg_db_config": ".connection",
    "TgRuntimeSettingsRepo": ".settings_repo",
    "TgAnalysisRepo": ".tg_analysis_repo",
    "TgCorrectionsRepo": ".tg_corrections_repo",
    "TgMessagesRepo": ".tg_messages_repo",
    "TgRepliesRepo": ".tg_replies_repo",
    "TgReplyLink": ".tg_replies_repo",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    return getattr(module, name)
