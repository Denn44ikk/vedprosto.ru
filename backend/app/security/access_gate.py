from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING

from fastapi import Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from ..config import AppSettings


ACCESS_COOKIE_NAME = "tnved_ui_access"
ACCESS_COOKIE_TTL_SECONDS = 60 * 60 * 24 * 30
_TOKEN_MESSAGE = b"tnved-ui-access-v1"


def is_access_gate_enabled(settings: AppSettings) -> bool:
    return bool(settings.access_password)


def build_access_cookie_value(settings: AppSettings) -> str:
    return hmac.new(settings.access_password.encode("utf-8"), _TOKEN_MESSAGE, hashlib.sha256).hexdigest()


def is_request_authenticated(request: Request, settings: AppSettings) -> bool:
    cookie_value = request.cookies.get(ACCESS_COOKIE_NAME, "")
    return hmac.compare_digest(cookie_value, build_access_cookie_value(settings))


def _is_public_path(path: str) -> bool:
    if path in {"/", "/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}:
        return True
    if path.startswith("/assets/"):
        return True
    return path in {"/favicon.ico", "/robots.txt"}


def install_access_gate(app) -> None:
    @app.middleware("http")
    async def access_gate_middleware(request: Request, call_next):
        settings = request.app.state.container.settings
        if (
            request.method == "OPTIONS"
            or not is_access_gate_enabled(settings)
            or _is_public_path(request.url.path)
            or is_request_authenticated(request, settings)
        ):
            return await call_next(request)

        return JSONResponse({"detail": "Authentication required."}, status_code=401)
