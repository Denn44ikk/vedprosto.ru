from __future__ import annotations

import re

from ...integrations.its.models import ITSFetchResult
from ...integrations.sigma.models import SigmaPaycalcResult
from .models import CustomsCalculationInput, CustomsCalculationResult


def _format_percent_label(value: float) -> str:
    rounded = round(float(value), 3)
    if abs(rounded - round(rounded)) < 0.0005:
        return f"{int(round(rounded))}%"
    return f"{rounded:.3f}".rstrip("0").rstrip(".") + "%"


class CustomsCalculationService:
    @staticmethod
    def normalize_duty_rate_text(value: str | None) -> str:
        text = re.sub(r"\s+", " ", (value or "").strip())
        if not text:
            return ""
        lowered = text.lower()
        if any(token in lowered for token in ("евро", "eur", "usd", "руб", "экю", "ecu")):
            return text

        percent_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", text)
        if percent_match is not None:
            percent_value = float(percent_match.group(1).replace(",", "."))
            return _format_percent_label(percent_value)

        numeric_match = re.fullmatch(r"-?\d+(?:[.,]\d+)?", text)
        if numeric_match is not None:
            numeric_value = float(text.replace(",", "."))
            if abs(numeric_value) <= 1:
                return _format_percent_label(numeric_value * 100.0)
            if abs(numeric_value) <= 100:
                return _format_percent_label(numeric_value)

        return text

    @classmethod
    def parse_percent_rate(cls, value: str | float | int | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, (float, int)):
            numeric_value = float(value)
            if abs(numeric_value) <= 1:
                return numeric_value
            if abs(numeric_value) <= 100:
                return numeric_value / 100.0
            return None

        text = cls.normalize_duty_rate_text(value)
        if not text or "%" not in text:
            return None
        if any(token in text.lower() for token in ("евро", "eur", "usd", "руб", "экю", "ecu")):
            return None
        match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", text)
        if match is None:
            return None
        return float(match.group(1).replace(",", ".")) / 100.0

    @classmethod
    def resolve_effective_duty_rate_text(
        cls,
        *,
        primary_duty_rate_text: str | None,
        fallback_duty_rate_text: str | None = None,
    ) -> tuple[str, str]:
        primary = cls.normalize_duty_rate_text(primary_duty_rate_text)
        fallback = cls.normalize_duty_rate_text(fallback_duty_rate_text)
        if cls.parse_percent_rate(primary) is not None:
            return primary, "primary"
        if cls.parse_percent_rate(fallback) is not None:
            return fallback, "fallback"
        if primary:
            return primary, "primary"
        if fallback:
            return fallback, "fallback"
        return "", "missing"

    @classmethod
    def resolve_effective_nds(
        cls,
        *,
        primary_nds_rate_text: str | None,
        fallback_nds_rate: float | None = None,
        fallback_nds_rate_text: str | None = None,
    ) -> tuple[float | None, str, str]:
        primary_text = cls.normalize_duty_rate_text(primary_nds_rate_text)
        primary_rate = cls.parse_percent_rate(primary_text)
        if primary_rate is not None:
            return primary_rate, primary_text, "primary"

        if fallback_nds_rate is not None:
            fallback_rate = cls.parse_percent_rate(fallback_nds_rate)
            if fallback_rate is not None:
                return fallback_rate, _format_percent_label(fallback_rate * 100.0), "fallback"

        fallback_text = cls.normalize_duty_rate_text(fallback_nds_rate_text)
        fallback_rate = cls.parse_percent_rate(fallback_text)
        if fallback_rate is not None:
            return fallback_rate, fallback_text, "fallback"

        if primary_text:
            return None, primary_text, "primary"
        if fallback_text:
            return None, fallback_text, "fallback"
        return None, "", "missing"

    @staticmethod
    def calculate_stp(*, its_value: float, duty_rate: float, nds_rate: float) -> float:
        return (its_value * duty_rate) + (((its_value * duty_rate) + its_value) * nds_rate)

    def build(self, run_input: CustomsCalculationInput) -> CustomsCalculationResult:
        duty_rate_text = self.normalize_duty_rate_text(run_input.primary_duty_rate_text)
        fallback_duty_rate_text = self.normalize_duty_rate_text(run_input.fallback_duty_rate_text)
        effective_duty_rate_text, effective_duty_source = self.resolve_effective_duty_rate_text(
            primary_duty_rate_text=duty_rate_text,
            fallback_duty_rate_text=fallback_duty_rate_text,
        )
        duty_rate = self.parse_percent_rate(effective_duty_rate_text)
        nds_rate, effective_nds_rate_text, effective_nds_source = self.resolve_effective_nds(
            primary_nds_rate_text=run_input.primary_nds_rate_text,
            fallback_nds_rate=run_input.fallback_nds_rate,
            fallback_nds_rate_text=run_input.fallback_nds_rate_text,
        )

        if run_input.its_status == "ok" and run_input.its_value is not None and duty_rate is not None and nds_rate is not None:
            return CustomsCalculationResult(
                code=run_input.code,
                its_status=run_input.its_status,
                its_value=run_input.its_value,
                its_bracket_value=run_input.its_bracket_value,
                duty_rate_text=duty_rate_text,
                fallback_duty_rate_text=fallback_duty_rate_text,
                effective_duty_rate_text=effective_duty_rate_text,
                effective_duty_source=effective_duty_source,
                nds_value=nds_rate,
                effective_nds_rate_text=effective_nds_rate_text,
                effective_nds_source=effective_nds_source,
                stp_value=self.calculate_stp(its_value=run_input.its_value, duty_rate=duty_rate, nds_rate=nds_rate),
                stp_status="calculated",
                notice_text=run_input.notice_text,
            )

        if run_input.its_status == "no_its_in_bot":
            stp_status = "manual_required_no_its_in_bot"
        elif run_input.its_status == "ok" and duty_rate is None:
            stp_status = "manual_required_non_percent_duty"
        elif run_input.its_status == "ok" and nds_rate is None:
            stp_status = "manual_required_non_percent_nds"
        else:
            stp_status = run_input.its_status if run_input.its_status else "its_error"

        return CustomsCalculationResult(
            code=run_input.code,
            its_status=run_input.its_status,
            its_value=run_input.its_value,
            its_bracket_value=run_input.its_bracket_value,
            duty_rate_text=duty_rate_text,
            fallback_duty_rate_text=fallback_duty_rate_text,
            effective_duty_rate_text=effective_duty_rate_text,
            effective_duty_source=effective_duty_source,
            nds_value=nds_rate,
            effective_nds_rate_text=effective_nds_rate_text,
            effective_nds_source=effective_nds_source,
            stp_value=None,
            stp_status=stp_status,
            notice_text=run_input.notice_text,
        )

    def build_from_sources(
        self,
        *,
        code: str,
        its_result: ITSFetchResult | None,
        sigma_result: SigmaPaycalcResult | None = None,
        fallback_duty_rate_text: str | None = None,
        fallback_nds_rate: float | None = None,
        fallback_nds_rate_text: str | None = None,
        notice_text: str = "",
    ) -> CustomsCalculationResult:
        its_status = its_result.status if its_result is not None else "its_missing"
        its_value = its_result.its_value if its_result is not None else None
        its_bracket_value = its_result.its_bracket_value if its_result is not None else None
        primary_duty_rate_text = sigma_result.duty_text if sigma_result is not None else None
        primary_nds_rate_text = sigma_result.vat_text if sigma_result is not None else None
        return self.build(
            CustomsCalculationInput(
                code=code,
                its_status=its_status,
                its_value=its_value,
                its_bracket_value=its_bracket_value,
                primary_duty_rate_text=primary_duty_rate_text,
                fallback_duty_rate_text=fallback_duty_rate_text,
                primary_nds_rate_text=primary_nds_rate_text,
                fallback_nds_rate=fallback_nds_rate,
                fallback_nds_rate_text=fallback_nds_rate_text,
                notice_text=notice_text,
            )
        )
