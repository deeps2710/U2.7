from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


APP_DIRECTORY_NAME = "ULTRON 2.7"


def resource_root() -> Path:
    """Return the source checkout or PyInstaller resource directory."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root).resolve()
    return Path(__file__).resolve().parents[2]


def desktop_data_dir(
    environ: Mapping[str, str] | None = None,
    *,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    current_platform = sys.platform if platform is None else platform
    user_home = Path.home() if home is None else home

    if current_platform == "win32":
        base = Path(env.get("LOCALAPPDATA") or user_home / "AppData" / "Local")
    elif current_platform == "darwin":
        base = user_home / "Library" / "Application Support"
    else:
        base = Path(env.get("XDG_DATA_HOME") or user_home / ".local" / "share")
    return base.expanduser() / APP_DIRECTORY_NAME
