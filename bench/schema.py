"""Immutable records shared by benchmark configuration and later runners."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Resolved model and generation settings used by one experiment."""

    model_id: str
    served_name: str
    revision: str
    dtype: Literal["auto", "float16", "bfloat16", "float32"]
    max_model_len: int
    gpu_memory_utilization: float
    max_num_seqs: int
    temperature: float
    max_tokens: int


@dataclass(frozen=True, slots=True)
class PromptBucket:
    """One inclusive input-token range and its workload sampling weight."""

    name: str
    minimum_tokens: int
    maximum_tokens: int
    weight: float


@dataclass(frozen=True, slots=True)
class ArrivalConfig:
    """Arrival-process settings resolved from a workload TOML file."""

    kind: Literal["constant", "poisson", "bursty"]
    duration_s: float
    seed: int
    rate_fraction_of_capacity: float
    low_rate_fraction_of_capacity: float | None = None
    high_rate_fraction_of_capacity: float | None = None
    burst_probability: float = 0.5
    interval_s: float = 1.0


@dataclass(frozen=True, slots=True)
class WorkloadConfig:
    """Prompt distribution and arrival process for one benchmark condition."""

    name: str
    arrival: ArrivalConfig
    warmup_requests: int
    prompt_buckets: tuple[PromptBucket, ...]
    source_path: Path


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """Fully resolved experiment configuration loaded from TOML files."""

    name: str
    model_config_path: Path
    workload_config_path: Path
    model: ModelConfig
    workload: WorkloadConfig
    target_endpoint: Literal["direct", "adip"]
    gateway_mode: Literal["pass_through", "batched"]
    policy: Literal["fixed", "adaptive"]
    max_batch_size: int
    max_wait_ms: int
    repetition_seeds: tuple[int, ...]
    cooldown_s: float
    output_dir: Path
    slo_derivation_rule: str
    health_url: str
    source_path: Path


@dataclass(frozen=True, slots=True)
class PlannedRequest:
    """One request generated before an open-loop run begins."""

    schema_version: int
    experiment_id: str
    run_id: str
    request_index: int
    policy: str
    model: str
    workload: str
    seed: int
    arrival_offset_s: float
    prompt: str
    input_tokens: int
    max_tokens: int
    temperature: float
    deadline_ms: int | None


@dataclass(frozen=True, slots=True)
class RequestResult:
    """Normalized request-level observation written to requests.jsonl."""

    schema_version: int
    experiment_id: str
    run_id: str
    request_index: int
    policy: str
    model: str
    workload: str
    seed: int
    target_arrival_s: float
    actual_arrival_s: float
    completed_s: float | None
    input_tokens: int
    output_tokens: int | None
    batch_id: str | None
    batch_size: int | None
    queue_ms: float | None
    backend_ms: float | None
    latency_ms: float | None
    deadline_ms: int | None
    deadline_met: bool | None
    status_code: int | None
    error_type: str | None


@dataclass(frozen=True, slots=True)
class GpuSample:
    """One independent nvidia-smi observation."""

    schema_version: int
    experiment_id: str
    run_id: str
    sampled_at_utc: str
    index: str | None
    name: str | None
    utilization_gpu_percent: float | None
    memory_used_mb: float | None
    memory_total_mb: float | None
    power_draw_w: float | None
    temperature_gpu_c: float | None
    error_type: str | None


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Metadata captured before a run sends benchmark traffic."""

    schema_version: int
    experiment_id: str
    run_id: str
    started_at_utc: str
    ended_at_utc: str | None
    git_commit: str
    git_dirty: bool
    configuration: Mapping[str, object]
    random_seed: int
    model_id: str
    model_revision: str
    vllm_version: str | None
    hardware: Mapping[str, object]
    warmup_requests: int
    measurement_duration_s: float
    commands: tuple[str, ...]
    gpu_telemetry_available: bool


@dataclass(frozen=True, slots=True)
class SummaryRecord:
    """Publication-facing aggregate metrics for one completed run."""

    schema_version: int
    experiment_id: str
    run_id: str
    offered_request_rate: float
    achieved_request_throughput: float
    achieved_output_token_throughput: float
    success_count: int
    failure_count: int
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    p99_latency_ms: float | None
    mean_queue_ms: float | None
    p95_queue_ms: float | None
    mean_backend_ms: float | None
    mean_batch_size: float | None
    slo_attainment_percent: float | None
    mean_gpu_utilization_percent: float | None
    max_vram_used_mb: float | None
    mean_power_draw_w: float | None
    p95_arrival_drift_ms: float | None
