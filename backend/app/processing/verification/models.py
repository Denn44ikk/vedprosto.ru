from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ...storage.knowledge.catalogs import TnvedCatalogSnapshot


@dataclass
class VerificationInput:
    selected_code: str = ""
    candidate_codes: tuple[str, ...] = ()
    item_context: str = ""
    descriptions: dict[str, str] = field(default_factory=dict)
    catalog: TnvedCatalogSnapshot | None = None
    enable_repair: bool = True


@dataclass(frozen=True)
class VerificationOutput:
    chosen_fixed: str
    candidates_fixed: tuple[str, ...]
    candidates_verbose: tuple[str, ...]
    candidate_pool_fixed: tuple[str, ...]
    candidate_pool_verbose: tuple[str, ...]
    error: str
    error_code: str
    repaired_code: str
    repair_note: str
    repair_reason_text: str
    final_code: str
    final_status: str
    descriptions: dict[str, str] = field(default_factory=dict)
    duty_rates: dict[str, str] = field(default_factory=dict)
    trace: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)
