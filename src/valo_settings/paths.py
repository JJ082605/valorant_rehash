from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        base = Path.home() / "Library/Application Support"
    d = base / "ValoSettings"
    d.mkdir(parents=True, exist_ok=True)
    return d
