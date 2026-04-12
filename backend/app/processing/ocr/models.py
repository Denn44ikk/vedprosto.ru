from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class OcrQualityDecision:
    retry_required: bool
    reason: str
    lazy_detected: bool
    reviewer: str = "heuristics"
    confidence: str = ""
    has_concrete_data: bool = False


@dataclass
class OcrRunInput:
    text_cn: str = ""
    source_description: str = ""
    image_paths: list[Path] = field(default_factory=list)
    existing_text_ru: str = ""
    existing_payload: dict[str, object] = field(default_factory=dict)
