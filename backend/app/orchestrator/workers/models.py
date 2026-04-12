from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PipelineCaseTask:
    case_id: str
    position: int
    total: int


@dataclass(frozen=True)
class PipelineBatchRequest:
    root_path: str
    case_ids: tuple[str, ...]
    requested_workers: int
    effective_workers: int
    flow_name: str = "ui"
    stages: tuple[str, ...] = ("ocr",)
    job_type: str = "background_prefetch"
    module_id: str = "batch_ocr"
    summary: str = ""
    extra_payload: dict[str, Any] = field(default_factory=dict)

    def build_job_payload(self) -> dict[str, Any]:
        return {
            "root_path": self.root_path,
            "case_ids": list(self.case_ids),
            "requested_workers": self.requested_workers,
            "effective_workers": self.effective_workers,
            "flow_name": self.flow_name,
            "stages": list(self.stages),
            **self.extra_payload,
        }


@dataclass(frozen=True)
class PipelineCaseResult:
    case_id: str
    position: int
    total: int
    status: str
    line: str
    error_text: str = ""
