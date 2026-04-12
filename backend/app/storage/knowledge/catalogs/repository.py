from __future__ import annotations

import re
from dataclasses import dataclass, field


def normalize_code_10(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) == 10 else ""


@dataclass(frozen=True)
class TnvedCatalogEntry:
    code: str
    description: str = ""
    duty_rate: str = ""


@dataclass(frozen=True)
class TnvedCatalogSnapshot:
    entries: tuple[TnvedCatalogEntry, ...] = ()
    codes_set: frozenset[str] = field(default_factory=frozenset)
    descriptions: dict[str, str] = field(default_factory=dict)
    duty_rates: dict[str, str] = field(default_factory=dict)
    idx6: dict[str, tuple[str, ...]] = field(default_factory=dict)
    idx8: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def has_code(self, code: object) -> bool:
        normalized = normalize_code_10(code)
        return bool(normalized and normalized in self.codes_set)

    def description_for(self, code: object) -> str:
        normalized = normalize_code_10(code)
        return self.descriptions.get(normalized, "")

    def duty_rate_for(self, code: object) -> str:
        normalized = normalize_code_10(code)
        return self.duty_rates.get(normalized, "")


def build_tnved_catalog_snapshot(rows: list[tuple[str, str, str | None]]) -> TnvedCatalogSnapshot:
    entries: list[TnvedCatalogEntry] = []
    descriptions: dict[str, str] = {}
    duty_rates: dict[str, str] = {}
    idx6: dict[str, list[str]] = {}
    idx8: dict[str, list[str]] = {}
    codes: list[str] = []

    for code_raw, description_raw, duty_rate_raw in rows:
        code = normalize_code_10(code_raw)
        if not code:
            continue
        description = str(description_raw or "").strip()
        duty_rate = str(duty_rate_raw or "").strip()
        entries.append(TnvedCatalogEntry(code=code, description=description, duty_rate=duty_rate))
        codes.append(code)
        if description:
            descriptions[code] = description
        if duty_rate:
            duty_rates[code] = duty_rate
        idx6.setdefault(code[:6], []).append(code)
        idx8.setdefault(code[:8], []).append(code)

    return TnvedCatalogSnapshot(
        entries=tuple(entries),
        codes_set=frozenset(codes),
        descriptions=descriptions,
        duty_rates=duty_rates,
        idx6={key: tuple(value) for key, value in idx6.items()},
        idx8={key: tuple(value) for key, value in idx8.items()},
    )
