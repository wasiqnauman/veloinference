"""Durable JSONL and atomic JSON writers for benchmark evidence."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4


def append_jsonl(path: Path, record: Mapping[str, object]) -> None:
    """Append one compact JSON object followed by one newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    """Write to a sibling temporary file and atomically replace the target."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
