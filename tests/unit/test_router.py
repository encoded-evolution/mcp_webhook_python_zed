"""Unit tests for envelope router module."""

import pytest
from mcp_webhook.router import (
    AuthError,
    RouterError,
    RoutingResponse,
    validate_auth,
    resolve_tool_mapping,
    extract_tool_args,
    invoke_tool,
    route_envelope,
    route_envelope_with_dict,
)
from mcp_webhook.envelope import Envelope, Meta
from mcp_webhook.mapping import MappingEntry, MappingConfig
from mcp_webhook.config import Settings, reset_settings
from mcp_webhook.tools import (
    AckEventResponse,
    ProcessPayloadResponse,
    clear_recent_events,
)


class TestAuthError:
    """Tests for the AuthError exception."""

    def test_auth_error_creation(self):
        """Test creating AuthError with custom message."""
        error = AuthError("Invalid token")
        assert error.message == "Invalid token"

    def test_auth_error_default_message(self):
        """Test creating AuthError with default message."""
        error = AuthError()
        assert error.message == "Authentication failed"


class TestRouterError:
    """Tests for the RouterError exception."""

    def test_router_error_creation(self):
        """Test creating RouterError with message and details."""
        error = RouterError("Tool not found", details={"tool": "unknown"})
        assert error.message == "Tool not found"
        assert error.details == {"tool": "unknown"}

    def test_router_error_without_details(self):
        """Test creating RouterError without details."""
        error = RouterError("Generic error")
        assert error.message == "Generic error"
        assert error.details == {}


class TestRoutingResponse:
    """Tests for the RoutingResponse Pydantic model."""

    def test_success_response(self):
        """Test creating a successful routing response."""
        response = RoutingResponse(
            success=True,
            tool="process_payload",
            result={"path": "/file.py", "user_id": "alice"},
            error=None,
        )
        assert response.success is True
        assert response.tool == "process_payload"
        assert response.result == {"path": "/file.py", "user_id": "alice"}
        assert response.error is None

    def test_error_response(self):
        """Test creating an error routing response."""
        response = RoutingResponse(
            success=False,
            tool=None,
            result=None,
            error="Invalid token",
        )
        assert response.success is False
        assert response.tool is None
        assert response.result is None
        assert response.error == "Invalid token"


class TestValidateAuth:
    """Tests for authentication validation."""

    def test_auth_disabled_skips_validation(self):
        """Test that validation is skipped when auth is disabled."""
        # Reset settings with no tokens
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = ""
        settings = Settings()
        reset_settings()

        # Create envelope without meta
        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
        )

        # Should not raise error
        validate_auth(envelope)

    def test_auth_disabled_with_whitespace_tokens(self):
        """Test that validation is skipped with whitespace-only tokens."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "   "
        settings = Settings()
        reset_settings()

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
        )

        # Should not raise error
        validate_auth(envelope)

    def test_auth_enabled_with_valid_token(self):
        """Test validation with valid token."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "token123"
        settings = Settings()
        reset_settings()

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
            meta=Meta(auth="token123"),
        )

        # Should not raise error
        validate_auth(envelope)

    def test_auth_enabled_with_valid_second_token(self):
        """Test validation with second valid token."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "token1,token2"
        settings = Settings()
        reset_settings()

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
            meta=Meta(auth="token2"),
        )

        # Should not raise error
        validate_auth(envelope)

    def test_auth_enabled_with_valid_token_with_spaces(self):
        """Test validation trims whitespace from tokens."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "token1, token2 , token3"
        settings = Settings()
        reset_settings()

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
            meta=Meta(auth="token2"),
        )

        # Should not raise error
        validate_auth(envelope)

    def test_auth_enabled_missing_meta_raises_error(self):
        """Test validation raises error when meta is missing."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "token123"
        settings = Settings()
        reset_settings()

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
        )

        with pytest.raises(AuthError, match="Authentication required: envelope missing 'meta' field"):
            validate_auth(envelope)

    def test_auth_enabled_missing_token_raises_error(self):
        """Test validation raises error when token is missing."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "token123"
        settings = Settings()
        reset_settings()

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
            meta=Meta(auth=None),
        )

        with pytest.raises(AuthError, match="Authentication required: envelope missing 'auth' token"):
            validate_auth(envelope)

    def test_auth_enabled_with_invalid_token_raises_error(self):
        """Test validation raises error with invalid token."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "token123"
        settings = Settings()
        reset_settings()

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
            meta=Meta(auth="invalid"),
        )

        with pytest.raises(AuthError, match="Authentication failed: invalid token"):
            validate_auth(envelope)

    def test_auth_enabled_with_empty_token_raises_error(self):
        """Test validation raises error with empty token."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "token123"
        settings = Settings()
        reset_settings()

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
            meta=Meta(auth=""),
        )

        with pytest.raises(AuthError, match="Authentication failed: invalid token"):
            validate_auth(envelope)


class TestResolveToolMapping:
    """Tests for tool mapping resolution."""

    def test_resolve_valid_mapping(self):
        """Test resolving a valid mapping."""
        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="ack_event",
                    args={},
                )
            ]
        )

        result = resolve_tool_mapping("file.save", mapping_config)

        assert result["tool"] == "ack_event"
        assert result["tool_func"].__name__ == "ack_event"
        assert result["args"] == {}

    def test_resolve_process_payload_mapping(self):
        """Test resolving process_payload mapping."""
        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="process_payload",
                    args={"path": "payload.path", "user_id": "payload.user.id"},
                )
            ]
        )

        result = resolve_tool_mapping("file.save", mapping_config)

        assert result["tool"] == "process_payload"
        assert result["tool_func"].__name__ == "process_payload"
        assert result["args"] == {"path": "payload.path", "user_id": "payload.user.id"}

    def test_resolve_list_recent_events_mapping(self):
        """Test resolving list_recent_events mapping."""
        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="admin.list",
                    tool="list_recent_events",
                    args={},
                )
            ]
        )

        result = resolve_tool_mapping("admin.list", mapping_config)

        assert result["tool"] == "list_recent_events"
        assert result["tool_func"].__name__ == "list_recent_events"
        assert result["args"] == {}

    def test_resolve_mapping_not_found_raises_error(self):
        """Test that error is raised when mapping is not found."""
        mapping_config = MappingConfig(mappings=[])

        with pytest.raises(RouterError, match="No mapping found for event type"):
            resolve_tool_mapping("unknown.event", mapping_config)

    def test_resolve_unregistered_tool_raises_error(self):
        """Test that error is raised for unregistered tool."""
        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="unknown_tool",
                    args={},
                )
            ]
        )

        with pytest.raises(RouterError, match="Tool 'unknown_tool' is not registered"):
            resolve_tool_mapping("file.save", mapping_config)


class TestExtractToolArgs:
    """Tests for argument extraction from envelopes."""

    def test_extract_single_argument(self):
        """Test extracting a single argument."""
        mapping_args = {"path": "path"}
        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/repo/file.py"},
        )

        result = extract_tool_args(mapping_args, envelope)

        assert result == {"path": "/repo/file.py"}

    def test_extract_multiple_arguments(self):
        """Test extracting multiple arguments."""
        mapping_args = {
            "path": "path",
            "user_id": "user.id",
            "filename": "meta.name",
        }
        envelope = Envelope(
            event_type="file.save",
            payload={
                "path": "/repo/file.py",
                "user": {"id": "alice"},
                "meta": {"name": "file.py"},
            },
        )

        result = extract_tool_args(mapping_args, envelope)

        assert result == {
            "path": "/repo/file.py",
            "user_id": "alice",
            "filename": "file.py",
        }

    def test_extract_nested_arguments(self):
        """Test extracting deeply nested arguments."""
        mapping_args = {"value": "data.level1.level2.level3"}
        envelope = Envelope(
            event_type="data.sync",
            payload={
                "data": {
                    "level1": {
                        "level2": {
                            "level3": "deep_value"
                        }
                    }
                }
            },
        )

        result = extract_tool_args(mapping_args, envelope)

        assert result == {"value": "deep_value"}

    def test_extract_empty_args(self):
        """Test extracting with empty mapping args."""
        mapping_args = {}
        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
        )

        result = extract_tool_args(mapping_args, envelope)

        assert result == {}

    def test_extract_with_different_types(self):
        """Test extracting values of different types."""
        mapping_args = {
            "string_val": "str",
            "int_val": "int",
            "bool_val": "bool",
            "list_val": "list",
            "dict_val": "dict",
            "null_val": "null",
        }
        envelope = Envelope(
            event_type="test",
            payload={
                "str": "text",
                "int": 42,
                "bool": True,
                "list": [1, 2, 3],
                "dict": {"key": "value"},
                "null": None,
            },
        )

        result = extract_tool_args(mapping_args, envelope)

        assert result == {
            "string_val": "text",
            "int_val": 42,
            "bool_val": True,
            "list_val": [1, 2, 3],
            "dict_val": {"key": "value"},
            "null_val": None,
        }

    def test_extract_missing_key_raises_error(self):
        """Test that error is raised for missing key."""
        mapping_args = {"missing": "payload.nonexistent"}
        envelope = Envelope(
            event_type="test",
            payload={"exists": "value"},
        )

        with pytest.raises(RouterError, match="Failed to extract argument 'missing'"):
            extract_tool_args(mapping_args, envelope)

    def test_extract_invalid_path_raises_error(self):
        """Test that error is raised for invalid path."""
        mapping_args = {"value": "payload.user.invalid"}
        envelope = Envelope(
            event_type="test",
            payload={"user": "not_a_dict"},
        )

        with pytest.raises(RouterError, match="Failed to extract argument 'value'"):
            extract_tool_args(mapping_args, envelope)

    def test_extract_empty_dot_path_raises_error(self):
        """Test that error is raised for empty dot path."""
        mapping_args = {"value": ""}
        envelope = Envelope(
            event_type="test",
            payload={"key": "value"},
        )

        with pytest.raises(RouterError, match="Argument 'value' has empty dot path"):
            extract_tool_args(mapping_args, envelope)


class TestInvokeTool:
    """Tests for tool invocation."""

    def test_invoke_ack_event(self):
        """Test invoking ack_event tool."""
        from mcp_webhook.tools import ack_event

        resolved_args = {"event_type": "file.save", "payload": {"path": "/file.py"}}

        result = invoke_tool(ack_event, resolved_args)

        assert result["success"] is True
        assert result["event_type"] == "file.save"
        assert "message" in result

    def test_invoke_process_payload(self):
        """Test invoking process_payload tool."""
        from mcp_webhook.tools import process_payload

        resolved_args = {"path": "/file.py", "user_id": "alice"}

        result = invoke_tool(process_payload, resolved_args)

        assert result["success"] is True
        assert result["path"] == "/file.py"
        assert result["user_id"] == "alice"

    def test_invoke_list_recent_events(self):
        """Test invoking list_recent_events tool."""
        from mcp_webhook.tools import list_recent_events

        # Add some events
        clear_recent_events()
        list_recent_events()

        resolved_args = {}

        result = invoke_tool(list_recent_events, resolved_args)

        assert "count" in result
        assert "events" in result
        assert "buffer_size" in result

    def test_invoke_with_additional_kwargs(self):
        """Test invoking tool with additional kwargs."""
        from mcp_webhook.tools import list_recent_events

        resolved_args = {}
        kwargs = {"max_count": 5}

        result = invoke_tool(list_recent_events, resolved_args, **kwargs)

        assert "count" in result
        assert result["count"] <= 5

    def test_invoke_with_invalid_args_raises_error(self):
        """Test that error is raised for invalid arguments."""
        from mcp_webhook.tools import process_payload

        # Missing required argument
        resolved_args = {"path": "/file.py"}  # Missing user_id

        with pytest.raises(RouterError, match="Tool invocation failed"):
            invoke_tool(process_payload, resolved_args)

    def test_invoke_with_type_error_raises_error(self):
        """Test that error is raised for type errors."""
        from mcp_webhook.tools import process_payload

        # Wrong argument type
        resolved_args = {"path": 123, "user_id": "alice"}

        with pytest.raises(RouterError, match="Tool invocation failed"):
            invoke_tool(process_payload, resolved_args)


class TestRouteEnvelope:
    """Tests for main envelope routing."""

    def test_route_valid_envelope_with_auth(self):
        """Test routing a valid envelope with authentication."""
        clear_recent_events()
        reset_settings()

        # Create mapping config with args that map to process_payload
        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="process_payload",
                    args={"path": "path", "user_id": "user.id"},
                )
            ]
        )

        # Create envelope
        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py", "user": {"id": "alice"}},
            meta=Meta(auth="token123"),
        )

        # Route envelope
        response = route_envelope(envelope, mapping_config)

        assert response.success is True
        assert response.tool == "process_payload"
        assert response.result is not None
        assert response.error is None
        assert response.result["success"] is True
        assert response.result["path"] == "/file.py"
        assert response.result["user_id"] == "alice"

    def test_route_envelope_without_auth(self):
        """Test routing envelope when auth is disabled."""
        clear_recent_events()
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = ""
        from mcp_webhook.config import Settings
        settings = Settings()
        reset_settings()

        # Create mapping config with args for ack_event
        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.open",
                    tool="ack_event",
                    args={"event_type": "event_type", "payload": "payload"},
                )
            ]
        )

        envelope = Envelope(
            event_type="file.open",
            payload={"event_type": "file.open", "payload": {"path": "/file.py"}},
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is True
        assert response.tool == "ack_event"
        assert response.result is not None
        assert response.error is None
        assert response.result["success"] is True
        assert response.result["event_type"] == "file.open"
        assert response.result["event_type"] == "file.open"

    def test_route_envelope_with_invalid_token(self):
        """Test routing envelope with invalid token."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "valid-token"
        from mcp_webhook.config import Settings
        settings = Settings()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="ack_event",
                    args={"event_type": "event_type", "payload": "payload"},
                )
            ]
        )

        envelope = Envelope(
            event_type="file.save",
            payload={"event_type": "file.save", "payload": {"path": "/file.py"}},
            meta=Meta(auth="invalid-token"),
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is False
        assert response.tool is None
        assert response.result is None
        assert response.error is not None
        assert "Authentication failed" in response.error

    def test_route_envelope_missing_meta_with_auth(self):
        """Test routing envelope missing meta when auth is enabled."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "token123"
        from mcp_webhook.config import Settings
        settings = Settings()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="ack_event",
                    args={"event_type": "event_type", "payload": "payload"},
                )
            ]
        )

        envelope = Envelope(
            event_type="file.save",
            payload={"event_type": "file.save", "payload": {"path": "/file.py"}},
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is False
        assert response.tool is None
        assert response.result is None
        assert response.error is not None
        assert "Authentication required" in response.error

    def test_route_envelope_no_mapping_found(self):
        """Test routing envelope with no matching mapping."""
        reset_settings()

        mapping_config = MappingConfig(mappings=[])

        envelope = Envelope(
            event_type="unknown.event",
            payload={"path": "/file.py"},
            meta=Meta(auth="token123"),
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is False
        assert response.tool is None
        assert response.result is None
        assert response.error is not None
        assert "No mapping found" in response.error

    def test_route_envelope_unregistered_tool(self):
        """Test routing envelope with unregistered tool."""
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="unknown_tool",
                    args={},
                )
            ]
        )

        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/file.py"},
            meta=Meta(auth="token123"),
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is False
        assert response.tool is None
        assert response.result is None
        assert response.error is not None
        assert "not registered" in response.error

    def test_route_envelope_argument_extraction_failure(self):
        """Test routing envelope with argument extraction failure."""
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="process_payload",
                    args={"path": "nonexistent"},
                )
            ]
        )

        envelope = Envelope(
            event_type="file.save",
            payload={"exists": "value"},
            meta=Meta(auth="token123"),
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is False
        assert response.tool is None
        assert response.result is None
        assert response.error is not None
        assert "Failed to extract argument" in response.error

    def test_route_envelope_with_complex_workflow(self):
        """Test routing envelope with complex nested arguments."""
        clear_recent_events()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="data.process",
                    tool="process_payload",
                    args={
                        "path": "data.file_path",
                        "user_id": "metadata.user.id",
                    },
                )
            ]
        )

        envelope = Envelope(
            event_type="data.process",
            payload={
                "data": {"file_path": "/repo/deep/file.py"},
                "metadata": {"user": {"id": "charlie"}},
            },
            meta=Meta(auth="token123"),
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is True
        assert response.tool == "process_payload"
        assert response.result is not None
        assert response.error is None
        assert response.result["success"] is True
        assert response.result["path"] == "/repo/deep/file.py"
        assert response.result["user_id"] == "charlie"


class TestRouteEnvelopeWithDict:
    """Tests for routing envelopes from dictionaries."""

    def test_route_valid_dict(self):
        """Test routing a valid dictionary envelope."""
        clear_recent_events()
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = ""
        from mcp_webhook.config import Settings
        settings = Settings()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="process_payload",
                    args={"path": "path", "user_id": "user"},
                )
            ]
        )

        envelope_dict = {
            "type": "event",
            "event_type": "file.save",
            "payload": {"path": "/file.py", "user": "alice"},
        }

        response = route_envelope_with_dict(envelope_dict, mapping_config)

        assert response.success is True
        assert response.tool == "process_payload"
        assert response.result is not None
        assert response.error is None
        assert response.result["success"] is True
        assert response.result["path"] == "/file.py"
        assert response.result["user_id"] == "alice"

    def test_route_invalid_dict(self):
        """Test routing an invalid dictionary envelope."""
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="ack_event",
                    args={},
                )
            ]
        )

        # Missing required field
        envelope_dict = {
            "type": "event",
            # Missing event_type
            "payload": {"path": "/file.py"},
        }

        response = route_envelope_with_dict(envelope_dict, mapping_config)

        assert response.success is False
        assert response.tool is None
        assert response.result is None
        assert response.error is not None
        assert "Invalid envelope" in response.error

    def test_route_dict_with_auth(self):
        """Test routing dictionary with authentication enabled."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "secret-token"
        settings = Settings()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="process_payload",
                    args={"path": "path", "user_id": "user"},
                )
            ]
        )

        envelope_dict = {
            "type": "event",
            "event_type": "file.save",
            "payload": {"path": "/file.py", "user": "alice"},
            "meta": {"auth": "secret-token"},
        }

        response = route_envelope_with_dict(envelope_dict, mapping_config)

        assert response.success is True
        assert response.tool == "process_payload"
        assert response.result is not None
        assert response.error is None
        assert response.result["success"] is True
        assert response.result["path"] == "/file.py"
        assert response.result["user_id"] == "alice"

    def test_route_dict_with_invalid_token(self):
        """Test routing dictionary with invalid token."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "secret-token"
        settings = Settings()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="ack_event",
                    args={},
                )
            ]
        )

        envelope_dict = {
            "type": "event",
            "event_type": "file.save",
            "payload": {"path": "/file.py"},
            "meta": {"auth": "wrong-token"},
        }

        response = route_envelope_with_dict(envelope_dict, mapping_config)

        assert response.success is False
        assert response.tool is None
        assert response.result is None
        assert response.error is not None
        assert "Authentication failed" in response.error


def _store_test_settings():
    """Helper to ensure clean settings state."""
    reset_settings()
    import os
    # Clear any existing env vars
    if "WEBHOOK_BEARER_TOKENS" in os.environ:
        del os.environ["WEBHOOK_BEARER_TOKENS"]


class TestIntegrationScenarios:
    """Integration tests for complete routing workflows."""

    def test_complete_workflow_with_mapping_file(self):
        """Test complete workflow using actual mapping file."""
        clear_recent_events()
        reset_settings()
        _store_test_settings()

        # Create test mapping
        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="file.save",
                    tool="process_payload",
                    args={"path": "path", "user_id": "user_id"},
                ),
                MappingEntry(
                    event="file.process",
                    tool="process_payload",
                    args={"path": "path", "user_id": "user_id"},
                ),
            ]
        )

        # Test file.save event
        envelope1 = Envelope(
            event_type="file.save",
            payload={"path": "/test/file.py", "user_id": "alice"},
        )
        response1 = route_envelope(envelope1, mapping_config)
        assert response1.success is True
        assert response1.tool == "process_payload"
        assert response1.result["success"] is True
        assert response1.result["path"] == "/test/file.py"
        assert response1.result["user_id"] == "alice"

        # Test file.process event
        envelope2 = Envelope(
            event_type="file.process",
            payload={"path": "/another/file.py", "user_id": "bob"},
        )
        response2 = route_envelope(envelope2, mapping_config)
        assert response2.success is True
        assert response2.tool == "process_payload"
        assert response2.result["path"] == "/another/file.py"
        assert response2.result["user_id"] == "bob"

    def test_auth_required_and_provided(self):
        """Test complete workflow with authentication."""
        clear_recent_events()
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "client-token-1,client-token-2"
        from mcp_webhook.config import Settings
        settings = Settings()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="user.login",
                    tool="ack_event",
                    args={"event_type": "event_type", "payload": "payload"},
                )
            ]
        )

        # Test with first token
        envelope1 = Envelope(
            event_type="user.login",
            payload={"event_type": "user.login", "payload": {"user": "alice"}},
            meta=Meta(auth="client-token-1"),
        )
        response1 = route_envelope(envelope1, mapping_config)
        assert response1.success is True
        assert response1.tool == "ack_event"
        assert response1.result is not None
        assert response1.result["success"] is True
        assert response1.result["event_type"] == "user.login"

        # Test with second token
        envelope2 = Envelope(
            event_type="user.login",
            payload={"event_type": "user.login", "payload": {"user": "bob"}},
            meta=Meta(auth="client-token-2"),
        )
        response2 = route_envelope(envelope2, mapping_config)
        assert response2.success is True
        assert response2.result is not None
        assert response2.result["success"] is True
        assert response2.result["event_type"] == "user.login"
        assert response2.result["event_type"] == "user.login"

    def test_auth_required_and_missing(self):
        """Test complete workflow when auth is required but missing."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "required-token"
        settings = Settings()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="test.event",
                    tool="ack_event",
                    args={},
                )
            ]
        )

        envelope = Envelope(
            event_type="test.event",
            payload={"data": "value"},
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is False
        assert "Authentication required" in response.error

    def test_auth_required_and_invalid(self):
        """Test complete workflow when auth token is invalid."""
        reset_settings()
        import os
        os.environ["WEBHOOK_BEARER_TOKENS"] = "correct-token"
        from mcp_webhook.config import Settings
        settings = Settings()
        reset_settings()

        mapping_config = MappingConfig(
            mappings=[
                MappingEntry(
                    event="test.event",
                    tool="ack_event",
                    args={"event_type": "event_type", "payload": "payload"},
                )
            ]
        )

        envelope = Envelope(
            event_type="test.event",
            payload={"event_type": "test.event", "payload": {"data": "value"}},
            meta=Meta(auth="wrong-token"),
        )

        response = route_envelope(envelope, mapping_config)

        assert response.success is False
        assert "Authentication failed" in response.error
