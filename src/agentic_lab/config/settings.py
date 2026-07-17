from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration. Secrets are intentionally never serialized or logged."""

    model_config = SettingsConfigDict(env_prefix="AGENTIC_LAB_")

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
    openrouter_api_key: SecretStr | None = None
    allowed_model_ids: frozenset[str] = Field(default_factory=frozenset)
    allowed_provider_ids: frozenset[str] = Field(default_factory=frozenset)
    github_app_id: int | None = Field(default=None, gt=0)
    github_private_key: SecretStr | None = None
    github_api_url: str = "https://api.github.com"
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str | None = None
    executor_image_digest: str | None = None
    require_target_manifest: bool = False

    @field_validator(
        "openrouter_api_key",
        "github_private_key",
        "langfuse_public_key",
        "langfuse_secret_key",
        mode="before",
    )
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("github_app_id", mode="before")
    @classmethod
    def empty_app_id_is_none(cls, value: object) -> object:
        return None if value == "" else value

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

    @field_validator("allowed_model_ids", mode="before")
    @classmethod
    def parse_model_ids(cls, value: object) -> frozenset[str]:
        if value is None or value == "":
            return frozenset()
        if isinstance(value, str):
            return frozenset(part.strip() for part in value.split(",") if part.strip())
        return frozenset(str(item) for item in value)  # type: ignore[arg-type]

    @field_validator("allowed_provider_ids", mode="before")
    @classmethod
    def parse_provider_ids(cls, value: object) -> frozenset[str]:
        if value is None or value == "":
            return frozenset()
        if isinstance(value, str):
            return frozenset(part.strip() for part in value.split(",") if part.strip())
        return frozenset(str(item) for item in value)  # type: ignore[arg-type]

    def readiness_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.allowed_repository_ids:
            errors.append("repository_allowlist_empty")
        if (self.openrouter_api_key is None) != (not self.allowed_model_ids):
            errors.append("incomplete_model_configuration")
        if self.openrouter_api_key is not None and not self.allowed_provider_ids:
            errors.append("provider_allowlist_empty")
        if (self.github_app_id is None) != (self.github_private_key is None):
            errors.append("incomplete_github_app_configuration")
        if (self.langfuse_public_key is None) != (self.langfuse_secret_key is None):
            errors.append("incomplete_langfuse_configuration")
        if self.executor_image_digest and not re.fullmatch(
            r"[^\s@]+@sha256:[0-9a-f]{64}", self.executor_image_digest
        ):
            errors.append("invalid_executor_image_digest")
        if self.require_target_manifest:
            if self.openrouter_api_key is None or not self.allowed_model_ids:
                errors.append("model_gateway_not_configured")
            if self.github_app_id is None or self.github_private_key is None:
                errors.append("github_app_not_configured")
            if self.langfuse_public_key is None or self.langfuse_secret_key is None:
                errors.append("langfuse_not_configured")
            if self.executor_image_digest is None:
                errors.append("executor_image_not_configured")
        return tuple(errors)


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=".env")
