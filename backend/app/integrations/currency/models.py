from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CurrencyRate:
    code: str
    nominal: int
    value_rub: float


@dataclass(frozen=True)
class CurrencyRatesSnapshot:
    source: str
    date: str
    note: str
    usd: CurrencyRate | None = None
    eur: CurrencyRate | None = None

