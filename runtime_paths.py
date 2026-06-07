from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Turnlight"
SOURCE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_base_dir() -> Path:
    bundled_dir = getattr(sys, "_MEIPASS", None)
    if bundled_dir:
        return Path(str(bundled_dir)).resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return SOURCE_DIR


def user_data_dir() -> Path:
    if not is_frozen():
        return SOURCE_DIR
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME
    return Path.home() / "AppData" / "Local" / APP_NAME


def ensure_user_data_dirs() -> None:
    data_dir = user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = data_dir / "samples"
    for state in ("busy_stop", "typing_arrow", "ignored"):
        (samples_dir / state).mkdir(parents=True, exist_ok=True)
