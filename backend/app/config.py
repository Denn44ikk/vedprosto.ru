from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
AGENT_UI_DIR = BACKEND_DIR.parent
PROJECT_ROOT = AGENT_UI_DIR.parent
FRONTEND_DIR = AGENT_UI_DIR / "frontend"
RUNTIME_DIR = BACKEND_DIR / "runtime"
UPLOADS_DIR = RUNTIME_DIR / "uploads"
TNVED_VBD_DIR = RUNTIME_DIR / "tnved_vbd"
TNVED_VBD_DOCS_DIR = TNVED_VBD_DIR / "docs"
TNVED_VBD_REFERENCE_DIR = TNVED_VBD_DOCS_DIR / "reference"
TNVED_VBD_EXAMPLES_DIR = TNVED_VBD_DOCS_DIR / "examples"
TNVED_VBD_INDEX_DIR = TNVED_VBD_DIR / "index"
TG_RUNTIME_DIR = RUNTIME_DIR / "tg"
TG_SESSIONS_DIR = TG_RUNTIME_DIR / "sessions"
TG_CACHE_DIR = TG_RUNTIME_DIR / "cache"
TG_STATE_PATH = TG_RUNTIME_DIR / "state.json"
TG_ITS_DIR = TG_RUNTIME_DIR / "its"
TG_ITS_CONFIG_PATH = TG_ITS_DIR / "tg_config.json"
ENV_PATH = AGENT_UI_DIR / ".env"
AI_INTEGRATION_DIR = APP_DIR / "integrations" / "ai"


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppSettings:
    app_title: str
    host: str
    port: int
    project_root: Path
    agent_ui_dir: Path
    frontend_dir: Path
    frontend_assets_dir: Path
    frontend_index_file: Path
    runtime_dir: Path
    uploads_dir: Path
    tnved_vbd_dir: Path
    tnved_vbd_docs_dir: Path
    tnved_vbd_reference_dir: Path
    tnved_vbd_examples_dir: Path
    tnved_vbd_index_dir: Path
    tnved_vbd_top_k: int
    tnved_vbd_chunk_size: int
    tnved_vbd_chunk_overlap: int
    tnved_vbd_embedding_backend: str
    tnved_vbd_embedding_model: str
    tg_runtime_dir: Path
    tg_sessions_dir: Path
    tg_cache_dir: Path
    tg_state_path: Path
    tg_its_dir: Path
    tg_its_config_path: Path
    env_path: Path
    ai_connector_profiles_path: Path
    ai_connector_max_concurrency: int
    pipeline_max_workers_total: int
    pipeline_max_workers_per_job: int
    chat_cli_ai_profile: str
    chat_cli_use_fallback: bool
    chat_cli_history_limit: int
    chat_cli_web_search_enabled: bool
    chat_cli_web_search_timeout_sec: float
    chat_cli_web_search_max_results: int
    access_password: str


def get_settings() -> AppSettings:
    load_env_file()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    TG_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    TG_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    TG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TG_ITS_DIR.mkdir(parents=True, exist_ok=True)
    ai_connector_profiles_path = Path(
        env_str("AI_CONNECTOR_PROFILES_PATH", str(AI_INTEGRATION_DIR / "profiles.yaml"))
    ).expanduser()
    if not ai_connector_profiles_path.is_absolute():
        ai_connector_profiles_path = (AGENT_UI_DIR / ai_connector_profiles_path).resolve()
    tnved_vbd_dir = Path(env_str("TNVED_VBD_DIR", str(TNVED_VBD_DIR))).expanduser()
    if not tnved_vbd_dir.is_absolute():
        tnved_vbd_dir = (AGENT_UI_DIR / tnved_vbd_dir).resolve()
    tnved_vbd_docs_dir = Path(env_str("TNVED_VBD_DOCS_DIR", str(TNVED_VBD_DOCS_DIR))).expanduser()
    if not tnved_vbd_docs_dir.is_absolute():
        tnved_vbd_docs_dir = (AGENT_UI_DIR / tnved_vbd_docs_dir).resolve()
    tnved_vbd_reference_dir = Path(
        env_str("TNVED_VBD_REFERENCE_DIR", str(TNVED_VBD_REFERENCE_DIR))
    ).expanduser()
    if not tnved_vbd_reference_dir.is_absolute():
        tnved_vbd_reference_dir = (AGENT_UI_DIR / tnved_vbd_reference_dir).resolve()
    tnved_vbd_examples_dir = Path(
        env_str("TNVED_VBD_EXAMPLES_DIR", str(TNVED_VBD_EXAMPLES_DIR))
    ).expanduser()
    if not tnved_vbd_examples_dir.is_absolute():
        tnved_vbd_examples_dir = (AGENT_UI_DIR / tnved_vbd_examples_dir).resolve()
    tnved_vbd_index_dir = Path(env_str("TNVED_VBD_INDEX_DIR", str(TNVED_VBD_INDEX_DIR))).expanduser()
    if not tnved_vbd_index_dir.is_absolute():
        tnved_vbd_index_dir = (AGENT_UI_DIR / tnved_vbd_index_dir).resolve()
    tnved_vbd_dir.mkdir(parents=True, exist_ok=True)
    tnved_vbd_docs_dir.mkdir(parents=True, exist_ok=True)
    tnved_vbd_reference_dir.mkdir(parents=True, exist_ok=True)
    tnved_vbd_examples_dir.mkdir(parents=True, exist_ok=True)
    tnved_vbd_index_dir.mkdir(parents=True, exist_ok=True)

    return AppSettings(
        app_title=env_str("APP_TITLE", "TNVED Agent Console"),
        host=env_str("APP_HOST", "127.0.0.1"),
        port=env_int("APP_PORT", 8011),
        project_root=PROJECT_ROOT,
        agent_ui_dir=AGENT_UI_DIR,
        frontend_dir=FRONTEND_DIR,
        frontend_assets_dir=FRONTEND_DIR / "assets",
        frontend_index_file=FRONTEND_DIR / "index.html",
        runtime_dir=RUNTIME_DIR,
        uploads_dir=UPLOADS_DIR,
        tnved_vbd_dir=tnved_vbd_dir,
        tnved_vbd_docs_dir=tnved_vbd_docs_dir,
        tnved_vbd_reference_dir=tnved_vbd_reference_dir,
        tnved_vbd_examples_dir=tnved_vbd_examples_dir,
        tnved_vbd_index_dir=tnved_vbd_index_dir,
        tnved_vbd_top_k=max(1, env_int("TNVED_VBD_TOP_K", 6)),
        tnved_vbd_chunk_size=max(400, env_int("TNVED_VBD_CHUNK_SIZE", 1400)),
        tnved_vbd_chunk_overlap=max(0, env_int("TNVED_VBD_CHUNK_OVERLAP", 220)),
        tnved_vbd_embedding_backend=env_str("TNVED_VBD_EMBEDDING_BACKEND", "default").lower() or "default",
        tnved_vbd_embedding_model=env_str("TNVED_VBD_EMBEDDING_MODEL", "text-embedding-3-small"),
        tg_runtime_dir=TG_RUNTIME_DIR,
        tg_sessions_dir=TG_SESSIONS_DIR,
        tg_cache_dir=TG_CACHE_DIR,
        tg_state_path=TG_STATE_PATH,
        tg_its_dir=TG_ITS_DIR,
        tg_its_config_path=TG_ITS_CONFIG_PATH,
        env_path=ENV_PATH,
        ai_connector_profiles_path=ai_connector_profiles_path,
        ai_connector_max_concurrency=env_int("AI_CONNECTOR_MAX_CONCURRENCY", 5),
        pipeline_max_workers_total=env_int(
            "PIPELINE_MAX_WORKERS_TOTAL",
            env_int("AI_CONNECTOR_MAX_CONCURRENCY", 5),
        ),
        pipeline_max_workers_per_job=env_int("PIPELINE_MAX_WORKERS_PER_JOB", 5),
        chat_cli_ai_profile=env_str("CHAT_CLI_AI_PROFILE", env_str("AI_CLI_PROFILE", "chat_cli")),
        chat_cli_use_fallback=env_bool("CHAT_CLI_USE_FALLBACK", env_bool("AI_CLI_USE_FALLBACK", True)),
        chat_cli_history_limit=env_int("CHAT_CLI_HISTORY_LIMIT", 6),
        chat_cli_web_search_enabled=env_bool("CHAT_CLI_WEB_SEARCH_ENABLED", True),
        chat_cli_web_search_timeout_sec=float(env_str("CHAT_CLI_WEB_SEARCH_TIMEOUT_SEC", "12") or "12"),
        chat_cli_web_search_max_results=max(1, env_int("CHAT_CLI_WEB_SEARCH_MAX_RESULTS", 5)),
        access_password=env_str("APP_ACCESS_PASSWORD", ""),
    )
