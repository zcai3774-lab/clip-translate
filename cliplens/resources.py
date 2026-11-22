"""Locate bundled assets both from source and from a PyInstaller build."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent.parent / relative
