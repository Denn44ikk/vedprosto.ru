from __future__ import annotations

from dataclasses import dataclass, field

from .calculator_service import EcoFeeCalculatorService
from .catalog_service import EcoFeeCatalogService, EcoGroupYearValue


@dataclass
class _LookupAccumulator:
    eco_group_code: str
    eco_group_name: str
    match_kind: str
    matched_digits_length: int
    rank_score: int
    source_rows: set[int] = field(default_factory=set)
    matched_codes: set[str] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)
    footnote_refs: set[str] = field(default_factory=set)
    db_entries: list[dict] = field(default_factory=list)
    db_entry_keys: set[tuple[int, str]] = field(default_factory=set)


class EcoFeeService:
    def __init__(
        self,
        *,
        catalog_service: EcoFeeCatalogService,
        calculator_service: EcoFeeCalculatorService,
    ) -> None:
        self.catalog_service = catalog_service
        self.calculator_service = calculator_service

    @staticmethod
    def _normalize_code(code: str) -> str:
        return "".join(ch for ch in str(code) if ch.isdigit())

    @staticmethod
    def _format_rate(rate_rub_per_kg: float | None) -> str:
        if rate_rub_per_kg is None:
            return "нет ставки"
        return f"{rate_rub_per_kg:.3f}".rstrip("0").rstrip(".") + " ₽/кг"

    @staticmethod
    def _format_usd_value(value: float | None) -> str:
        if value is None:
            return "не найдено"
        return f"+{value:.3f}".rstrip("0").rstrip(".")

    @staticmethod
    def _sort_footnote_refs(values: set[str]) -> list[str]:
        return sorted(values, key=lambda item: (0, int(item)) if str(item).isdigit() else (1, str(item)))

    @staticmethod
    def _goods_surcharge_usd_per_kg(
        *,
        rate_rub_per_kg: float | None,
        complexity_coeff: float | None,
        utilization_norm: float | None,
        usd_rate: float | None,
    ) -> float | None:
        if (
            rate_rub_per_kg is None
            or complexity_coeff is None
            or utilization_norm is None
            or usd_rate is None
            or usd_rate <= 0
        ):
            return None
        return (rate_rub_per_kg * complexity_coeff * utilization_norm) / usd_rate

    @staticmethod
    def _match_info(code_digits: str, entry_digits: str) -> tuple[str, int, int] | None:
        if not code_digits or not entry_digits:
            return None
        if code_digits == entry_digits:
            return ("exact", len(entry_digits), 300)
        if len(code_digits) > len(entry_digits) and code_digits.startswith(entry_digits):
            return ("prefix", len(entry_digits), 200)
        if len(code_digits) < len(entry_digits) and entry_digits.startswith(code_digits):
            return ("expanded", len(code_digits), 100)
        return None

    def _year_value(self, year: int, eco_group_code: str) -> EcoGroupYearValue | None:
        catalog = self.catalog_service.get_catalog()
        return catalog.groups_by_year.get(year, {}).get(eco_group_code)

    def get_reference(self, *, year: int | None = None) -> dict:
        catalog = self.catalog_service.get_catalog()
        selected_year = year or catalog.default_year
        if selected_year not in catalog.supported_years:
            raise ValueError(f"Год {selected_year} пока не поддержан для расчета экосбора.")
        groups = []
        for value in sorted(
            catalog.groups_by_year.get(selected_year, {}).values(),
            key=lambda item: int(item.eco_group_code),
        ):
            groups.append(
                {
                    "eco_group_code": value.eco_group_code,
                    "eco_group_name": value.eco_group_name,
                    "rate_rub_per_ton": value.rate_rub_per_ton,
                    "rate_rub_per_kg": value.rate_rub_per_kg,
                    "complexity_coeff": value.complexity_coeff,
                    "utilization_norm": value.utilization_norm,
                }
            )
        return {
            "default_year": catalog.default_year,
            "supported_years": list(catalog.supported_years),
            "usd_rate": catalog.usd_rate,
            "packaging_norm": catalog.packaging_norms.get(selected_year),
            "groups": groups,
        }

    def _decorate_match(self, match: dict, *, usd_rate: float | None) -> dict:
        surcharge_usd_per_kg = self._goods_surcharge_usd_per_kg(
            rate_rub_per_kg=match.get("rate_rub_per_kg"),
            complexity_coeff=match.get("complexity_coeff"),
            utilization_norm=match.get("utilization_norm"),
            usd_rate=usd_rate,
        )
        examples = [str(item).strip() for item in match.get("examples", []) if str(item).strip()]
        names_text = "; ".join(examples[:2])
        short_text = self._format_usd_value(surcharge_usd_per_kg)
        return {
            **match,
            "surcharge_usd_per_kg": round(surcharge_usd_per_kg, 6) if surcharge_usd_per_kg is not None else None,
            "short_text": short_text,
            "names_text": names_text,
        }

    @staticmethod
    def _code_packet_status(year_packets: list[dict]) -> str:
        statuses = {str(item.get("status", "")).strip() for item in year_packets}
        if "resolved" in statuses:
            return "resolved"
        if "ambiguous" in statuses:
            return "ambiguous"
        if "not_found" in statuses:
            return "not_found"
        if "invalid" in statuses:
            return "invalid"
        if "error" in statuses:
            return "error"
        return "pending"

    def build_code_packet(self, *, code: str, preferred_year: int = 2026) -> dict:
        catalog = self.catalog_service.get_catalog()
        supported_years = list(catalog.supported_years)
        selected_year = preferred_year if preferred_year in supported_years else catalog.default_year
        year_packets: list[dict] = []

        for year in supported_years:
            lookup = self.lookup_by_code(code=code, year=year)
            matches = [self._decorate_match(item, usd_rate=catalog.usd_rate) for item in lookup.get("matches", [])]
            best_match = matches[0] if matches else None
            if lookup["status"] == "resolved" and best_match is not None:
                short_text = best_match["short_text"]
                names_text = short_text
                if best_match.get("names_text"):
                    names_text = f"{short_text} · {best_match['names_text']}"
            elif lookup["status"] == "ambiguous":
                short_text = str(lookup["preview"])
                names_text = short_text
            else:
                short_text = str(lookup["preview"])
                names_text = short_text
            year_packets.append(
                {
                    **lookup,
                    "usd_rate": catalog.usd_rate,
                    "packaging_norm": catalog.packaging_norms.get(year),
                    "matches_count": len(matches),
                    "best_match": best_match,
                    "matches": matches,
                    "short_text": short_text,
                    "names_text": names_text,
                }
            )

        selected_packet = next((item for item in year_packets if int(item.get("year", 0)) == selected_year), None)
        if selected_packet is None and year_packets:
            selected_packet = year_packets[0]
            selected_year = int(selected_packet.get("year", selected_year))

        return {
            "code_input": code,
            "code_digits": self._normalize_code(code),
            "default_year": catalog.default_year,
            "supported_years": supported_years,
            "selected_year": selected_year,
            "status": self._code_packet_status(year_packets),
            "note": str(selected_packet.get("note", "")) if selected_packet else "",
            "short_text": str(selected_packet.get("short_text", "нет данных")) if selected_packet else "нет данных",
            "names_text": str(selected_packet.get("names_text", "нет данных")) if selected_packet else "нет данных",
            "years": year_packets,
        }

    def lookup_by_code(self, *, code: str, year: int = 2026) -> dict:
        catalog = self.catalog_service.get_catalog()
        code_digits = self._normalize_code(code)
        if len(code_digits) < 4:
            return {
                "code_input": code,
                "code_digits": code_digits,
                "year": year,
                "status": "invalid",
                "note": "Для экосбора нужен код минимум от 4 знаков.",
                "preview": "нужно минимум 4 знака",
                "matches": [],
            }

        grouped: dict[str, _LookupAccumulator] = {}
        for entry in catalog.map_entries:
            match = self._match_info(code_digits, entry.tnved_digits)
            if not match:
                continue

            match_kind, matched_digits_length, rank_score = match
            accumulator = grouped.get(entry.eco_group_code)
            if accumulator is None:
                accumulator = _LookupAccumulator(
                    eco_group_code=entry.eco_group_code,
                    eco_group_name=entry.eco_group_name,
                    match_kind=match_kind,
                    matched_digits_length=matched_digits_length,
                    rank_score=rank_score,
                )
                grouped[entry.eco_group_code] = accumulator
            elif (rank_score, matched_digits_length) > (accumulator.rank_score, accumulator.matched_digits_length):
                accumulator.match_kind = match_kind
                accumulator.matched_digits_length = matched_digits_length
                accumulator.rank_score = rank_score

            accumulator.source_rows.add(entry.source_row)
            accumulator.matched_codes.add(entry.tnved_digits)
            if entry.row_name not in accumulator.examples:
                accumulator.examples.append(entry.row_name)
            accumulator.footnote_refs.update(entry.footnote_refs)
            entry_key = (entry.source_row, entry.tnved_digits)
            if entry_key not in accumulator.db_entry_keys:
                accumulator.db_entry_keys.add(entry_key)
                accumulator.db_entries.append(
                    {
                        "entry_key": f"{entry.source_row}:{entry.tnved_digits}",
                        "source_row": entry.source_row,
                        "row_name": entry.row_name,
                        "okpd2": entry.okpd2,
                        "tnved_raw": entry.tnved_raw,
                        "tnved_digits": entry.tnved_digits,
                        "tnved_name": entry.tnved_name,
                        "eco_group_code": entry.eco_group_code,
                        "eco_group_name": entry.eco_group_name,
                        "footnotes": [
                            {
                                "ref": ref,
                                "marker": f"<{ref}>",
                                "text": str(catalog.footnotes.get(ref, "")).strip(),
                            }
                            for ref in self._sort_footnote_refs(set(entry.footnote_refs))
                        ],
                    }
                )

        matches = []
        for eco_group_code, accumulator in sorted(
            grouped.items(),
            key=lambda item: (-item[1].rank_score, -item[1].matched_digits_length, int(item[0])),
        ):
            year_value = self._year_value(year, eco_group_code)
            matches.append(
                {
                    "selection_key": eco_group_code,
                    "eco_group_code": eco_group_code,
                    "eco_group_name": accumulator.eco_group_name,
                    "match_kind": accumulator.match_kind,
                    "matched_digits_length": accumulator.matched_digits_length,
                    "source_rows": sorted(accumulator.source_rows),
                    "matched_codes": sorted(accumulator.matched_codes),
                    "examples": accumulator.examples,
                    "db_entries": accumulator.db_entries,
                    "footnotes": [
                        {
                            "ref": ref,
                            "marker": f"<{ref}>",
                            "text": str(catalog.footnotes.get(ref, "")).strip(),
                        }
                        for ref in self._sort_footnote_refs(accumulator.footnote_refs)
                    ],
                    "rate_rub_per_ton": year_value.rate_rub_per_ton if year_value else None,
                    "rate_rub_per_kg": year_value.rate_rub_per_kg if year_value else None,
                    "complexity_coeff": year_value.complexity_coeff if year_value else None,
                    "utilization_norm": year_value.utilization_norm if year_value else None,
                    "preview": self._format_rate(year_value.rate_rub_per_kg if year_value else None),
                }
            )

        if not matches:
            status = "not_found"
            note = "По этому коду совпадений в базе экосбора не найдено."
            preview = "не найдено"
        elif len(matches) == 1:
            status = "resolved"
            note = "По коду найдено одно рабочее eco-совпадение."
            preview = matches[0]["preview"]
        else:
            status = "ambiguous"
            note = "По коду найдено несколько eco-групп. Оператору нужно выбрать строку по названию."
            preview = f"{len(matches)} варианта"

        return {
            "code_input": code,
            "code_digits": code_digits,
            "year": year,
            "status": status,
            "note": note,
            "preview": preview,
            "matches": matches,
        }

    def preview_for_code(self, *, code: str, year: int = 2026) -> str:
        try:
            packet = self.build_code_packet(code=code, preferred_year=year)
            return str(packet.get("short_text") or "нет данных")
        except Exception:
            return "нет данных"

    def calculate(
        self,
        *,
        year: int,
        goods_group_code: str,
        goods_weight_kg: float,
        packaging_rows: list[dict],
        usd_rate: float | None,
    ) -> dict:
        catalog = self.catalog_service.get_catalog()
        goods_value = self._year_value(year, goods_group_code)
        if goods_value is None:
            raise ValueError(f"Eco-группа товара не найдена для года {year}: {goods_group_code}")

        effective_usd_rate = usd_rate or catalog.usd_rate
        packaging_norm = catalog.packaging_norms.get(year)

        goods_amount = self.calculator_service.calculate_amount(
            weight_kg=goods_weight_kg,
            rate_rub_per_kg=goods_value.rate_rub_per_kg,
            complexity_coeff=goods_value.complexity_coeff,
            utilization_norm=goods_value.utilization_norm,
        )

        packaging_breakdowns: list[dict] = []
        packaging_amount = 0.0
        for row in packaging_rows:
            group_code = str(row.get("eco_group_code", "")).strip()
            weight_kg = float(row.get("weight_kg", 0.0) or 0.0)
            if not group_code:
                continue
            group_value = self._year_value(year, group_code)
            if group_value is None:
                raise ValueError(f"Eco-группа упаковки не найдена для года {year}: {group_code}")
            amount_rub = self.calculator_service.calculate_amount(
                weight_kg=weight_kg,
                rate_rub_per_kg=group_value.rate_rub_per_kg,
                complexity_coeff=group_value.complexity_coeff,
                utilization_norm=packaging_norm,
            )
            packaging_amount += amount_rub
            packaging_breakdowns.append(
                {
                    "eco_group_code": group_value.eco_group_code,
                    "eco_group_name": group_value.eco_group_name,
                    "weight_kg": weight_kg,
                    "rate_rub_per_kg": group_value.rate_rub_per_kg,
                    "complexity_coeff": group_value.complexity_coeff,
                    "utilization_norm": packaging_norm,
                    "amount_rub": round(amount_rub, 6),
                }
            )

        total_amount_rub = goods_amount + packaging_amount
        total_weight_kg = float(goods_weight_kg) + sum(float(row.get("weight_kg", 0.0) or 0.0) for row in packaging_rows)
        total_amount_usd = self.calculator_service.calculate_usd(total_amount_rub, effective_usd_rate)
        usd_per_kg = self.calculator_service.calculate_usd_per_kg(total_amount_usd, total_weight_kg)

        return {
            "year": year,
            "goods": {
                "eco_group_code": goods_value.eco_group_code,
                "eco_group_name": goods_value.eco_group_name,
                "weight_kg": float(goods_weight_kg),
                "rate_rub_per_kg": goods_value.rate_rub_per_kg,
                "complexity_coeff": goods_value.complexity_coeff,
                "utilization_norm": goods_value.utilization_norm,
                "amount_rub": round(goods_amount, 6),
            },
            "packaging": packaging_breakdowns,
            "totals": {
                "goods_amount_rub": round(goods_amount, 6),
                "packaging_amount_rub": round(packaging_amount, 6),
                "total_amount_rub": round(total_amount_rub, 6),
                "usd_rate": effective_usd_rate,
                "total_amount_usd": round(total_amount_usd, 6) if total_amount_usd is not None else None,
                "total_weight_kg": round(total_weight_kg, 6),
                "usd_per_kg": round(usd_per_kg, 6) if usd_per_kg is not None else None,
                "packaging_norm": packaging_norm,
            },
        }


__all__ = ["EcoFeeService"]
