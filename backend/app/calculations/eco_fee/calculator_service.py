from __future__ import annotations


class EcoFeeCalculatorService:
    @staticmethod
    def calculate_amount(
        *,
        weight_kg: float,
        rate_rub_per_kg: float | None,
        complexity_coeff: float | None,
        utilization_norm: float | None,
    ) -> float:
        if weight_kg <= 0:
            return 0.0
        if rate_rub_per_kg is None or complexity_coeff is None or utilization_norm is None:
            return 0.0
        return float(weight_kg) * rate_rub_per_kg * complexity_coeff * utilization_norm

    @staticmethod
    def calculate_usd(total_amount_rub: float, usd_rate: float | None) -> float | None:
        if usd_rate is None or usd_rate <= 0:
            return None
        return total_amount_rub / usd_rate

    @staticmethod
    def calculate_usd_per_kg(total_amount_usd: float | None, total_weight_kg: float) -> float | None:
        if total_amount_usd is None or total_weight_kg <= 0:
            return None
        return total_amount_usd / total_weight_kg
