"""ITS integration package with lazy exports."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "ITSConfig": ".models",
    "ITSFetchResult": ".models",
    "TGItsClient": ".client",
    "classify_reply_code_match": ".parser",
    "extract_reply_codes": ".parser",
    "parse_reply": ".parser",
    "ITSService": ".service",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    return getattr(module, name)
