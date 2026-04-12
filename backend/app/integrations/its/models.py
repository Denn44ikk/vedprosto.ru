from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ITSConfig:
    api_id: str
    api_hash: str
    bot_username: str
    session_path: str
    timeout_sec: int = 30
    delay_sec: float = 3.0
    max_retries: int = 3
    config_path: str | None = None

    @property
    def session_base_path(self) -> str:
        path = Path(self.session_path)
        if path.suffix.lower() == ".session":
            return str(path.with_suffix(""))
        return str(path)


@dataclass(frozen=True)
class ITSFetchResult:
    code: str
    status: str
    its_value: float | None
    its_bracket_value: float | None
    reply_variant: int | None
    date_text: str | None
    raw_reply: str
    error_text: str | None = None
    reply_code_match_status: str = "not_checked"
    reply_code_candidates: tuple[str, ...] = ()

    @property
    def is_technical_failure(self) -> bool:
        return self.status in {
            "telethon_missing",
            "not_configured",
            "session_invalid",
            "timeout",
            "transport_error",
            "auth_error",
            "bot_resolve_error",
            "batch_skipped_technical_outage",
            "reply_code_mismatch",
            "worker_not_running",
            "queue_stalled",
        }

    @property
    def is_batch_outage_failure(self) -> bool:
        return self.is_technical_failure
