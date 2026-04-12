"""Sigma integration package with lazy exports."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "PP1637_CUSTOMS_FEE_EMOJI": ".utils",
    "SIGMA_ECO_ATTENTION_PREFIX": ".utils",
    "SIGMA_EXCISE_EMOJI": ".utils",
    "SIGMA_MANDATORY_MARKING_EMOJI": ".utils",
    "SIGMA_PAYCALC_BASE_URL": ".parser",
    "SIGMA_PROTECTIVE_EMOJI": ".utils",
    "SIGMA_SECTION_ECO_EMOJI": ".utils",
    "SigmaConfig": ".models",
    "SigmaEcoGroup": ".models",
    "SigmaMeasureState": ".models",
    "SigmaParserInput": ".connector",
    "SigmaParserOutput": ".connector",
    "SigmaPaycalcResult": ".models",
    "SigmaPriceSection": ".models",
    "SigmaPriceSnapshot": ".models",
    "SigmaRawRow": ".models",
    "SigmaService": ".service",
    "build_sigma_config": ".service",
    "build_sigma_paycalc_url": ".parser",
    "build_sigma_price_section": ".price_view",
    "build_sigma_price_snapshot": ".price_view",
    "decode_sigma_html": ".parser",
    "extract_eco_groups": ".price_view",
    "normalize_code_10": ".utils",
    "normalize_emoji_flags": ".utils",
    "normalize_sigma_calc_values": ".price_view",
    "parse_sigma_input": ".connector",
    "parse_sigma_paycalc_bytes": ".parser",
    "parse_sigma_paycalc_html": ".parser",
    "parse_sigma_payload": ".connector",
    "render_sigma_price_lines": ".price_view",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    return getattr(module, name)
