"""Where Gameline keeps things, in development and inside Gameline.app.

User data (state.json, the demo game, .env) lives in a per-user folder, so
./run.sh and the packaged app share it, and the app never writes into its
own bundle. Bundled read-only files (icons) come from the app's Resources
folder when frozen, or from the repo otherwise.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# py2app sets sys.frozen in a full build; alias builds run straight from source.
FROZEN = bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    if os.getenv("GAMELINE_DATA"):
        path = Path(os.environ["GAMELINE_DATA"]).expanduser()
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "Gameline"
    else:
        path = Path.home() / ".gameline"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path() -> Path:
    return data_dir() / "state.json"


def resources_dir() -> Path:
    if FROZEN and os.getenv("RESOURCEPATH"):
        return Path(os.environ["RESOURCEPATH"])
    return REPO_ROOT


def icons_dir() -> Path:
    return resources_dir() / "assets" / "icons"


def migrate_legacy_data() -> list[str]:
    """One-time move from the old repo-local data/ folder (and repo .env) into
    the data folder. Never overwrites. Returns what was copied."""
    copied = []
    if FROZEN:
        return copied
    target = data_dir()
    for src, dst in ((REPO_ROOT / "data" / "state.json", target / "state.json"),
                     (REPO_ROOT / ".env", target / ".env")):
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            copied.append(str(dst))
    return copied
