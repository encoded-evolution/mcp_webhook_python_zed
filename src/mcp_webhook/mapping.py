"""Mapping configuration parser for event-to-tool resolution.

This module provides functionality to:
- Load mapping configurations from YAML/JSON files
- Extract values from nested dictionaries using dot-path syntax
- Resolve event types to MCP tools and their arguments
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from mcp_webhook.config import get_settings


class MappingEntry(BaseModel):
    """Represents a single event-to-tool mapping.

    Attributes:
        event: The event type to match (e.g., "file.save")
        tool: The name of the MCP tool to invoke
        args: Dictionary mapping argument names to dot-path templates
    """

    event: str = Field(..., description="Event type to match")
    tool: str = Field(..., description="MCP tool name to invoke")
    args: Dict[str, str] = Field(
        default_factory=dict,
        description="Argument names mapped to dot-path templates"
    )

    @field_validator("event", "tool")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Validate that event and tool names are not empty strings."""
        if not v or not v.strip():
            raise ValueError("Event and tool names cannot be empty")
        return v.strip()


class MappingConfig(BaseModel):
    """Container for all mapping entries.

    Attributes:
        mappings: List of mapping entries
    """

    mappings: List[MappingEntry] = Field(
        default_factory=list,
        description="List of event-to-tool mappings"
    )


def extract_value(data: Dict[str, Any], dot_path: str) -> Any:
    """Extract a value from a nested dictionary using dot-path syntax.

    Args:
        data: The dictionary to extract from
        dot_path: Dot-separated path (e.g., "payload.user.id")

    Returns:
        The value at the specified path

    Raises:
        KeyError: If the path cannot be resolved
        TypeError: If intermediate value is not a dict

    Examples:
        >>> data = {"payload": {"user": {"id": "alice"}}}
        >>> extract_value(data, "payload.user.id")
        'alice'
        >>> extract_value(data, "payload.path")
        KeyError: 'path'
    """
    if not dot_path:
        raise KeyError("Dot path cannot be empty")

    keys = dot_path.split(".")
    current = data

    for i, key in enumerate(keys):
        if not isinstance(current, dict):
            raise TypeError(
                f"Cannot access key '{key}' at path '{'.'.join(keys[:i])}' "
                f"because parent value is not a dict (got {type(current).__name__})"
            )

        if key not in current:
            raise KeyError(
                f"Key '{key}' not found at path '{'.'.join(keys[:i])}' "
                f"in dot path '{dot_path}'"
            )

        current = current[key]

    return current


def extract_value_safe(data: Dict[str, Any], dot_path: str, default: Any = None) -> Any:
    """Extract a value from a nested dictionary with a default on failure.

    Args:
        data: The dictionary to extract from
        dot_path: Dot-separated path (e.g., "payload.user.id")
        default: Value to return if extraction fails

    Returns:
        The value at the specified path, or default if extraction fails

    Examples:
        >>> data = {"payload": {"user": {"id": "alice"}}}
        >>> extract_value_safe(data, "payload.user.id", "unknown")
        'alice'
        >>> extract_value_safe(data, "payload.missing", "unknown")
        'unknown'
    """
    try:
        return extract_value(data, dot_path)
    except (KeyError, TypeError):
        return default


def load_mapping_config(file_path: Optional[str] = None) -> MappingConfig:
    """Load mapping configuration from a YAML or JSON file.

    Args:
        file_path: Path to the mapping file. If None, uses the path from settings.

    Returns:
        MappingConfig object with loaded mappings

    Raises:
        FileNotFoundError: If the mapping file doesn't exist
        yaml.YAMLError: If the YAML/JSON is invalid
        ValueError: If the mapping structure is invalid

    Examples:
        >>> config = load_mapping_config("config/mapping.yml")
        >>> config.mappings[0].event
        'file.save'
    """
    settings = get_settings()

    if file_path is None:
        file_path = settings.mapping_file

    path = Path(file_path)

    # Check if file exists
    if not path.exists():
        raise FileNotFoundError(
            f"Mapping file not found at '{file_path}'. "
            f"Current directory: {os.getcwd()}"
        )

    # Load the file content
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Failed to parse mapping file '{file_path}': {e}") from e
    except Exception as e:
        raise IOError(f"Failed to read mapping file '{file_path}': {e}") from e

    # Validate structure
    if content is None:
        content = {}

    if not isinstance(content, dict):
        raise ValueError(
            f"Mapping file '{file_path}' must contain a YAML object/dict at root level"
        )

    if "mappings" not in content:
        content["mappings"] = []

    # Validate and parse mappings
    try:
        config = MappingConfig(**content)
    except Exception as e:
        raise ValueError(f"Invalid mapping configuration in '{file_path}': {e}") from e

    return config


def find_mapping_for_event(config: MappingConfig, event_type: str) -> Optional[MappingEntry]:
    """Find the mapping entry for a given event type.

    Args:
        config: The mapping configuration to search
        event_type: The event type to find (e.g., "file.save")

    Returns:
        The matching MappingEntry, or None if no match found

    Examples:
        >>> config = load_mapping_config("config/mapping.yml")
        >>> mapping = find_mapping_for_event(config, "file.save")
        >>> mapping.tool
        'process_payload'
    """
    for entry in config.mappings:
        if entry.event == event_type:
            return entry
    return None


def resolve_args(mapping: MappingEntry, envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve argument values from an envelope using mapping templates.

    Args:
        mapping: The mapping entry with argument templates
        envelope: The envelope data containing the payload

    Returns:
        Dictionary with resolved argument values

    Raises:
        KeyError: If required arguments cannot be resolved
        ValueError: If the envelope structure is invalid

    Examples:
        >>> mapping = MappingEntry(
        ...     event="file.save",
        ...     tool="process_payload",
        ...     args={"path": "payload.path", "user_id": "payload.user.id"}
        ... )
        >>> envelope = {"payload": {"path": "/file.py", "user": {"id": "alice"}}}
        >>> resolve_args(mapping, envelope)
        {'path': '/file.py', 'user_id': 'alice'}
    """
    resolved = {}

    for arg_name, dot_path in mapping.args.items():
        if not dot_path:
            raise ValueError(
                f"Argument '{arg_name}' in mapping for event '{mapping.event}' "
                f"has an empty dot path"
            )

        try:
            value = extract_value(envelope, dot_path)
            resolved[arg_name] = value
        except KeyError as e:
            raise KeyError(
                f"Failed to resolve argument '{arg_name}' for event '{mapping.event}': {e}"
            ) from e
        except TypeError as e:
            raise TypeError(
                f"Failed to resolve argument '{arg_name}' for event '{mapping.event}': {e}"
            ) from e

    return resolved
