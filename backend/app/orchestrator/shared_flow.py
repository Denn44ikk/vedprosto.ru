from __future__ import annotations

import re
from dataclasses import dataclass

from .stage_map import SHARED_PIPELINE_STAGES


SHARED_FLOW_NAME = "shared_flow"


@dataclass(frozen=True)
class SharedFlowInput:
    source_text: str | None


@dataclass(frozen=True)
class SharedFlowResult:
    source_text: str
    normalized_text: str
    detected_codes: tuple[str, ...]
    primary_code: str | None
    tnved_status: str


def _normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def run_shared_flow(payload: SharedFlowInput) -> SharedFlowResult:
    normalized_text = _normalize_text(payload.source_text)
    detected_codes = tuple(dict.fromkeys(re.findall(r"\b\d{10}\b", normalized_text)))
    primary_code = detected_codes[0] if len(detected_codes) == 1 else None
    if primary_code:
        tnved_status = "code_detected"
    elif detected_codes:
        tnved_status = "code_candidates"
    elif normalized_text:
        tnved_status = "input_only"
    else:
        tnved_status = "empty"
    return SharedFlowResult(
        source_text=(payload.source_text or "").strip(),
        normalized_text=normalized_text,
        detected_codes=detected_codes,
        primary_code=primary_code,
        tnved_status=tnved_status,
    )


def describe_shared_flow() -> tuple[str, ...]:
    """Return the canonical stage order for the common analysis pipeline."""
    return SHARED_PIPELINE_STAGES


__all__ = [
    "SHARED_FLOW_NAME",
    "SharedFlowInput",
    "SharedFlowResult",
    "describe_shared_flow",
    "run_shared_flow",
]
