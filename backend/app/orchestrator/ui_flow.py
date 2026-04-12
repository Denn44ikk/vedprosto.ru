from __future__ import annotations

from .shared_flow import SHARED_FLOW_NAME, describe_shared_flow


UI_FLOW_NAME = "ui_flow"


def describe_ui_flow() -> dict[str, object]:
    return {
        "name": UI_FLOW_NAME,
        "base_flow": SHARED_FLOW_NAME,
        "stages": describe_shared_flow(),
        "channel_specific": ("workspace", "chat_cli"),
    }

