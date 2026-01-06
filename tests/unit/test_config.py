"""Unit tests for configuration module."""

import os
import pytest
from mcp_webhook.config import Settings, get_settings, reset_settings


class TestSettingsDefaults:
    """Test default configuration values."""

    def test_default_port(self):
        """Test default port is 9000."""
        settings = Settings()
        assert settings.port == 9000

    def test_default_mcp_name(self):
        """Test default MCP name."""
        settings = Settings()
        assert settings.mcp_name == "MCP-STDIO-Server"

    def test_default_webhook_bearer_tokens(self):
        """Test default bearer tokens is empty string."""
        settings = Settings()
        assert settings.webhook_bearer_tokens == ""

    def test_default_async_processing(self):
        """Test default async processing is False."""
        settings = Settings()
        assert settings.async_processing is False

    def test_default_mapping_file(self):
        """Test default mapping file path."""
        settings = Settings()
        assert settings.mapping_file == "/app/config/mapping.yml"

    def test_default_log_level(self):
        """Test default log level is INFO."""
        settings = Settings()
        assert settings.log_level == "INFO"


class TestSettingsValidation:
    """Test configuration validation."""

    def test_valid_log_levels(self):
        """Test all valid log levels are accepted."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in valid_levels:
            settings = Settings(log_level=level)
            assert settings.log_level == level

    def test_log_level_case_normalization(self):
        """Test log level is normalized to uppercase."""
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

        settings = Settings(log_level="Info")
        assert settings.log_level == "INFO"

    def test_invalid_log_level_raises_error(self):
        """Test invalid log level raises ValueError."""
        with pytest.raises(ValueError, match="log_level must be one of"):
            Settings(log_level="INVALID")

    def test_port_range_validation_min(self):
        """Test port below 1 raises validation error."""
        with pytest.raises(ValueError):
            Settings(port=0)

    def test_port_range_validation_max(self):
        """Test port above 65535 raises validation error."""
        with pytest.raises(ValueError):
            Settings(port=65536)

    def test_valid_port_values(self):
        """Test valid port values are accepted."""
        settings = Settings(port=8080)
        assert settings.port == 8080


class TestBearerTokensProperty:
    """Test bearer_tokens_list property behavior."""

    def test_empty_string_returns_empty_list(self):
        """Test empty bearer tokens string yields empty list."""
        settings = Settings(webhook_bearer_tokens="")
        assert settings.bearer_tokens_list == []

    def test_whitespace_only_returns_empty_list(self):
        """Test whitespace-only string yields empty list."""
        settings = Settings(webhook_bearer_tokens="   ")
        assert settings.bearer_tokens_list == []

    def test_single_token(self):
        """Test single token is parsed correctly."""
        settings = Settings(webhook_bearer_tokens="token123")
        assert settings.bearer_tokens_list == ["token123"]

    def test_multiple_tokens(self):
        """Test multiple tokens are parsed and trimmed."""
        settings = Settings(webhook_bearer_tokens="token1, token2,token3")
        assert settings.bearer_tokens_list == ["token1", "token2", "token3"]

    def test_tokens_with_extra_whitespace(self):
        """Test tokens are trimmed of leading/trailing whitespace."""
        settings = Settings(webhook_bearer_tokens="  token1  ,  token2  ,  token3  ")
        assert settings.bearer_tokens_list == ["token1", "token2", "token3"]

    def test_empty_tokens_in_list_are_filtered(self):
        """Test empty tokens resulting from split are filtered out."""
        settings = Settings(webhook_bearer_tokens="token1,,token2,,token3")
        assert settings.bearer_tokens_list == ["token1", "token2", "token3"]

    def test_token_with_spaces(self):
        """Test tokens can contain spaces if not trimmed."""
        settings = Settings(webhook_bearer_tokens="my secret token")
        assert settings.bearer_tokens_list == ["my secret token"]


class TestAuthEnabledProperty:
    """Test auth_enabled property behavior."""

    def test_auth_disabled_with_no_tokens(self):
        """Test auth is disabled when no tokens configured."""
        settings = Settings(webhook_bearer_tokens="")
        assert settings.auth_enabled is False

    def test_auth_disabled_with_whitespace_only(self):
        """Test auth is disabled with whitespace-only tokens."""
        settings = Settings(webhook_bearer_tokens="   ")
        assert settings.auth_enabled is False

    def test_auth_enabled_with_single_token(self):
        """Test auth is enabled with one token."""
        settings = Settings(webhook_bearer_tokens="token1")
        assert settings.auth_enabled is True

    def test_auth_enabled_with_multiple_tokens(self):
        """Test auth is enabled with multiple tokens."""
        settings = Settings(webhook_bearer_tokens="token1,token2,token3")
        assert settings.auth_enabled is True


class TestSettingsFromEnv:
    """Test settings loading from environment variables."""

    def test_port_from_env(self):
        """Test port loaded from environment variable."""
        env_value = "8080"
        settings = Settings(_env_file=None, **{"port": int(env_value)})
        assert settings.port == 8080

    def test_mcp_name_from_env(self):
        """Test MCP name loaded from environment variable."""
        settings = Settings(_env_file=None, mcp_name="CustomServer")
        assert settings.mcp_name == "CustomServer"

    def test_bearer_tokens_from_env(self):
        """Test bearer tokens loaded from environment variable."""
        settings = Settings(
            _env_file=None,
            webhook_bearer_tokens="tokenA,tokenB"
        )
        assert settings.webhook_bearer_tokens == "tokenA,tokenB"
        assert settings.bearer_tokens_list == ["tokenA", "tokenB"]

    def test_async_processing_from_env(self):
        """Test async processing loaded from environment variable."""
        settings = Settings(_env_file=None, async_processing=True)
        assert settings.async_processing is True

    def test_mapping_file_from_env(self):
        """Test mapping file path loaded from environment variable."""
        settings = Settings(
            _env_file=None,
            mapping_file="/custom/path/mapping.yml"
        )
        assert settings.mapping_file == "/custom/path/mapping.yml"


class TestGetSettingsSingleton:
    """Test get_settings singleton behavior."""

    def test_get_settings_returns_singleton(self):
        """Test get_settings returns same instance on subsequent calls."""
        reset_settings()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_creates_new_instance_after_reset(self):
        """Test reset_settings causes new instance to be created."""
        settings1 = get_settings()
        reset_settings()
        settings2 = get_settings()
        assert settings1 is not settings2

    def test_get_settings_with_custom_values(self):
        """Test get_settings can be configured via environment."""
        reset_settings()
        # Create settings with custom values via kwargs
        settings = Settings(port=9999)
        assert settings.port == 9999


class TestSettingsIntegration:
    """Integration tests for settings behavior."""

    def test_default_configuration_matches_env_example(self):
        """Test that default settings match .env.example defaults."""
        settings = Settings()

        # These values should match .env.example defaults
        assert settings.port == 9000
        assert settings.mcp_name == "MCP-STDIO-Server"
        assert settings.webhook_bearer_tokens == ""
        assert settings.async_processing is False
        assert settings.mapping_file == "/app/config/mapping.yml"
        assert settings.log_level == "INFO"

    def test_full_configuration(self):
        """Test settings with all fields customized."""
        settings = Settings(
            port=8080,
            mcp_name="TestServer",
            webhook_bearer_tokens="token1,token2",
            async_processing=True,
            mapping_file="/test/path/mapping.yml",
            log_level="DEBUG"
        )

        assert settings.port == 8080
        assert settings.mcp_name == "TestServer"
        assert settings.webhook_bearer_tokens == "token1,token2"
        assert settings.bearer_tokens_list == ["token1", "token2"]
        assert settings.auth_enabled is True
        assert settings.async_processing is True
        assert settings.mapping_file == "/test/path/mapping.yml"
        assert settings.log_level == "DEBUG"

    def test_auth_flow_scenarios(self):
        """Test various authentication configuration scenarios."""
        # Scenario 1: No auth (default)
        settings = Settings()
        assert settings.auth_enabled is False
        assert settings.bearer_tokens_list == []

        # Scenario 2: Auth enabled
        settings = Settings(webhook_bearer_tokens="secret123")
        assert settings.auth_enabled is True
        assert "secret123" in settings.bearer_tokens_list

        # Scenario 3: Multiple auth tokens
        settings = Settings(webhook_bearer_tokens="token1,token2,token3")
        assert settings.auth_enabled is True
        assert len(settings.bearer_tokens_list) == 3
