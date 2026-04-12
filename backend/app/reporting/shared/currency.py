from __future__ import annotations

from ...integrations.currency import CurrencyRate
from ...integrations.currency import CurrencyRatesSnapshot


def _build_rate_payload(rate: CurrencyRate | None) -> dict[str, object] | None:
    if rate is None:
        return None
    return {
        "code": rate.code,
        "nominal": rate.nominal,
        "value_rub": rate.value_rub,
    }


def build_currency_rates_payload(snapshot: CurrencyRatesSnapshot) -> dict[str, object]:
    return {
        "source": snapshot.source,
        "date": snapshot.date,
        "note": snapshot.note,
        "usd": _build_rate_payload(snapshot.usd),
        "eur": _build_rate_payload(snapshot.eur),
    }


__all__ = ["build_currency_rates_payload"]

