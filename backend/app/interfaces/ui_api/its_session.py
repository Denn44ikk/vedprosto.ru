from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...dependencies import get_container
from .contracts.its_session import (
    ItsSessionDiagnosticView,
    ItsSessionCodeRequest,
    ItsSessionPasswordRequest,
    ItsSessionPhoneRequest,
    ItsSessionStatusView,
    ItsSessionTestQueryRequest,
    ItsSessionToggleRequest,
)


router = APIRouter(prefix="/its-session", tags=["its-session"])


@router.get("/status", response_model=ItsSessionStatusView)
async def get_its_session_status(container=Depends(get_container)) -> ItsSessionStatusView:
    return ItsSessionStatusView(**(await container.ui_its_session_service.get_status_payload()))


@router.post("/start", response_model=ItsSessionStatusView)
async def start_its_session_login(request: ItsSessionPhoneRequest, container=Depends(get_container)) -> ItsSessionStatusView:
    try:
        payload = await container.ui_its_session_service.start_login(phone=request.phone)
        return ItsSessionStatusView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/code", response_model=ItsSessionStatusView)
async def submit_its_session_code(request: ItsSessionCodeRequest, container=Depends(get_container)) -> ItsSessionStatusView:
    try:
        payload = await container.ui_its_session_service.submit_code(code=request.code)
        return ItsSessionStatusView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/password", response_model=ItsSessionStatusView)
async def submit_its_session_password(
    request: ItsSessionPasswordRequest,
    container=Depends(get_container),
) -> ItsSessionStatusView:
    try:
        payload = await container.ui_its_session_service.submit_password(password=request.password)
        return ItsSessionStatusView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel", response_model=ItsSessionStatusView)
async def cancel_its_session_login(container=Depends(get_container)) -> ItsSessionStatusView:
    return ItsSessionStatusView(**(await container.ui_its_session_service.cancel_login()))


@router.post("/delete", response_model=ItsSessionStatusView)
async def delete_its_session(container=Depends(get_container)) -> ItsSessionStatusView:
    try:
        payload = await container.ui_its_session_service.delete_session()
        return ItsSessionStatusView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/enabled", response_model=ItsSessionStatusView)
async def set_its_enabled(
    request: ItsSessionToggleRequest,
    container=Depends(get_container),
) -> ItsSessionStatusView:
    try:
        payload = await container.ui_its_session_service.set_enabled(enabled=request.enabled)
        return ItsSessionStatusView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/check-access", response_model=ItsSessionDiagnosticView)
async def check_its_access(container=Depends(get_container)) -> ItsSessionDiagnosticView:
    try:
        payload = await container.ui_its_session_service.check_access_payload()
        return ItsSessionDiagnosticView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-query", response_model=ItsSessionDiagnosticView)
async def test_its_query(
    request: ItsSessionTestQueryRequest,
    container=Depends(get_container),
) -> ItsSessionDiagnosticView:
    try:
        payload = await container.ui_its_session_service.test_query_payload(code=request.code)
        return ItsSessionDiagnosticView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
