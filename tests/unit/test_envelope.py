"""Unit tests for envelope models and extraction utilities."""

import pytest

from mcp_webhook.envelope import Envelope, Meta, extract_value, extract_value_with_default


class TestMetaModel:
    """Tests for the Meta Pydantic model."""

    def test_meta_with_all_fields(self):
        """Test creating a Meta object with all fields populated."""
        meta = Meta(
            auth="token123",
            id="550e8400-e29b-41d4-a716-446655440000",
            timestamp="2026-01-06T12:00:00Z"
        )
        assert meta.auth == "token123"
        assert meta.id == "550e8400-e29b-41d4-a716-446655440000"
        assert meta.timestamp == "2026-01-06T12:00:00Z"

    def test_meta_with_partial_fields(self):
        """Test creating a Meta object with only some fields populated."""
        meta = Meta(auth="token123")
        assert meta.auth == "token123"
        assert meta.id is None
        assert meta.timestamp is None

    def test_meta_empty(self):
        """Test creating an empty Meta object."""
        meta = Meta()
        assert meta.auth is None
        assert meta.id is None
        assert meta.timestamp is None


class TestEnvelopeModel:
    """Tests for the Envelope Pydantic model."""

    def test_valid_envelope_minimal(self):
        """Test creating a valid envelope with minimal fields."""
        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/repo/file.py"}
        )
        assert envelope.type == "event"
        assert envelope.event_type == "file.save"
        assert envelope.payload == {"path": "/repo/file.py"}
        assert envelope.meta is None

    def test_valid_envelope_full(self):
        """Test creating a valid envelope with all fields populated."""
        meta = Meta(auth="token1", id="uuid-123", timestamp="2026-01-06T12:00:00Z")
        envelope = Envelope(
            type="event",
            event_type="file.save",
            payload={"path": "/repo/file.py", "user": {"id": "alice"}},
            meta=meta
        )
        assert envelope.type == "event"
        assert envelope.event_type == "file.save"
        assert envelope.payload["path"] == "/repo/file.py"
        assert envelope.meta.auth == "token1"

    def test_envelope_type_normalization(self):
        """Test that the type field is normalized to lowercase."""
        envelope = Envelope(
            type="EVENT",
            event_type="file.save",
            payload={}
        )
        assert envelope.type == "event"

    def test_envelope_invalid_type(self):
        """Test that envelopes with invalid type field are rejected."""
        with pytest.raises(ValueError, match="type must be 'event'"):
            Envelope(
                type="message",
                event_type="file.save",
                payload={}
            )

    def test_envelope_empty_event_type(self):
        """Test that envelopes with empty event_type are rejected."""
        with pytest.raises(ValueError, match="event_type cannot be empty"):
            Envelope(
                event_type="",
                payload={}
            )

    def test_envelope_whitespace_event_type(self):
        """Test that envelopes with whitespace-only event_type are rejected."""
        with pytest.raises(ValueError, match="event_type cannot be empty"):
            Envelope(
                event_type="   ",
                payload={}
            )

    def test_envelope_event_type_stripped(self):
        """Test that event_type is stripped of leading/trailing whitespace."""
        envelope = Envelope(
            event_type="  file.save  ",
            payload={}
        )
        assert envelope.event_type == "file.save"

    def test_envelope_missing_required_fields(self):
        """Test that envelopes without required fields are rejected."""
        with pytest.raises(ValueError):
            Envelope(event_type="file.save")  # Missing payload

        with pytest.raises(ValueError):
            Envelope(payload={})  # Missing event_type

    def test_envelope_from_dict(self):
        """Test creating envelope from dictionary (as from JSON)."""
        data = {
            "type": "event",
            "event_type": "file.save",
            "payload": {"path": "/repo/file.py"},
            "meta": {"auth": "token1"}
        }
        envelope = Envelope(**data)
        assert envelope.event_type == "file.save"
        assert envelope.payload["path"] == "/repo/file.py"
        assert envelope.meta.auth == "token1"


class TestExtractValue:
    """Tests for the extract_value utility function."""

    def test_extract_simple_value(self):
        """Test extracting a simple top-level value."""
        payload = {"user_id": "alice"}
        result = extract_value(payload, "user_id")
        assert result == "alice"

    def test_extract_nested_value(self):
        """Test extracting a nested value using dot notation."""
        payload = {"user": {"id": "alice", "name": "Alice"}}
        result = extract_value(payload, "user.id")
        assert result == "alice"

    def test_extract_deeply_nested_value(self):
        """Test extracting a deeply nested value."""
        payload = {
            "data": {
                "level1": {
                    "level2": {
                        "level3": "deep_value"
                    }
                }
            }
        }
        result = extract_value(payload, "data.level1.level2.level3")
        assert result == "deep_value"

    def test_extract_list_value(self):
        """Test extracting a list from payload."""
        payload = {"items": [1, 2, 3]}
        result = extract_value(payload, "items")
        assert result == [1, 2, 3]

    def test_extract_none_value(self):
        """Test extracting None value."""
        payload = {"value": None}
        result = extract_value(payload, "value")
        assert result is None

    def test_extract_zero_value(self):
        """Test extracting zero value."""
        payload = {"value": 0}
        result = extract_value(payload, "value")
        assert result == 0

    def test_extract_false_value(self):
        """Test extracting False value."""
        payload = {"value": False}
        result = extract_value(payload, "value")
        assert result is False

    def test_extract_empty_string(self):
        """Test extracting empty string."""
        payload = {"value": ""}
        result = extract_value(payload, "value")
        assert result == ""

    def test_extract_from_complex_structure(self):
        """Test extracting from a complex nested structure."""
        payload = {
            "event": {
                "type": "file.save",
                "data": {
                    "path": "/repo/file.py",
                    "meta": {
                        "size": 1024,
                        "modified": "2026-01-06T12:00:00Z"
                    }
                }
            }
        }
        result = extract_value(payload, "event.data.meta.size")
        assert result == 1024

    def test_extract_empty_path_raises_error(self):
        """Test that empty dot_path raises ValueError."""
        payload = {"key": "value"}
        with pytest.raises(ValueError, match="Dot path cannot be empty"):
            extract_value(payload, "")

    def test_extract_invalid_empty_key_raises_error(self):
        """Test that dot_path with empty keys raises ValueError."""
        payload = {"key": {"nested": "value"}}
        with pytest.raises(ValueError, match="Invalid dot path: empty key"):
            extract_value(payload, "key..nested")

    def test_extract_missing_key_raises_keyerror(self):
        """Test that missing keys raise KeyError."""
        payload = {"user": {"id": "alice"}}
        with pytest.raises(KeyError, match="Key 'email' not found"):
            extract_value(payload, "user.email")

    def test_extract_missing_first_key_raises_keyerror(self):
        """Test that missing first key raises KeyError."""
        payload = {"user": {"id": "alice"}}
        with pytest.raises(KeyError, match="Key 'missing' not found"):
            extract_value(payload, "missing.key")

    def test_extract_non_dict_intermediate_raises_typeerror(self):
        """Test that trying to access a key on a non-dict value raises TypeError."""
        payload = {"user": "alice"}
        with pytest.raises(TypeError, match="parent value is not a dict"):
            extract_value(payload, "user.id")

    def test_extract_number_intermediate_raises_typeerror(self):
        """Test that trying to access a key on a number raises TypeError."""
        payload = {"value": 42}
        with pytest.raises(TypeError, match="parent value is not a dict"):
            extract_value(payload, "value.something")

    def test_extract_non_dict_payload_raises_typeerror(self):
        """Test that non-dict payload raises TypeError."""
        with pytest.raises(TypeError, match="Payload must be a dict"):
            extract_value("not a dict", "key")


class TestExtractValueWithDefault:
    """Tests for the extract_value_with_default utility function."""

    def test_extract_with_default_success(self):
        """Test successful extraction returns the value, not default."""
        payload = {"user": {"id": "alice"}}
        result = extract_value_with_default(payload, "user.id", "default")
        assert result == "alice"

    def test_extract_with_default_missing_key(self):
        """Test that missing keys return the default value."""
        payload = {"user": {"id": "alice"}}
        result = extract_value_with_default(payload, "user.email", "unknown@example.com")
        assert result == "unknown@example.com"

    def test_extract_with_default_invalid_path(self):
        """Test that invalid paths return the default value."""
        payload = {"user": {"id": "alice"}}
        result = extract_value_with_default(payload, "missing.key", "default")
        assert result == "default"

    def test_extract_with_default_non_dict_intermediate(self):
        """Test that non-dict intermediate values return default."""
        payload = {"user": "alice"}
        result = extract_value_with_default(payload, "user.id", "default")
        assert result == "default"

    def test_extract_with_default_none_default(self):
        """Test that None can be used as default."""
        payload = {"user": {"id": "alice"}}
        result = extract_value_with_default(payload, "user.email", None)
        assert result is None

    def test_extract_with_default_empty_string_default(self):
        """Test that empty string can be used as default."""
        payload = {"user": {"id": "alice"}}
        result = extract_value_with_default(payload, "user.email", "")
        assert result == ""

    def test_extract_with_default_list_default(self):
        """Test that a list can be used as default."""
        payload = {"user": {"id": "alice"}}
        result = extract_value_with_default(payload, "user.email", [])
        assert result == []

    def test_extract_with_default_dict_default(self):
        """Test that a dict can be used as default."""
        payload = {"user": {"id": "alice"}}
        result = extract_value_with_default(payload, "user.email", {})
        assert result == {}

    def test_extract_actual_none_value_vs_default(self):
        """Test that actual None values are returned, not the default."""
        payload = {"value": None}
        result = extract_value_with_default(payload, "value", "default")
        assert result is None

    def test_extract_with_default_empty_path(self):
        """Test that empty path returns default."""
        payload = {"key": "value"}
        result = extract_value_with_default(payload, "", "default")
        assert result == "default"

    def test_extract_with_default_no_default_specified(self):
        """Test extraction when no default is specified (returns None on failure)."""
        payload = {"user": {"id": "alice"}}
        result = extract_value_with_default(payload, "user.email")
        assert result is None


class TestIntegration:
    """Integration tests combining envelope and extraction."""

    def test_extract_from_envelope_payload(self):
        """Test extracting values from an envelope's payload."""
        meta = Meta(auth="token1")
        envelope = Envelope(
            event_type="file.save",
            payload={
                "path": "/repo/file.py",
                "user": {"id": "alice", "name": "Alice"}
            },
            meta=meta
        )

        # Extract user ID from payload
        user_id = extract_value(envelope.payload, "user.id")
        assert user_id == "alice"

        # Extract path from payload
        path = extract_value(envelope.payload, "path")
        assert path == "/repo/file.py"

    def test_extract_with_default_from_envelope_payload(self):
        """Test extracting values with default from an envelope's payload."""
        envelope = Envelope(
            event_type="file.save",
            payload={"path": "/repo/file.py", "user": {"id": "alice"}}
        )

        # Existing value
        user_id = extract_value_with_default(envelope.payload, "user.id", "unknown")
        assert user_id == "alice"

        # Missing value
        email = extract_value_with_default(envelope.payload, "user.email", "unknown@example.com")
        assert email == "unknown@example.com"

    def test_nested_extraction_with_default_chain(self):
        """Test chained extraction with defaults."""
        payload = {
            "data": {
                "user": {"id": "alice"},
                "files": [
                    {"path": "/file1.py", "size": 1024},
                    {"path": "/file2.py", "size": 2048}
                ]
            }
        }

        # Extract existing value
        user_id = extract_value_with_default(payload, "data.user.id", "unknown")
        assert user_id == "alice"

        # Extract from list (returns the list)
        files = extract_value_with_default(payload, "data.files", [])
        assert len(files) == 2

        # Extract missing nested value
        missing = extract_value_with_default(payload, "data.missing.nested", "fallback")
        assert missing == "fallback"
