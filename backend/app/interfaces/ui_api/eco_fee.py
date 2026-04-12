from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...dependencies import get_container
from ...reporting.shared import build_currency_rates_payload
from .contracts.eco_fee import (
    EcoFeeCalculateRequest,
    EcoFeeCalculateResponse,
    EcoFeeCurrencyRatesView,
    EcoFeeLookupRequest,
    EcoFeeLookupResponse,
    EcoFeeReferenceView,
)


router = APIRouter(prefix="/eco-fee", tags=["eco-fee"])


@router.get("/reference", response_model=EcoFeeReferenceView)
def get_eco_fee_reference(year: int | None = None, container=Depends(get_container)) -> EcoFeeReferenceView:
    try:
        payload = container.eco_fee_service.get_reference(year=year)
        return EcoFeeReferenceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/currency-rates", response_model=EcoFeeCurrencyRatesView)
def get_eco_fee_currency_rates(container=Depends(get_container)) -> EcoFeeCurrencyRatesView:
    try:
        snapshot = container.currency_service.get_cbr_daily_rates()
        payload = build_currency_rates_payload(snapshot)
        return EcoFeeCurrencyRatesView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/lookup", response_model=EcoFeeLookupResponse)
def lookup_eco_fee(request: EcoFeeLookupRequest, container=Depends(get_container)) -> EcoFeeLookupResponse:
    try:
        payload = container.eco_fee_service.lookup_by_code(code=request.code, year=request.year)
        return EcoFeeLookupResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/calculate", response_model=EcoFeeCalculateResponse)
def calculate_eco_fee(request: EcoFeeCalculateRequest, container=Depends(get_container)) -> EcoFeeCalculateResponse:
    try:
        payload = container.eco_fee_service.calculate(
            year=request.year,
            goods_group_code=request.goods_group_code,
            goods_weight_kg=request.goods_weight_kg,
            packaging_rows=[row.model_dump() for row in request.packaging_rows],
            usd_rate=request.usd_rate,
        )
        return EcoFeeCalculateResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
