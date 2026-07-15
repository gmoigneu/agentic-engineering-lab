from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration. Secrets are intentionally never serialized or logged."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGENTIC_LAB_")

    database_url: str = "postgresql+psycopg://agentic_lab:agentic_lab@postgres:5432/agentic_lab"
    operator_token: SecretStr
    github_webhook_secret: SecretStr
    allowed_repository_ids: frozenset[int] = Field(default_factory=frozenset)
    environment: str = "local"
    lease_seconds: int = Field(default=60, ge=10, le=3600)
    max_model_turns: int = Field(default=12, ge=1)
    max_tool_calls: int = Field(default=40, ge=1)
    max_wall_seconds: int = Field(default=1200, ge=1)
    max_usd: float = Field(default=3.0, gt=0)

    @field_validator("allowed_repository_ids", mode="before")
    @classmethod
    def parse_repository_ids(cls, value: object) -> frozenset[int]:
        if value is None or value == "":
            return frozenset()
        if isinstance(value, int):
            return frozenset({value})
        if isinstance(value, str):
            return frozenset(int(part.strip()) for part in value.split(",") if part.strip())
        return frozenset(int(item) for item in value)  # type: ignore[arg-type]


@lru_cache
def get_settings() -> Settings:
    return Settings()
