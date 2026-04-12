from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CustomsCalculationInput:
    code: str
    its_status: str
    its_value: float | None = None
    its_bracket_value: float | None = None
    primary_duty_rate_text: str | None = None
    fallback_duty_rate_text: str | None = None
    primary_nds_rate_text: str | None = None
    fallback_nds_rate: float | None = None
    fallback_nds_rate_text: str | None = None
    notice_text: str = ""


@dataclass(frozen=True)
class CustomsCalculationResult:
    code: str
    its_status: str
    its_value: float | None
    its_bracket_value: float | None
    duty_rate_text: str
    fallback_duty_rate_text: str
    effective_duty_rate_text: str
    effective_duty_source: str
    nds_value: float | None
    effective_nds_rate_text: str
    effective_nds_source: str
    stp_value: float | None
    stp_status: str
    notice_text: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "its_status": self.its_status,
            "its_value": self.its_value,
            "its_bracket_value": self.its_bracket_value,
            "duty_rate_text": self.duty_rate_text,
            "fallback_duty_rate_text": self.fallback_duty_rate_text,
            "effective_duty_rate_text": self.effective_duty_rate_text,
            "effective_duty_source": self.effective_duty_source,
            "nds_value": self.nds_value,
            "effective_nds_rate_text": self.effective_nds_rate_text,
            "effective_nds_source": self.effective_nds_source,
            "stp_value": self.stp_value,
            "stp_status": self.stp_status,
            "notice_text": self.notice_text,
        }
