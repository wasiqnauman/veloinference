"""Load and validate the committed TOML benchmark configuration files."""

from __future__ import annotations

import math
import tomllib
from pathlib import Path
from typing import Any

from bench.schema import (
    ArrivalConfig,
    ExperimentConfig,
    ModelConfig,
    PromptBucket,
    WorkloadConfig,
)


class ConfigError(ValueError):
    """Raised when a benchmark TOML file violates the experiment contract."""


def load_experiment_config(path: Path) -> ExperimentConfig:
    """Load TOML, validate all fields, resolve paths, and return immutable config."""

    source_path = path.expanduser().resolve()
    experiment = _load_toml(source_path, "experiment")
    base_dir = source_path.parent

    name = _required_string(experiment, "name", "experiment")
    model_config_path = _resolve_config_path(
        experiment, "model_config", base_dir, "experiment"
    )
    workload_config_path = _resolve_config_path(
        experiment, "workload_config", base_dir, "experiment"
    )
    model = _load_model_config(model_config_path)
    workload = _load_workload_config(workload_config_path)

    target_endpoint = _literal(
        experiment,
        "target_endpoint",
        ("direct", "adip"),
        "experiment",
    )
    gateway_mode = _literal(
        experiment,
        "adip_gateway_mode",
        ("pass_through", "batched"),
        "experiment",
    )
    policy = _literal(
        experiment,
        "policy",
        ("fixed", "adaptive"),
        "experiment",
    )
    max_batch_size = _positive_int(experiment, "max_batch_size", "experiment")
    max_wait_ms = _nonnegative_int(experiment, "max_wait_ms", "experiment")
    repetition_seeds = _positive_int_tuple(
        experiment, "repetition_seeds", "experiment"
    )
    cooldown_s = _nonnegative_float(experiment, "cooldown_s", "experiment")
    output_dir = _resolve_path(experiment, "output_dir", base_dir, "experiment")
    slo_derivation_rule = _required_string(
        experiment, "slo_derivation_rule", "experiment"
    )
    health_url = _required_string(experiment, "health_url", "experiment")
    if not health_url.startswith(("http://", "https://")):
        raise ConfigError("experiment.health_url must start with http:// or https://")

    if target_endpoint == "direct" and gateway_mode != "pass_through":
        raise ConfigError(
            "experiment.adip_gateway_mode must be pass_through when "
            "experiment.target_endpoint is direct"
        )
    calibration_rates_rps = _optional_positive_float_tuple(
        experiment, "calibration_rates_rps", "experiment"
    )
    pilot_rates_rps = _optional_positive_float_tuple(
        experiment, "pilot_rates_rps", "experiment"
    )
    pilot_wait_windows_ms = _optional_positive_int_tuple(
        experiment, "pilot_wait_windows_ms", "experiment"
    )
    final_modes = _optional_string_tuple(experiment, "final_modes", "experiment")
    if final_modes is not None and any(
        mode not in ("direct", "pass_through", "fixed", "adaptive")
        for mode in final_modes
    ):
        raise ConfigError(
            "experiment.final_modes must contain only direct, pass_through, fixed, adaptive"
        )
    final_rates_rps = _optional_positive_float_tuple(
        experiment, "final_rates_rps", "experiment"
    )
    final_repetitions = _optional_positive_int_tuple(
        experiment, "final_repetitions", "experiment"
    )
    if final_repetitions is not None and len(final_repetitions) > len(repetition_seeds):
        raise ConfigError(
            "experiment.final_repetitions cannot contain more entries than "
            "experiment.repetition_seeds"
        )
    resume_existing = _bool_or_default(experiment, "resume_existing", "experiment", False)
    adaptive_max_wait_ms = _positive_int_or_default(
        experiment, "adaptive_max_wait_ms", "experiment", 20
    )
    harness_drift_threshold_ms = _nonnegative_float_or_default(
        experiment, "harness_drift_threshold_ms", "experiment", 10.0
    )
    harness_error_threshold = (
        _float_between(
            experiment,
            "harness_error_threshold",
            0.0,
            1.0,
            "experiment",
            include_lower=True,
        )
        if "harness_error_threshold" in experiment
        else 0.01
    )

    return ExperimentConfig(
        name=name,
        model_config_path=model_config_path,
        workload_config_path=workload_config_path,
        model=model,
        workload=workload,
        target_endpoint=target_endpoint,
        gateway_mode=gateway_mode,
        policy=policy,
        max_batch_size=max_batch_size,
        max_wait_ms=max_wait_ms,
        repetition_seeds=repetition_seeds,
        cooldown_s=cooldown_s,
        output_dir=output_dir,
        slo_derivation_rule=slo_derivation_rule,
        health_url=health_url,
        source_path=source_path,
        calibration_rates_rps=calibration_rates_rps,
        pilot_rates_rps=pilot_rates_rps,
        pilot_wait_windows_ms=pilot_wait_windows_ms,
        final_modes=final_modes,
        final_rates_rps=final_rates_rps,
        final_repetitions=final_repetitions,
        resume_existing=resume_existing,
        adaptive_max_wait_ms=adaptive_max_wait_ms,
        harness_drift_threshold_ms=harness_drift_threshold_ms,
        harness_error_threshold=harness_error_threshold,
    )


def _load_model_config(path: Path) -> ModelConfig:
    values = _load_toml(path, "model")
    dtype = _literal(values, "dtype", ("auto", "float16", "bfloat16", "float32"), "model")
    gpu_memory_utilization = _float_between(
        values, "gpu_memory_utilization", 0.0, 1.0, "model", include_lower=False
    )
    return ModelConfig(
        model_id=_required_string(values, "model_id", "model"),
        served_name=_required_string(values, "served_name", "model"),
        revision=_required_string(values, "revision", "model"),
        dtype=dtype,
        max_model_len=_positive_int(values, "max_model_len", "model"),
        gpu_memory_utilization=gpu_memory_utilization,
        max_num_seqs=_positive_int(values, "max_num_seqs", "model"),
        temperature=_nonnegative_float(values, "temperature", "model"),
        max_tokens=_positive_int(values, "max_tokens", "model"),
    )


def _load_workload_config(path: Path) -> WorkloadConfig:
    values = _load_toml(path, "workload")
    buckets_value = values.get("prompt_buckets")
    if not isinstance(buckets_value, list) or not buckets_value:
        raise ConfigError("workload.prompt_buckets must be a non-empty array")

    buckets = tuple(
        _load_prompt_bucket(bucket, index) for index, bucket in enumerate(buckets_value)
    )
    names = [bucket.name for bucket in buckets]
    if len(names) != len(set(names)):
        raise ConfigError("workload.prompt_buckets names must be unique")
    weight_total = sum(bucket.weight for bucket in buckets)
    if not math.isclose(weight_total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ConfigError(
            "workload.prompt_buckets weights must sum to 1.0 "
            f"(got {weight_total:.12g})"
        )

    kind = _literal(values, "arrival_kind", ("constant", "poisson", "bursty"), "workload")
    arrival = ArrivalConfig(
        kind=kind,
        duration_s=_positive_float(values, "duration_s", "workload"),
        seed=_int_value(values, "seed", "workload"),
        rate_fraction_of_capacity=_float_between(
            values,
            "rate_fraction_of_capacity",
            0.0,
            1.0,
            "workload",
            include_lower=False,
        ),
        low_rate_fraction_of_capacity=_optional_fraction(
            values, "low_rate_fraction_of_capacity", "workload"
        ),
        high_rate_fraction_of_capacity=_optional_fraction(
            values, "high_rate_fraction_of_capacity", "workload"
        ),
        burst_probability=(
            _float_between(
                values,
                "burst_probability",
                0.0,
                1.0,
                "workload",
                include_lower=True,
            )
            if "burst_probability" in values
            else 0.5
        ),
        interval_s=_positive_float_or_default(values, "interval_s", "workload", 1.0),
    )
    if kind == "bursty" and (
        arrival.low_rate_fraction_of_capacity is None
        or arrival.high_rate_fraction_of_capacity is None
    ):
        raise ConfigError(
            "workload bursty arrivals require low_rate_fraction_of_capacity and "
            "high_rate_fraction_of_capacity"
        )
    if (
        arrival.low_rate_fraction_of_capacity is not None
        and arrival.high_rate_fraction_of_capacity is not None
        and arrival.low_rate_fraction_of_capacity > arrival.high_rate_fraction_of_capacity
    ):
        raise ConfigError(
            "workload.low_rate_fraction_of_capacity cannot exceed "
            "workload.high_rate_fraction_of_capacity"
        )

    return WorkloadConfig(
        name=_required_string(values, "name", "workload"),
        arrival=arrival,
        warmup_requests=_nonnegative_int(values, "warmup_requests", "workload"),
        prompt_buckets=buckets,
        source_path=path,
    )


def _load_prompt_bucket(value: Any, index: int) -> PromptBucket:
    section = f"workload.prompt_buckets[{index}]"
    if not isinstance(value, dict):
        raise ConfigError(f"{section} must be a TOML table")
    minimum_tokens = _positive_int(value, "minimum_tokens", section)
    maximum_tokens = _positive_int(value, "maximum_tokens", section)
    if minimum_tokens > maximum_tokens:
        raise ConfigError(f"{section}.minimum_tokens cannot exceed maximum_tokens")
    return PromptBucket(
        name=_required_string(value, "name", section),
        minimum_tokens=minimum_tokens,
        maximum_tokens=maximum_tokens,
        weight=_positive_float(value, "weight", section),
    )


def _load_toml(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"{label} configuration does not exist: {path}")
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {label} configuration {path}: {exc}") from exc
    return value


def _resolve_config_path(
    values: dict[str, Any], key: str, base_dir: Path, section: str
) -> Path:
    path = _resolve_path(values, key, base_dir, section)
    if not path.is_file():
        raise ConfigError(f"{section}.{key} does not exist: {path}")
    return path


def _resolve_path(values: dict[str, Any], key: str, base_dir: Path, section: str) -> Path:
    raw = _required_string(values, key, section)
    path = Path(raw).expanduser()
    return (base_dir / path).resolve() if not path.is_absolute() else path.resolve()


def _required_string(values: dict[str, Any], key: str, section: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{section}.{key} must be a non-empty string")
    return value.strip()


def _literal[T](
    values: dict[str, Any], key: str, choices: tuple[T, ...], section: str
) -> T:
    value = values.get(key)
    if value not in choices:
        choices_text = ", ".join(str(choice) for choice in choices)
        raise ConfigError(f"{section}.{key} must be one of: {choices_text}")
    return value


def _int_value(values: dict[str, Any], key: str, section: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{section}.{key} must be an integer")
    return value


def _positive_int(values: dict[str, Any], key: str, section: str) -> int:
    value = _int_value(values, key, section)
    if value <= 0:
        raise ConfigError(f"{section}.{key} must be greater than 0")
    return value


def _nonnegative_int(values: dict[str, Any], key: str, section: str) -> int:
    value = _int_value(values, key, section)
    if value < 0:
        raise ConfigError(f"{section}.{key} must be greater than or equal to 0")
    return value


def _positive_int_tuple(values: dict[str, Any], key: str, section: str) -> tuple[int, ...]:
    value = values.get(key)
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{section}.{key} must be a non-empty array of integers")
    result = tuple(value)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in result):
        raise ConfigError(f"{section}.{key} must contain only integers")
    if any(item < 0 for item in result):
        raise ConfigError(f"{section}.{key} must contain only non-negative integers")
    return result


def _optional_positive_float_tuple(
    values: dict[str, Any], key: str, section: str
) -> tuple[float, ...] | None:
    if key not in values:
        return None
    value = values[key]
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{section}.{key} must be a non-empty array of numbers")
    result = tuple(float(item) for item in value if not isinstance(item, bool))
    if len(result) != len(value) or any(not math.isfinite(item) or item <= 0 for item in result):
        raise ConfigError(f"{section}.{key} must contain only finite numbers greater than 0")
    return result


def _optional_positive_int_tuple(
    values: dict[str, Any], key: str, section: str
) -> tuple[int, ...] | None:
    if key not in values:
        return None
    value = values[key]
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{section}.{key} must be a non-empty array of integers")
    result = tuple(value)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in result):
        raise ConfigError(f"{section}.{key} must contain only integers")
    if any(item <= 0 for item in result):
        raise ConfigError(f"{section}.{key} must contain only integers greater than 0")
    return result


def _optional_string_tuple(
    values: dict[str, Any], key: str, section: str
) -> tuple[str, ...] | None:
    if key not in values:
        return None
    value = values[key]
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{section}.{key} must be a non-empty array of strings")
    result = tuple(value)
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise ConfigError(f"{section}.{key} must contain only non-empty strings")
    return tuple(item.strip() for item in result)


def _bool_or_default(
    values: dict[str, Any], key: str, section: str, default: bool
) -> bool:
    if key not in values:
        return default
    value = values[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{section}.{key} must be a boolean")
    return value


def _float_value(values: dict[str, Any], key: str, section: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{section}.{key} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ConfigError(f"{section}.{key} must be finite")
    return result


def _positive_float(values: dict[str, Any], key: str, section: str) -> float:
    value = _float_value(values, key, section)
    if value <= 0:
        raise ConfigError(f"{section}.{key} must be greater than 0")
    return value


def _positive_float_or_default(
    values: dict[str, Any], key: str, section: str, default: float
) -> float:
    if key not in values:
        return default
    return _positive_float(values, key, section)


def _positive_int_or_default(
    values: dict[str, Any], key: str, section: str, default: int
) -> int:
    if key not in values:
        return default
    return _positive_int(values, key, section)


def _nonnegative_float(values: dict[str, Any], key: str, section: str) -> float:
    value = _float_value(values, key, section)
    if value < 0:
        raise ConfigError(f"{section}.{key} must be greater than or equal to 0")
    return value


def _nonnegative_float_or_default(
    values: dict[str, Any], key: str, section: str, default: float
) -> float:
    if key not in values:
        return default
    return _nonnegative_float(values, key, section)


def _float_between(
    values: dict[str, Any],
    key: str,
    lower: float,
    upper: float,
    section: str,
    *,
    include_lower: bool,
) -> float:
    value = _float_value(values, key, section)
    lower_ok = value >= lower if include_lower else value > lower
    if not lower_ok or value > upper:
        lower_text = ">=" if include_lower else ">"
        raise ConfigError(
            f"{section}.{key} must be {lower_text} {lower} and <= {upper}"
        )
    return value


def _optional_fraction(values: dict[str, Any], key: str, section: str) -> float | None:
    if key not in values:
        return None
    return _float_between(values, key, 0.0, 1.0, section, include_lower=True)
