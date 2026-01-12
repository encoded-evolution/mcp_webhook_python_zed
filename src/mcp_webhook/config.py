"""Configuration management for MCP Webhook Server.

This module uses Pydantic BaseSettings to load configuration from environment
variables and provide type-safe access to settings throughout the application.
"""

from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Settings can be overridden by:
    - Environment variables
    - .env file (if present)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server Configuration
    port: int = Field(
        default=9000,
        description="Port for stdio-proxy listener",
        ge=1,
        le=65535,
    )

    mcp_name: str = Field(
        default="MCP-STDIO-Server",
        description="Human-friendly server name",
    )

    # Authentication
    webhook_bearer_tokens: str = Field(
        default="",
        description="Comma-separated bearer tokens; empty disables auth",
    )

    # Processing
    async_processing: bool = Field(
        default=False,
        description="Enable asynchronous processing",
    )

    # File Paths
    mapping_file: str = Field(
        default="/app/config/mapping.yml",
        description="Path to mapping configuration file",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Redis Configuration
    redis_url: str = Field(
        default="",
        description="Redis connection URL (e.g., redis://localhost:6379/0); empty disables Redis queue",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f"log_level must be one of {valid_levels}, got '{v}'"
            )
        return v_upper

    @property
    def bearer_tokens_list(self) -> List[str]:
        """Parse comma-separated bearer tokens into a list.

        Returns empty list if webhook_bearer_tokens is empty string.
        Trims whitespace from each token.
        """
        if not self.webhook_bearer_tokens.strip():
            return []
        tokens = [t.strip() for t in self.webhook_bearer_tokens.split(",")]
        return [t for t in tokens if t]

    @property
    def auth_enabled(self) -> bool:
        """Check if authentication is enabled.

        Returns True if at least one bearer token is configured.
        """
        return len(self.bearer_tokens_list) > 0

    @property
    def redis_enabled(self) -> bool:
        """Check if Redis queue is enabled.

        Returns True if redis_url is configured and non-empty.
        """
        return bool(self.redis_url.strip())


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance.

    Creates the instance on first call and reuses it for subsequent calls.

    Returns:
        Settings: The application settings instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset the global settings instance.

    Primarily used in tests to ensure clean state between test cases.
    """
    global _settings
    _settings = None
