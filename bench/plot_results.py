"""Utilities for plotting benchmark output."""

from __future__ import annotations

import json
from pathlib import Path


def load_summary(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())
