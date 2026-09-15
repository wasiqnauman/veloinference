"""Tests for safe reuse of completed final-matrix evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.config import ConfigError
from bench.final import _load_existing_summary


def test_missing_final_run_is_available_for_execution(tmp_path: Path) -> None:
    assert (
        _load_existing_summary(
            tmp_path / "missing",
            run_id="direct-rate-0p5-rep-1",
            resume_existing=True,
        )
        is None
    )


def test_complete_final_run_is_reused(tmp_path: Path) -> None:
    run_dir = tmp_path / "direct" / "direct-rate-0p5-rep-1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    summary = {
        "run_id": "direct-rate-0p5-rep-1",
        "success_count": 60,
        "failure_count": 0,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    assert (
        _load_existing_summary(
            run_dir,
            run_id="direct-rate-0p5-rep-1",
            resume_existing=True,
        )
        == summary
    )


def test_incomplete_final_run_is_rejected(tmp_path: Path) -> None:
    run_dir = tmp_path / "direct" / "direct-rate-1p5-rep-1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"status": "started"}), encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="archive it before resuming"):
        _load_existing_summary(
            run_dir,
            run_id="direct-rate-1p5-rep-1",
            resume_existing=True,
        )
