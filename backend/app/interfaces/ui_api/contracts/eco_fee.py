from __future__ import annotations

from pydantic import BaseModel, Field


class EcoFeeFootnoteView(BaseModel):
    ref: str
    marker: str
    text: str


class EcoFeeGroupReferenceView(BaseModel):
    eco_group_code: str
    eco_group_name: str
    rate_rub_per_ton: float | None
    rate_rub_per_kg: float | None
    complexity_coeff: float | None
    utilization_norm: float | None


class EcoFeeReferenceView(BaseModel):
    default_year: int
    supported_years: list[int]
    usd_rate: float | None
    packaging_norm: float | None
    groups: list[EcoFeeGroupReferenceView]


class EcoFeeLookupRequest(BaseModel):
    code: str
    year: int = Field(default=2026, ge=2025, le=2027)


class EcoFeeLookupMatchView(BaseModel):
    selection_key: str
    eco_group_code: str
    eco_group_name: str
    match_kind: str
    matched_digits_length: int
    source_rows: list[int]
    matched_codes: list[str]
    examples: list[str]
    footnotes: list[EcoFeeFootnoteView] = Field(default_factory=list)
    rate_rub_per_ton: float | None
    rate_rub_per_kg: float | None
    complexity_coeff: float | None
    utilization_norm: float | None
    preview: str


class CurrencyRateView(BaseModel):
    code: str
    nominal: int
    value_rub: float


class EcoFeeCurrencyRatesView(BaseModel):
    source: str
    date: str
    note: str
    usd: CurrencyRateView | None = None
    eur: CurrencyRateView | None = None


class EcoFeeLookupResponse(BaseModel):
    code_input: str
    code_digits: str
    year: int
    status: str
    note: str
    preview: str
    matches: list[EcoFeeLookupMatchView]


class EcoFeePackagingRowRequest(BaseModel):
    eco_group_code: str
    weight_kg: float = Field(default=0.0, ge=0.0)


class EcoFeeCalculateRequest(BaseModel):
    year: int = Field(default=2026, ge=2025, le=2027)
    goods_group_code: str
    goods_weight_kg: float = Field(default=0.0, ge=0.0)
    packaging_rows: list[EcoFeePackagingRowRequest] = Field(default_factory=list)
    usd_rate: float | None = Field(default=None, gt=0.0)


class EcoFeeBreakdownView(BaseModel):
    eco_group_code: str
    eco_group_name: str
    weight_kg: float
    rate_rub_per_kg: float | None
    complexity_coeff: float | None
    utilization_norm: float | None
    amount_rub: float


class EcoFeeTotalsView(BaseModel):
    goods_amount_rub: float
    packaging_amount_rub: float
    total_amount_rub: float
    usd_rate: float | None
    total_amount_usd: float | None
    total_weight_kg: float
    usd_per_kg: float | None
    packaging_norm: float | None


class EcoFeeCalculateResponse(BaseModel):
    year: int
    goods: EcoFeeBreakdownView
    packaging: list[EcoFeeBreakdownView]
    totals: EcoFeeTotalsView
