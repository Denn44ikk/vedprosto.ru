from __future__ import annotations

from .shared_flow import SHARED_FLOW_NAME
from .tg_flow import TG_FLOW_NAME
from .ui_flow import UI_FLOW_NAME


FLOW_REGISTRY: dict[str, str] = {
    "shared": SHARED_FLOW_NAME,
    "ui": UI_FLOW_NAME,
    "tg": TG_FLOW_NAME,
}

