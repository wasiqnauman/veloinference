"""Configuration for the gateway."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ADIP"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    backend_kind: Literal["mock", "vllm"] = "mock"
    gateway_mode: Literal["pass_through", "batched"] = "batched"
    batch_policy: Literal["fixed", "adaptive"] = "fixed"
    batch_max_size: int = Field(default=8, ge=1)
    batch_max_wait_ms: int = Field(default=10, ge=0)
    queue_max_size: int = Field(default=1024, ge=1)
    mock_backend_base_latency_ms: int = Field(default=15, ge=0)
    mock_backend_per_item_latency_ms: int = Field(default=4, ge=0)
    vllm_base_url: str = "http://127.0.0.1:8001"
    vllm_api_key: str | None = None
    vllm_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    vllm_timeout_s: float = Field(default=120.0, gt=0)
    adaptive_ewma_alpha: float = Field(default=0.2, gt=0, le=1)
    adaptive_low_load_threshold: float = Field(default=1.0, ge=0)
    research_telemetry: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="ADIP_", extra="ignore")


settings = Settings()
