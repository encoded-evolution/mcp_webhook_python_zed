"""Test script to verify config module functionality."""

from mcp_webhook.config import Settings, get_settings

def test_config_module():
    """Verify config module can be imported and instantiated."""
    print("Testing config module...")

    # Test 1: Import and instantiate settings
    settings = Settings()
    print(f"✓ Settings instantiated successfully")

    # Test 2: Verify default values match .env.example
    assert settings.port == 9000, f"Expected port 9000, got {settings.port}"
    print(f"✓ Port: {settings.port}")

    assert settings.mcp_name == "MCP-STDIO-Server", f"Expected 'MCP-STDIO-Server', got {settings.mcp_name}"
    print(f"✓ MCP Name: {settings.mcp_name}")

    assert settings.webhook_bearer_tokens == "", f"Expected empty bearer tokens, got '{settings.webhook_bearer_tokens}'"
    print(f"✓ Bearer tokens (raw): '{settings.webhook_bearer_tokens}'")

    assert settings.async_processing is False, f"Expected async_processing=False, got {settings.async_processing}"
    print(f"✓ Async processing: {settings.async_processing}")

    assert settings.mapping_file == "/app/config/mapping.yml", f"Expected '/app/config/mapping.yml', got {settings.mapping_file}"
    print(f"✓ Mapping file: {settings.mapping_file}")

    assert settings.log_level == "INFO", f"Expected 'INFO', got {settings.log_level}"
    print(f"✓ Log level: {settings.log_level}")

    # Test 3: Verify WEBHOOK_BEARER_TOKENS empty yields empty list
    assert settings.bearer_tokens_list == [], f"Expected empty list, got {settings.bearer_tokens_list}"
    print(f"✓ Bearer tokens list (empty): {settings.bearer_tokens_list}")

    # Test 4: Verify auth is disabled when no tokens
    assert settings.auth_enabled is False, f"Expected auth_enabled=False, got {settings.auth_enabled}"
    print(f"✓ Auth enabled: {settings.auth_enabled}")

    # Test 5: Test get_settings singleton
    from mcp_webhook.config import reset_settings
    reset_settings()
    settings_singleton1 = get_settings()
    settings_singleton2 = get_settings()
    assert settings_singleton1 is settings_singleton2, "get_settings should return same instance"
    print(f"✓ get_settings() returns singleton")

    # Test 6: Test with custom tokens
    custom_settings = Settings(webhook_bearer_tokens="token1,token2")
    assert custom_settings.bearer_tokens_list == ["token1", "token2"], f"Expected ['token1', 'token2'], got {custom_settings.bearer_tokens_list}"
    assert custom_settings.auth_enabled is True, f"Expected auth_enabled=True, got {custom_settings.auth_enabled}"
    print(f"✓ Custom tokens work: {custom_settings.bearer_tokens_list}")
    print(f"✓ Auth enabled with tokens: {custom_settings.auth_enabled}")

    print("\n✅ All config module tests passed!")

if __name__ == "__main__":
    test_config_module()
