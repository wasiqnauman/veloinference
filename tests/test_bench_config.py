"""Tests for benchmark schemas and manifest configuration loading."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest

from bench.config import ConfigError, load_experiment_config
from bench.schema import ExperimentConfig, ModelConfig, RequestResult

ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = ROOT / "configs" / "experiments" / "mock_smoke.toml"
PILOT_CONFIG = ROOT / "configs" / "experiments" / "fixed_window_pilot.toml"
PILOT_90_CONFIG = ROOT / "configs" / "experiments" / "fixed_window_pilot_90pct.toml"
FINAL_CONFIG = ROOT / "configs" / "experiments" / "primary_final.toml"
FINAL_SMOKE_CONFIG = ROOT / "configs" / "experiments" / "primary_final_smoke.toml"


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
    assert config.harness_drift_threshold_ms == 10.0
    assert config.harness_error_threshold == 0.01
    assert config.pilot_rates_rps is None
    assert config.pilot_wait_windows_ms is None
    assert config.final_modes is None
    assert config.adaptive_max_wait_ms == 20


def test_required_records_are_frozen_dataclasses() -> None:
    assert is_dataclass(ModelConfig)
    assert is_dataclass(RequestResult)

    model = load_experiment_config(SMOKE_CONFIG).model
    with pytest.raises(FrozenInstanceError):
        model.max_tokens = 16  # type: ignore[misc]


def test_pilot_config_contains_explicit_rates_and_wait_windows() -> None:
    config = load_experiment_config(PILOT_CONFIG)

    assert config.target_endpoint == "adip"
    assert config.gateway_mode == "batched"
    assert config.pilot_rates_rps == (0.5, 1.0, 2.0)
    assert config.pilot_wait_windows_ms == (1, 5, 10, 20)


def test_pilot_90_percent_extension_has_one_explicit_rate() -> None:
    config = load_experiment_config(PILOT_90_CONFIG)

    assert config.pilot_rates_rps == (1.8,)
    assert config.pilot_wait_windows_ms == (1, 5, 10, 20)


def test_final_config_freezes_modes_rates_and_repetitions() -> None:
    config = load_experiment_config(FINAL_CONFIG)

    assert config.final_modes == ("direct", "pass_through", "fixed", "adaptive")
    assert config.final_rates_rps == (0.5, 1.0, 1.5, 1.8)
    assert config.final_repetitions == (1, 2, 3)
    assert config.adaptive_max_wait_ms == 20


def test_final_smoke_config_has_one_condition_per_mode() -> None:
    config = load_experiment_config(FINAL_SMOKE_CONFIG)

    assert config.final_modes == ("direct", "pass_through", "fixed", "adaptive")
    assert config.final_rates_rps == (0.5,)
    assert config.final_repetitions == (1,)
    assert config.workload.arrival.duration_s == 4.0


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

    target = tmp_path / Path(relative_path)
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
