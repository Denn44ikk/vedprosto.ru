from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


AI_INTEGRATION_DIR = Path(__file__).resolve().parent
AGENT_UI_DIR = AI_INTEGRATION_DIR.parents[3]
DEFAULT_ENV_FILE = AGENT_UI_DIR / ".env"
DEFAULT_PROFILES_PATH = AI_INTEGRATION_DIR / "profiles.yaml"


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw: str, *, base_dir: Path) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


@dataclass(frozen=True)
class AISettings:
    integration_dir: Path
    agent_ui_dir: Path
    default_env_file: Path
    profiles_path: Path
    max_concurrency: int
    retries: int
    cli_profile: str
    cli_use_fallback: bool
    cli_log_level: str


def get_ai_settings() -> AISettings:
    profiles_raw = _env_str("AI_CONNECTOR_PROFILES_PATH", _env_str("AI_CONNECTOR_PROFILES", str(DEFAULT_PROFILES_PATH)))

    return AISettings(
        integration_dir=AI_INTEGRATION_DIR,
        agent_ui_dir=AGENT_UI_DIR,
        default_env_file=_resolve_path(_env_str("AI_CLI_ENV_FILE", str(DEFAULT_ENV_FILE)), base_dir=AGENT_UI_DIR),
        profiles_path=_resolve_path(profiles_raw, base_dir=AGENT_UI_DIR),
        max_concurrency=_env_int("AI_CONNECTOR_MAX_CONCURRENCY", 5),
        retries=_env_int("AI_CONNECTOR_RETRIES", 3),
        cli_profile=_env_str("AI_CLI_PROFILE", "chat_cli"),
        cli_use_fallback=_env_bool("AI_CLI_USE_FALLBACK", True),
        cli_log_level=_env_str("AI_CLI_LOG_LEVEL", "WARNING"),
    )


__all__ = ["AISettings", "get_ai_settings"]
