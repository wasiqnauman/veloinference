"""Configuration for the gateway."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ADIP"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    batch_max_size: int = Field(default=8, ge=1)
    batch_max_wait_ms: int = Field(default=10, ge=1)
    queue_max_size: int = Field(default=1024, ge=1)
    mock_backend_base_latency_ms: int = Field(default=15, ge=0)
    mock_backend_per_item_latency_ms: int = Field(default=4, ge=0)

    model_config = SettingsConfigDict(env_prefix="ADIP_", extra="ignore")


settings = Settings()
