"""Resolves paths to bundled non-Python resources (icons, docs) both when
running from source and when packaged by PyInstaller (--onedir), which
places extra data under sys._MEIPASS instead of next to the source tree.
"""
from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)
