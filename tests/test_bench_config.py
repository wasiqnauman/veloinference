"""Tests for benchmark schemas and manifest configuration loading."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest

from bench.config import ConfigError, load_experiment_config
from bench.schema import ExperimentConfig, ModelConfig, RequestResult


ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = ROOT / "configs" / "experiments" / "mock_smoke.toml"


def test_smoke_config_resolves_paths_relative_to_config_file() -> None:
    config = load_experiment_config(SMOKE_CONFIG)

    assert isinstance(config, ExperimentConfig)
    assert config.model_config_path == (ROOT / "configs" / "models" / "mock.toml").resolve()
    assert config.workload_config_path == (
        ROOT / "configs" / "workloads" / "short_constant.toml"
    ).resolve()
    assert config.output_dir == (ROOT / "results" / "raw").resolve()
    assert config.model.max_tokens == 8
    assert config.workload.prompt_buckets[0].weight == 1.0


def test_required_records_are_frozen_dataclasses() -> None:
    assert is_dataclass(ModelConfig)
    assert is_dataclass(RequestResult)

    model = load_experiment_config(SMOKE_CONFIG).model
    with pytest.raises(FrozenInstanceError):
        model.max_tokens = 16  # type: ignore[misc]


@pytest.mark.parametrize(
    ("relative_path", "replacement", "message"),
    [
        ("configs/models/mock.toml", "max_model_len = 0", "max_model_len"),
        ("configs/models/mock.toml", "gpu_memory_utilization = 0.0", "gpu_memory"),
        ("configs/workloads/short_constant.toml", "weight = 0.5", "weights"),
        ("configs/workloads/short_constant.toml", "maximum_tokens = 0", "maximum_tokens"),
    ],
)
def test_invalid_boundary_has_actionable_error(
    tmp_path: Path, relative_path: str, replacement: str, message: str
) -> None:
    config_root = tmp_path / "configs"
    (config_root / "models").mkdir(parents=True)
    (config_root / "workloads").mkdir()
    (config_root / "experiments").mkdir()

    for source in (ROOT / "configs").rglob("*.toml"):
        destination = config_root / source.relative_to(ROOT / "configs")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    target = config_root / Path(relative_path)
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            {
                "max_model_len = 0": "max_model_len = 2048",
                "gpu_memory_utilization = 0.0": "gpu_memory_utilization = 0.50",
                "weight = 0.5": "weight = 1.0",
                "maximum_tokens = 0": "maximum_tokens = 32",
            }[replacement],
            replacement,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=message):
        load_experiment_config(config_root / "experiments" / "mock_smoke.toml")


def test_missing_referenced_config_is_reported(tmp_path: Path) -> None:
    config = tmp_path / "missing.toml"
    config.write_text(
        'name = "missing"\nmodel_config = "model.toml"\n'
        'workload_config = "workload.toml"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="does not exist"):
        load_experiment_config(config)
