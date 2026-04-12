from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from ...security.access_gate import (
    ACCESS_COOKIE_NAME,
    ACCESS_COOKIE_TTL_SECONDS,
    build_access_cookie_value,
    is_access_gate_enabled,
    is_request_authenticated,
)


router = APIRouter(prefix="/auth", tags=["auth"])


class AuthLoginRequest(BaseModel):
    password: str


@router.get("/status")
def auth_status(request: Request) -> dict[str, bool]:
    settings = request.app.state.container.settings
    enabled = is_access_gate_enabled(settings)
    return {
        "enabled": enabled,
        "authenticated": (not enabled) or is_request_authenticated(request, settings),
    }


@router.post("/login")
def auth_login(payload: AuthLoginRequest, request: Request, response: Response) -> dict[str, bool]:
    settings = request.app.state.container.settings
    enabled = is_access_gate_enabled(settings)
    if not enabled:
        return {"authenticated": True}

    if payload.password != settings.access_password:
        response.status_code = 401
        return {"authenticated": False}

    response.set_cookie(
        ACCESS_COOKIE_NAME,
        build_access_cookie_value(settings),
        max_age=ACCESS_COOKIE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return {"authenticated": True}


@router.post("/logout")
def auth_logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(ACCESS_COOKIE_NAME)
    return {"authenticated": False}
