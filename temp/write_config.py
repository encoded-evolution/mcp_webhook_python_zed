"""Script to generate config.py with proper content."""

import os

config_content = '''"""Configuration management for MCP STDIO Webhook Server.

This module uses Pydantic BaseSettings to manage configuration from environment
variables, providing type safety, validation, and default values.
"""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings can be overridden by environment variables. The model
    automatically reads from the environment and validates values.
    """

    port: int = Field(
        default=9000,
        ge=1,
        le=65535,
        description="Port for stdio-proxy TCP listener",
    )

    mcp_name: str = Field(
        default="MCP-STDIO-Server",
        description="Human-friendly server name",
    )

    webhook_bearer_tokens: List[str] = Field(
        default_factory=list,
        description="Comma-separated bearer tokens for authentication",
    )

    async_processing: bool = Field(
        default=False,
        description="Enable asynchronous processing mode",
    )

    mapping_file: str = Field(
        default="/app/config/mapping.yml",
        description="Path to event mapping configuration file",
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate that log_level is a valid Python logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(
                f"log_level must be one of {', '.join(sorted(valid_levels))}, got '{v}'"
            )
        return v.upper()

    @field_validator("webhook_bearer_tokens", mode="before")
    @classmethod
    def parse_tokens(cls, v: object) -> List[str]:
        """Parse webhook_bearer_tokens from environment variable.

        Accepts either a comma-separated string or a list.
        Empty string or None returns an empty list.
        """
        if isinstance(v, list):
            return [token.strip() for token in v if token.strip()]
        if isinstance(v, str) and v.strip():
            return [token.strip() for token in v.split(",") if token.strip()]
        return []


settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance.

    Returns:
        Settings: The application settings object.
    """
    return settings


__all__ = ["Settings", "settings", "get_settings"]
'''

# Get the correct paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
config_path = os.path.join(project_dir, "src", "mcp_webhook", "config.py")

# Write the config.py file
with open(config_path, "w", encoding="utf-8") as f:
    f.write(config_content)

print(f"Created config.py at {config_path}")
