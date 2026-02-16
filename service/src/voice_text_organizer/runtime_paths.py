from __future__ import annotations

import os
from pathlib import Path


def resolve_runtime_dir() -> Path:
    env_runtime_dir = os.getenv("VTO_RUNTIME_DIR")
    if env_runtime_dir:
        return Path(env_runtime_dir).expanduser().resolve()

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Typeless" / "runtime"

    return Path.home() / "AppData" / "Local" / "Typeless" / "runtime"


RUNTIME_DIR = resolve_runtime_dir()
RUNTIME_SETTINGS_PATH = RUNTIME_DIR / "settings.json"
RUNTIME_HISTORY_DB_PATH = RUNTIME_DIR / "history.db"
RUNTIME_BACKEND_LOG_PATH = RUNTIME_DIR / "backend.log"
RUNTIME_BACKEND_STDOUT_LOG_PATH = RUNTIME_DIR / "backend.stdout.log"
RUNTIME_BACKEND_STDERR_LOG_PATH = RUNTIME_DIR / "backend.stderr.log"
