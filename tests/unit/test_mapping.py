"""Unit tests for mapping configuration module."""

import os
import tempfile
import pytest
from pathlib import Path
from mcp_webhook.mapping import (
    MappingEntry,
    MappingConfig,
    extract_value,
    extract_value_safe,
    load_mapping_config,
    find_mapping_for_event,
    resolve_args,
)


class TestMappingEntryModel:
    """Test MappingEntry Pydantic model validation."""

    def test_valid_mapping_entry(self):
        """Test creating a valid mapping entry."""
        entry = MappingEntry(
            event="file.save",
            tool="process_payload",
            args={"path": "payload.path", "user_id": "payload.user.id"}
        )
        assert entry.event == "file.save"
        assert entry.tool == "process_payload"
        assert entry.args == {"path": "payload.path", "user_id": "payload.user.id"}

    def test_mapping_entry_with_empty_args(self):
        """Test mapping entry with no arguments."""
        entry = MappingEntry(event="file.save", tool="ack_event")
        assert entry.args == {}

    def test_mapping_event_trims_whitespace(self):
        """Test event name is trimmed of whitespace."""
        entry = MappingEntry(event="  file.save  ", tool="process_payload")
        assert entry.event == "file.save"

    def test_mapping_tool_trims_whitespace(self):
        """Test tool name is trimmed of whitespace."""
        entry = MappingEntry(event="file.save", tool="  process_payload  ")
        assert entry.tool == "process_payload"

    def test_empty_event_raises_error(self):
        """Test empty event string raises validation error."""
        with pytest.raises(ValueError, match="Event and tool names cannot be empty"):
            MappingEntry(event="", tool="process_payload")

    def test_whitespace_only_event_raises_error(self):
        """Test whitespace-only event raises validation error."""
        with pytest.raises(ValueError, match="Event and tool names cannot be empty"):
            MappingEntry(event="   ", tool="process_payload")

    def test_empty_tool_raises_error(self):
        """Test empty tool string raises validation error."""
        with pytest.raises(ValueError, match="Event and tool names cannot be empty"):
            MappingEntry(event="file.save", tool="")


class TestMappingConfigModel:
    """Test MappingConfig Pydantic model."""

    def test_empty_mapping_config(self):
        """Test config with no mappings."""
        config = MappingConfig()
        assert config.mappings == []

    def test_mapping_config_with_entries(self):
        """Test config with multiple mapping entries."""
        entries = [
            MappingEntry(event="file.save", tool="process_payload"),
            MappingEntry(event="file.open", tool="ack_event"),
        ]
        config = MappingConfig(mappings=entries)
        assert len(config.mappings) == 2
        assert config.mappings[0].event == "file.save"
        assert config.mappings[1].event == "file.open"


class TestExtractValue:
    """Test extract_value function for dot-path extraction."""

    def test_extract_single_level_key(self):
        """Test extracting a top-level key."""
        data = {"name": "alice"}
        result = extract_value(data, "name")
        assert result == "alice"

    def test_extract_two_level_path(self):
        """Test extracting nested value two levels deep."""
        data = {"user": {"id": "123"}}
        result = extract_value(data, "user.id")
        assert result == "123"

    def test_extract_deep_nesting(self):
        """Test extracting deeply nested value."""
        data = {"a": {"b": {"c": {"d": "value"}}}}
        result = extract_value(data, "a.b.c.d")
        assert result == "value"

    def test_extract_with_number_values(self):
        """Test extracting numeric values."""
        data = {"payload": {"count": 42, "price": 19.99}}
        assert extract_value(data, "payload.count") == 42
        assert extract_value(data, "payload.price") == 19.99

    def test_extract_with_boolean_values(self):
        """Test extracting boolean values."""
        data = {"payload": {"active": True, "deleted": False}}
        assert extract_value(data, "payload.active") is True
        assert extract_value(data, "payload.deleted") is False

    def test_extract_with_list_values(self):
        """Test extracting list values."""
        data = {"payload": {"tags": ["python", "mcp", "webhook"]}}
        result = extract_value(data, "payload.tags")
        assert result == ["python", "mcp", "webhook"]

    def test_extract_with_dict_values(self):
        """Test extracting dict values."""
        data = {"payload": {"meta": {"id": "123", "timestamp": "2024-01-01"}}}
        result = extract_value(data, "payload.meta")
        assert result == {"id": "123", "timestamp": "2024-01-01"}

    def test_extract_with_null_value(self):
        """Test extracting None/null value."""
        data = {"payload": {"value": None}}
        result = extract_value(data, "payload.value")
        assert result is None

    def test_missing_key_raises_error(self):
        """Test that missing key raises KeyError."""
        data = {"user": {"id": "123"}}
        with pytest.raises(KeyError, match="Key 'name' not found"):
            extract_value(data, "user.name")

    def test_missing_intermediate_key_raises_error(self):
        """Test that missing intermediate key raises KeyError."""
        data = {"user": {"id": "123"}}
        with pytest.raises(KeyError, match="Key 'profile' not found"):
            extract_value(data, "user.profile.name")

    def test_non_dict_parent_raises_error(self):
        """Test accessing key on non-dict parent raises TypeError."""
        data = {"user": "alice"}
        with pytest.raises(TypeError, match="Cannot access key 'name' at path 'user'"):
            extract_value(data, "user.name")

    def test_empty_dot_path_raises_error(self):
        """Test empty dot path raises KeyError."""
        data = {"user": {"id": "123"}}
        with pytest.raises(KeyError, match="Dot path cannot be empty"):
            extract_value(data, "")

    def test_dot_path_with_leading_dot(self):
        """Test dot path with leading dot is handled."""
        data = {"user": {"id": "123"}}
        with pytest.raises(KeyError, match="Key '' not found"):
            extract_value(data, ".user.id")


class TestExtractValueSafe:
    """Test extract_value_safe function with default values."""

    def test_extract_value_safe_success(self):
        """Test successful extraction returns value."""
        data = {"user": {"id": "123"}}
        result = extract_value_safe(data, "user.id", "default")
        assert result == "123"

    def test_extract_value_safe_missing_key_returns_default(self):
        """Test missing key returns default value."""
        data = {"user": {"id": "123"}}
        result = extract_value_safe(data, "user.name", "unknown")
        assert result == "unknown"

    def test_extract_value_safe_type_error_returns_default(self):
        """Test type error returns default value."""
        data = {"user": "alice"}
        result = extract_value_safe(data, "user.name", "default")
        assert result == "default"

    def test_extract_value_safe_default_none(self):
        """Test default None when extraction fails."""
        data = {"user": {"id": "123"}}
        result = extract_value_safe(data, "missing.path")
        assert result is None

    def test_extract_value_safe_with_empty_string(self):
        """Test extracting empty string value."""
        data = {"payload": {"value": ""}}
        result = extract_value_safe(data, "payload.value", "default")
        assert result == ""


class TestLoadMappingConfig:
    """Test loading mapping configuration from files."""

    def test_load_valid_yaml_config(self, tmp_path):
        """Test loading valid YAML mapping file."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
mappings:
  - event: "file.save"
    tool: "process_payload"
    args:
      path: payload.path
      user_id: payload.user.id
  - event: "file.open"
    tool: "ack_event"
    args:
      file: payload.path
""")
        config = load_mapping_config(str(config_file))
        assert len(config.mappings) == 2
        assert config.mappings[0].event == "file.save"
        assert config.mappings[1].event == "file.open"

    def test_load_empty_mappings_list(self, tmp_path):
        """Test loading config with empty mappings list."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
mappings: []
""")
        config = load_mapping_config(str(config_file))
        assert len(config.mappings) == 0

    def test_load_config_without_mappings_key(self, tmp_path):
        """Test loading config without mappings key creates empty list."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
other_key: value
""")
        config = load_mapping_config(str(config_file))
        assert len(config.mappings) == 0

    def test_load_empty_file(self, tmp_path):
        """Test loading empty YAML file."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("")
        config = load_mapping_config(str(config_file))
        assert len(config.mappings) == 0

    def test_load_json_format(self, tmp_path):
        """Test loading JSON format configuration."""
        config_file = tmp_path / "mapping.json"
        config_file.write_text("""
{
  "mappings": [
    {
      "event": "file.save",
      "tool": "process_payload",
      "args": {"path": "payload.path"}
    }
  ]
}
""")
        config = load_mapping_config(str(config_file))
        assert len(config.mappings) == 1
        assert config.mappings[0].event == "file.save"

    def test_load_nonexistent_file_raises_error(self):
        """Test loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Mapping file not found"):
            load_mapping_config("/nonexistent/path/mapping.yml")

    def test_load_invalid_yaml_raises_error(self, tmp_path):
        """Test loading invalid YAML raises YAMLError."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
mappings:
  - event: "file.save"
    tool: "process_payload"
  invalid yaml indentation
""")
        with pytest.raises(Exception, match="Failed to parse"):
            load_mapping_config(str(config_file))

    def test_load_invalid_structure_raises_error(self, tmp_path):
        """Test loading config with invalid structure raises ValueError."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
- event: "file.save"
  tool: "process_payload"
""")
        with pytest.raises(ValueError, match="must contain a YAML object"):
            load_mapping_config(str(config_file))

    def test_load_invalid_mapping_entry_raises_error(self, tmp_path):
        """Test loading config with invalid mapping entry raises ValueError."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
mappings:
  - event: ""
    tool: "process_payload"
""")
        with pytest.raises(ValueError, match="Invalid mapping configuration"):
            load_mapping_config(str(config_file))

    def test_load_complex_mapping(self, tmp_path):
        """Test loading complex mapping with multiple arguments."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
mappings:
  - event: "git.push"
    tool: "process_payload"
    args:
      repo: payload.repository.name
      branch: payload.ref
      committer: payload.pusher.name
      commit_count: payload.commits.length
""")
        config = load_mapping_config(str(config_file))
        mapping = config.mappings[0]
        assert mapping.event == "git.push"
        assert len(mapping.args) == 4
        assert mapping.args["repo"] == "payload.repository.name"


class TestFindMappingForEvent:
    """Test finding mapping entries by event type."""

    def test_find_existing_mapping(self):
        """Test finding a mapping that exists."""
        config = MappingConfig(mappings=[
            MappingEntry(event="file.save", tool="process_payload"),
            MappingEntry(event="file.open", tool="ack_event"),
        ])
        result = find_mapping_for_event(config, "file.save")
        assert result is not None
        assert result.event == "file.save"
        assert result.tool == "process_payload"

    def test_find_nonexistent_mapping(self):
        """Test finding a mapping that doesn't exist."""
        config = MappingConfig(mappings=[
            MappingEntry(event="file.save", tool="process_payload"),
        ])
        result = find_mapping_for_event(config, "file.delete")
        assert result is None

    def test_find_in_empty_config(self):
        """Test finding mapping in empty config."""
        config = MappingConfig()
        result = find_mapping_for_event(config, "file.save")
        assert result is None

    def test_find_with_duplicate_events(self):
        """Test finding when multiple mappings have same event (returns first)."""
        config = MappingConfig(mappings=[
            MappingEntry(event="file.save", tool="process_payload"),
            MappingEntry(event="file.save", tool="alternate_tool"),
        ])
        result = find_mapping_for_event(config, "file.save")
        assert result.tool == "process_payload"

    def test_case_sensitive_event_matching(self):
        """Test event matching is case-sensitive."""
        config = MappingConfig(mappings=[
            MappingEntry(event="File.Save", tool="process_payload"),
        ])
        assert find_mapping_for_event(config, "File.Save") is not None
        assert find_mapping_for_event(config, "file.save") is None
        assert find_mapping_for_event(config, "FILE.SAVE") is None


class TestResolveArgs:
    """Test resolving arguments from envelopes using mapping templates."""

    def test_resolve_single_argument(self):
        """Test resolving a single argument."""
        mapping = MappingEntry(
            event="file.save",
            tool="process_payload",
            args={"path": "payload.path"}
        )
        envelope = {"payload": {"path": "/file.py"}}
        result = resolve_args(mapping, envelope)
        assert result == {"path": "/file.py"}

    def test_resolve_multiple_arguments(self):
        """Test resolving multiple arguments."""
        mapping = MappingEntry(
            event="file.save",
            tool="process_payload",
            args={
                "path": "payload.path",
                "user_id": "payload.user.id",
                "timestamp": "meta.timestamp"
            }
        )
        envelope = {
            "payload": {"path": "/file.py", "user": {"id": "alice"}},
            "meta": {"timestamp": "2024-01-01T00:00:00Z"}
        }
        result = resolve_args(mapping, envelope)
        assert result == {
            "path": "/file.py",
            "user_id": "alice",
            "timestamp": "2024-01-01T00:00:00Z"
        }

    def test_resolve_with_nested_values(self):
        """Test resolving deeply nested argument values."""
        mapping = MappingEntry(
            event="complex.event",
            tool="process",
            args={"value": "a.b.c.d"}
        )
        envelope = {"a": {"b": {"c": {"d": "result"}}}}
        result = resolve_args(mapping, envelope)
        assert result == {"value": "result"}

    def test_resolve_with_different_value_types(self):
        """Test resolving arguments with different data types."""
        mapping = MappingEntry(
            event="mixed.types",
            tool="process",
            args={
                "string": "payload.str",
                "number": "payload.num",
                "boolean": "payload.bool",
                "list": "payload.items",
                "null": "payload.nothing"
            }
        )
        envelope = {
            "payload": {
                "str": "text",
                "num": 42,
                "bool": True,
                "items": [1, 2, 3],
                "nothing": None
            }
        }
        result = resolve_args(mapping, envelope)
        assert result == {
            "string": "text",
            "number": 42,
            "boolean": True,
            "list": [1, 2, 3],
            "null": None
        }

    def test_resolve_empty_args_returns_empty_dict(self):
        """Test resolving when mapping has no arguments."""
        mapping = MappingEntry(
            event="no.args",
            tool="process",
            args={}
        )
        envelope = {"payload": {"data": "value"}}
        result = resolve_args(mapping, envelope)
        assert result == {}

    def test_resolve_missing_key_raises_error(self):
        """Test that missing required argument raises KeyError."""
        mapping = MappingEntry(
            event="missing.key",
            tool="process",
            args={"user_id": "payload.user.id"}
        )
        envelope = {"payload": {"path": "/file.py"}}
        with pytest.raises(KeyError, match="Failed to resolve argument.*user_id"):
            resolve_args(mapping, envelope)

    def test_resolve_invalid_path_raises_error(self):
        """Test that invalid path raises TypeError."""
        mapping = MappingEntry(
            event="invalid.path",
            tool="process",
            args={"name": "payload.user.name"}
        )
        envelope = {"payload": {"user": "not_a_dict"}}
        with pytest.raises(TypeError, match="Failed to resolve argument 'name'"):
            resolve_args(mapping, envelope)

    def test_resolve_empty_dot_path_raises_error(self):
        """Test empty dot path in mapping raises ValueError."""
        mapping = MappingEntry(
            event="empty.path",
            tool="process",
            args={"arg1": ""}
        )
        envelope = {"payload": {"data": "value"}}
        with pytest.raises(ValueError, match="has an empty dot path"):
            resolve_args(mapping, envelope)

    def test_resolve_full_envelope_scenario(self):
        """Test full envelope scenario matching planning example."""
        mapping = MappingEntry(
            event="file.save",
            tool="process_payload",
            args={
                "path": "payload.path",
                "user_id": "payload.user.id",
                "event_type": "event_type",
                "meta_id": "meta.id"
            }
        )
        envelope = {
            "type": "event",
            "event_type": "file.save",
            "payload": {
                "path": "/repo/file.py",
                "user": {"id": "alice"}
            },
            "meta": {
                "id": "uuid-123",
                "timestamp": "2026-01-06T12:00:00Z"
            }
        }
        result = resolve_args(mapping, envelope)
        assert result == {
            "path": "/repo/file.py",
            "user_id": "alice",
            "event_type": "file.save",
            "meta_id": "uuid-123"
        }


class TestIntegrationScenarios:
    """Integration tests combining multiple mapping functions."""

    def test_full_mapping_workflow(self, tmp_path):
        """Test complete workflow: load -> find -> resolve."""
        # Setup: Create mapping file
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
mappings:
  - event: "file.save"
    tool: "process_payload"
    args:
      path: payload.path
      user_id: payload.user.id
""")

        # Step 1: Load config
        config = load_mapping_config(str(config_file))
        assert len(config.mappings) == 1

        # Step 2: Find mapping
        mapping = find_mapping_for_event(config, "file.save")
        assert mapping is not None
        assert mapping.tool == "process_payload"

        # Step 3: Resolve arguments
        envelope = {
            "type": "event",
            "event_type": "file.save",
            "payload": {"path": "/test.py", "user": {"id": "bob"}},
            "meta": {"id": "xyz"}
        }
        args = resolve_args(mapping, envelope)
        assert args == {"path": "/test.py", "user_id": "bob"}

    def test_multiple_events_workflow(self, tmp_path):
        """Test workflow with multiple event types."""
        config_file = tmp_path / "mapping.yml"
        config_file.write_text("""
mappings:
  - event: "file.save"
    tool: "process_payload"
    args:
      path: payload.path
  - event: "file.open"
    tool: "ack_event"
    args:
      file: payload.path
  - event: "git.push"
    tool: "process_payload"
    args:
      repo: payload.repo
""")

        config = load_mapping_config(str(config_file))

        # Test first event
        mapping1 = find_mapping_for_event(config, "file.save")
        assert mapping1.tool == "process_payload"

        # Test second event
        mapping2 = find_mapping_for_event(config, "file.open")
        assert mapping2.tool == "ack_event"

        # Test third event
        mapping3 = find_mapping_for_event(config, "git.push")
        assert mapping3.tool == "process_payload"

        # Test unknown event
        mapping4 = find_mapping_for_event(config, "unknown.event")
        assert mapping4 is None

    def test_dot_path_extraction_examples_from_planning(self):
        """Test dot-path extraction examples from Planning.md."""
        # Example from planning: payload.user.id
        data = {
            "payload": {
                "path": "/repo/file.py",
                "user": {"id": "alice"}
            }
        }

        assert extract_value(data, "payload.path") == "/repo/file.py"
        assert extract_value(data, "payload.user.id") == "alice"

        # Test safe extraction with defaults
        assert extract_value_safe(data, "payload.missing", "default") == "default"
        assert extract_value_safe(data, "payload.user.name", "unknown") == "unknown"
