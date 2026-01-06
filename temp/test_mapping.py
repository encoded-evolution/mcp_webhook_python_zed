"""Verification script for mapping module functionality."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_webhook.mapping import (
    load_mapping_config,
    find_mapping_for_event,
    resolve_args,
    extract_value,
    extract_value_safe,
)


def test_example_mapping_file():
    """Test loading and using the example mapping file."""
    print("=" * 70)
    print("Test 1: Loading example mapping configuration")
    print("=" * 70)

    example_file = Path(__file__).parent.parent / "config" / "mapping.yml.example"

    if not example_file.exists():
        print(f"❌ Example file not found: {example_file}")
        return False

    try:
        config = load_mapping_config(str(example_file))
        print(f"✅ Loaded {len(config.mappings)} mappings from example file")

        # List all mappings
        print("\nConfigured mappings:")
        for i, mapping in enumerate(config.mappings, 1):
            print(f"  {i}. {mapping.event} -> {mapping.tool}")
            for arg_name, dot_path in mapping.args.items():
                print(f"       {arg_name}: {dot_path}")

        return True
    except Exception as e:
        print(f"❌ Failed to load example file: {e}")
        return False


def test_dot_path_extraction():
    """Test dot-path extraction functionality."""
    print("\n" + "=" * 70)
    print("Test 2: Dot-path extraction")
    print("=" * 70)

    # Test data from planning example
    data = {
        "payload": {
            "path": "/repo/file.py",
            "user": {
                "id": "alice"
            }
        },
        "meta": {
            "id": "uuid-123",
            "timestamp": "2026-01-06T12:00:00Z"
        }
    }

    tests = [
        ("payload.path", "/repo/file.py"),
        ("payload.user.id", "alice"),
        ("meta.id", "uuid-123"),
        ("meta.timestamp", "2026-01-06T12:00:00Z"),
    ]

    all_passed = True
    for dot_path, expected in tests:
        try:
            result = extract_value(data, dot_path)
            if result == expected:
                print(f"✅ extract_value(data, '{dot_path}') = '{result}'")
            else:
                print(f"❌ extract_value(data, '{dot_path}') = '{result}' (expected '{expected}')")
                all_passed = False
        except Exception as e:
            print(f"❌ extract_value(data, '{dot_path}') failed: {e}")
            all_passed = False

    # Test safe extraction
    result = extract_value_safe(data, "payload.missing", "default")
    if result == "default":
        print(f"✅ extract_value_safe with missing key returns default: '{result}'")
    else:
        print(f"❌ extract_value_safe failed: expected 'default', got '{result}'")
        all_passed = False

    return all_passed


def test_event_resolution():
    """Test event-to-tool resolution."""
    print("\n" + "=" * 70)
    print("Test 3: Event resolution and argument extraction")
    print("=" * 70)

    example_file = Path(__file__).parent.parent / "config" / "mapping.yml.example"
    config = load_mapping_config(str(example_file))

    # Test case: file.save event
    envelope = {
        "type": "event",
        "event_type": "file.save",
        "payload": {
            "path": "/repo/file.py",
            "user": {
                "id": "alice"
            }
        },
        "meta": {
            "id": "uuid-123",
            "timestamp": "2026-01-06T12:00:00Z"
        }
    }

    mapping = find_mapping_for_event(config, "file.save")
    if mapping:
        print(f"✅ Found mapping for 'file.save' -> '{mapping.tool}'")

        try:
            args = resolve_args(mapping, envelope)
            print(f"✅ Resolved arguments: {args}")

            # Verify expected arguments
            expected = {
                "path": "/repo/file.py",
                "user_id": "alice",
                "timestamp": "2026-01-06T12:00:00Z"
            }

            if args == expected:
                print(f"✅ Arguments match expected values")
                return True
            else:
                print(f"❌ Arguments don't match expected")
                print(f"   Expected: {expected}")
                print(f"   Got:      {args}")
                return False
        except Exception as e:
            print(f"❌ Failed to resolve arguments: {e}")
            return False
    else:
        print(f"❌ No mapping found for 'file.save'")
        return False


def test_error_handling():
    """Test error handling for invalid operations."""
    print("\n" + "=" * 70)
    print("Test 4: Error handling")
    print("=" * 70)

    all_passed = True

    # Test missing key
    data = {"user": {"id": "123"}}
    try:
        extract_value(data, "user.name")
        print(f"❌ Missing key should raise KeyError")
        all_passed = False
    except KeyError:
        print(f"✅ Missing key raises KeyError as expected")

    # Test non-dict parent
    data2 = {"user": "alice"}
    try:
        extract_value(data2, "user.name")
        print(f"❌ Non-dict parent should raise TypeError")
        all_passed = False
    except TypeError:
        print(f"✅ Non-dict parent raises TypeError as expected")

    # Test empty dot path
    try:
        extract_value(data, "")
        print(f"❌ Empty dot path should raise KeyError")
        all_passed = False
    except KeyError:
        print(f"✅ Empty dot path raises KeyError as expected")

    # Test safe extraction fallback
    result = extract_value_safe(data, "user.name", "default")
    if result == "default":
        print(f"✅ Safe extraction returns default on error")
    else:
        print(f"❌ Safe extraction failed: expected 'default', got '{result}'")
        all_passed = False

    return all_passed


def test_multiple_events():
    """Test multiple event types."""
    print("\n" + "=" * 70)
    print("Test 5: Multiple event types")
    print("=" * 70)

    example_file = Path(__file__).parent.parent / "config" / "mapping.yml.example"
    config = load_mapping_config(str(example_file))

    test_events = [
        ("file.save", "process_payload"),
        ("file.open", "ack_event"),
        ("git.push", "process_payload"),
        ("auth.login", "ack_event"),
        ("error.reported", "process_payload"),
        ("message.received", "process_payload"),
    ]

    all_passed = True
    for event_type, expected_tool in test_events:
        mapping = find_mapping_for_event(config, event_type)
        if mapping and mapping.tool == expected_tool:
            print(f"✅ '{event_type}' -> '{expected_tool}'")
        else:
            print(f"❌ '{event_type}' -> expected '{expected_tool}', got '{mapping.tool if mapping else None}'")
            all_passed = False

    # Test unknown event
    mapping = find_mapping_for_event(config, "unknown.event")
    if mapping is None:
        print(f"✅ Unknown event returns None")
    else:
        print(f"❌ Unknown event should return None, got '{mapping}'")
        all_passed = False

    return all_passed


def main():
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("MCP Webhook Mapping Module Verification")
    print("=" * 70)

    results = {
        "Example mapping file": test_example_mapping_file(),
        "Dot-path extraction": test_dot_path_extraction(),
        "Event resolution": test_event_resolution(),
        "Error handling": test_error_handling(),
        "Multiple events": test_multiple_events(),
    }

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")

    all_passed = all(results.values())

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ All verification tests passed!")
    else:
        print("❌ Some verification tests failed")
    print("=" * 70 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
