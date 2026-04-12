from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ....config import AppSettings
from ....integrations.its.models import ITSConfig
from .service import TgBotRuntimeSettings, TgBotSettingsService, _env


@dataclass(frozen=True)
class SessionDeleteResult:
    session_path: str
    moved_paths: tuple[str, ...]
    quarantine_suffix: str


@dataclass(frozen=True)
class SessionInstallResult:
    session_path: str
    installed_paths: tuple[str, ...]
    quarantine_suffix: str | None


def resolve_session_path(
    *,
    settings: AppSettings,
    settings_service: TgBotSettingsService,
    runtime_settings: TgBotRuntimeSettings | None = None,
    its_config: ITSConfig | None = None,
) -> Path:
    state = runtime_settings or settings_service.load()
    if its_config is not None:
        return Path(its_config.session_path)
    if state.its_session_path:
        return Path(state.its_session_path)
    session_path = _env("TG_SESSION_PATH")
    if session_path:
        return Path(session_path)
    return settings.tg_sessions_dir / "tg_its.session"


def related_session_files(session_path: Path) -> tuple[Path, ...]:
    if not session_path.parent.exists():
        return ()
    allowed_names = {
        session_path.name,
        f"{session_path.name}-journal",
        f"{session_path.name}-wal",
        f"{session_path.name}-shm",
    }
    related = sorted(path for path in session_path.parent.iterdir() if path.is_file() and path.name in allowed_names)
    return tuple(related)


def cleanup_temp_session_files(temp_session_path: Path) -> tuple[str, ...]:
    removed: list[str] = []
    for path in related_session_files(temp_session_path):
        path.unlink(missing_ok=True)
        removed.append(str(path))
    return tuple(removed)


def _quarantine_files(paths: tuple[Path, ...], *, suffix: str) -> tuple[str, ...]:
    moved: list[str] = []
    for path in paths:
        target = path.with_name(f"{path.name}.{suffix}")
        path.replace(target)
        moved.append(str(target))
    return tuple(moved)


async def delete_current_session(
    *,
    settings: AppSettings,
    settings_service: TgBotSettingsService,
    its_service: Any | None = None,
) -> SessionDeleteResult:
    runtime_settings = settings_service.load()
    session_path = resolve_session_path(
        settings=settings,
        settings_service=settings_service,
        runtime_settings=runtime_settings,
        its_config=(getattr(its_service, "config", None) if its_service is not None else None),
    )
    suffix = f"deleted.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    moved_paths = _quarantine_files(related_session_files(session_path), suffix=suffix)
    if its_service is not None:
        await its_service.reload_runtime()
    return SessionDeleteResult(
        session_path=str(session_path),
        moved_paths=moved_paths,
        quarantine_suffix=suffix,
    )


async def install_temp_session(
    *,
    settings: AppSettings,
    settings_service: TgBotSettingsService,
    temp_session_path: Path,
    its_service: Any | None = None,
) -> SessionInstallResult:
    runtime_settings = settings_service.load()
    session_path = resolve_session_path(
        settings=settings,
        settings_service=settings_service,
        runtime_settings=runtime_settings,
        its_config=(getattr(its_service, "config", None) if its_service is not None else None),
    )
    session_path.parent.mkdir(parents=True, exist_ok=True)

    existing = related_session_files(session_path)
    quarantine_suffix: str | None = None
    if existing:
        quarantine_suffix = f"replaced.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        _quarantine_files(existing, suffix=quarantine_suffix)

    installed: list[str] = []
    for source in related_session_files(temp_session_path):
        target_name = source.name.replace(temp_session_path.name, session_path.name, 1)
        target = session_path.with_name(target_name)
        source.replace(target)
        installed.append(str(target))

    if its_service is not None:
        await its_service.reload_runtime()
    return SessionInstallResult(
        session_path=str(session_path),
        installed_paths=tuple(installed),
        quarantine_suffix=quarantine_suffix,
    )


__all__ = [
    "SessionDeleteResult",
    "SessionInstallResult",
    "cleanup_temp_session_files",
    "delete_current_session",
    "install_temp_session",
    "related_session_files",
    "resolve_session_path",
]
