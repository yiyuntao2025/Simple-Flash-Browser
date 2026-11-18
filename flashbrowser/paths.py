from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
