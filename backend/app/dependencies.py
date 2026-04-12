from __future__ import annotations

from fastapi import Request

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .container import AppContainer


def get_container(request: Request) -> "AppContainer":
    return request.app.state.container
