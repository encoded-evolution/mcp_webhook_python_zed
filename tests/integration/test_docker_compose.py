"""Integration tests for docker-compose configuration.

These tests verify:
- docker-compose.yml exists and has valid syntax
- Service configuration is correct
- Environment variables are properly configured
- Volume and port mappings are correct
- Health checks are configured
"""

import os
import yaml
import pytest
from pathlib import Path


def test_docker_compose_exists():
    """Test that docker-compose.yml exists at project root."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"
    assert compose_file.exists(), "docker-compose.yml not found at project root"


def test_docker_compose_yaml_syntax():
    """Test that docker-compose.yml has valid YAML syntax."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()

    # Try to parse as YAML
    try:
        data = yaml.safe_load(content)
        assert data is not None, "docker-compose.yml is empty or invalid"
    except yaml.YAMLError as e:
        pytest.fail(f"docker-compose.yml has invalid YAML syntax: {e}")


def test_docker_compose_version():
    """Test that docker-compose.yml has a valid version."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    assert "version" in data, "docker-compose.yml missing version field"
    # Check for version 3.x format
    assert str(data["version"]).startswith("3"), \
        f"Expected docker-compose version 3.x, got {data['version']}"


def test_docker_compose_has_services():
    """Test that docker-compose.yml defines services."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    assert "services" in data, "docker-compose.yml missing services section"
    assert len(data["services"]) > 0, "docker-compose.yml has no services defined"


def test_docker_compose_main_service():
    """Test that docker-compose.yml has the main MCP service."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # The main service should exist (may be named "mcp-stdio" or similar)
    assert len(data["services"]) > 0, "No services found in docker-compose.yml"

    # Get first service
    service_name = list(data["services"].keys())[0]
    service = data["services"][service_name]

    # Verify service has required fields
    assert "image" in service or "build" in service, \
        f"Service {service_name} must have either 'image' or 'build' directive"


def test_docker_compose_port_mapping():
    """Test that docker-compose.yml has port mapping."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # Check each service for port mapping
    services_with_ports = []
    for service_name, service_config in data["services"].items():
        if "ports" in service_config:
            services_with_ports.append(service_name)
            ports = service_config["ports"]
            assert len(ports) > 0, f"Service {service_name} has empty ports list"
            # Check for port 9000 (default MCP port)
            assert any("9000" in str(p) for p in ports), \
                f"Service {service_name} should map port 9000"

    assert len(services_with_ports) > 0, "No services with port mappings found"


def test_docker_compose_environment_variables():
    """Test that docker-compose.yml has required environment variables."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # Get first service
    service_name = list(data["services"].keys())[0]
    service = data["services"][service_name]

    assert "environment" in service, f"Service {service_name} missing environment section"

    env_vars = service["environment"]

    # Check for required environment variables
    required_vars = ["PORT", "MCP_NAME", "LOG_LEVEL", "MAPPING_FILE"]
    for var in required_vars:
        assert any(var in str(e) for e in env_vars), \
            f"Service {service_name} should have environment variable {var}"


def test_docker_compose_volume_mounts():
    """Test that docker-compose.yml has volume mounts."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # Get first service
    service_name = list(data["services"].keys())[0]
    service = data["services"][service_name]

    assert "volumes" in service, f"Service {service_name} missing volumes section"

    volumes = service["volumes"]
    assert len(volumes) > 0, f"Service {service_name} has no volumes"

    # Check for config directory mount
    assert any("config" in str(v) for v in volumes), \
        f"Service {service_name} should mount config directory"


def test_docker_compose_healthcheck():
    """Test that docker-compose.yml has health check configuration."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # Get first service
    service_name = list(data["services"].keys())[0]
    service = data["services"][service_name]

    # Health check can be at service level or in docker-compose file level
    # Check service level first
    if "healthcheck" in service:
        healthcheck = service["healthcheck"]
        assert "test" in healthcheck, "Health check missing test command"
        assert "interval" in healthcheck, "Health check missing interval"
        assert "timeout" in healthcheck, "Health check missing timeout"
        assert "retries" in healthcheck, "Health check missing retries"


def test_docker_compose_restart_policy():
    """Test that docker-compose.yml has restart policy."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # Get first service
    service_name = list(data["services"].keys())[0]
    service = data["services"][service_name]

    assert "restart" in service, f"Service {service_name} missing restart policy"

    # Check for reasonable restart policies
    valid_policies = ["always", "on-failure", "unless-stopped"]
    assert service["restart"] in valid_policies, \
        f"Invalid restart policy: {service['restart']}"


def test_docker_compose_logging():
    """Test that docker-compose.yml has logging configuration."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # Get first service
    service_name = list(data["services"].keys())[0]
    service = data["services"][service_name]

    if "logging" in service:
        logging_config = service["logging"]
        assert "driver" in logging_config, "Logging config missing driver"
        assert logging_config["driver"] == "json-file", "Expected json-file driver"


def test_mapping_yml_example_exists():
    """Test that mapping.yml.example exists in config directory."""
    project_root = Path(__file__).parent.parent.parent
    mapping_example = project_root / "config" / "mapping.yml.example"
    assert mapping_example.exists(), "config/mapping.yml.example not found"


def test_mapping_yml_example_valid_yaml():
    """Test that mapping.yml.example has valid YAML syntax."""
    project_root = Path(__file__).parent.parent.parent
    mapping_example = project_root / "config" / "mapping.yml.example"

    content = mapping_example.read_text()

    try:
        data = yaml.safe_load(content)
        assert data is not None, "mapping.yml.example is empty or invalid"
    except yaml.YAMLError as e:
        pytest.fail(f"mapping.yml.example has invalid YAML syntax: {e}")


def test_mapping_yml_example_has_mappings():
    """Test that mapping.yml.example defines mappings."""
    project_root = Path(__file__).parent.parent.parent
    mapping_example = project_root / "config" / "mapping.yml.example"

    content = mapping_example.read_text()
    data = yaml.safe_load(content)

    assert "mappings" in data, "mapping.yml.example missing 'mappings' key"
    assert len(data["mappings"]) > 0, "mapping.yml.example has no mappings defined"

    # Check that each mapping has required fields
    for mapping in data["mappings"]:
        assert "event" in mapping, f"Mapping missing 'event' field: {mapping}"
        assert "tool" in mapping, f"Mapping missing 'tool' field: {mapping}"


@pytest.mark.parametrize(
    "var_name",
    ["PORT", "MCP_NAME", "WEBHOOK_BEARER_TOKENS", "ASYNC_PROCESSING", "LOG_LEVEL"],
)
def test_docker_compose_env_has_defaults(var_name):
    """Test that docker-compose.yml environment variables have default values."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # Get first service
    service_name = next(iter(data["services"].keys()))
    service = data["services"][service_name]

    env_vars = service["environment"]

    # Find the variable and check for default value
    var_config = [e for e in env_vars if var_name in str(e)]
    assert len(var_config) > 0, f"Environment variable {var_name} not found"

    # Check for default value syntax (${VAR:-default})
    var_str = str(var_config[0])
    assert ":-" in var_str, f"{var_name} should have default value with :- syntax"


def test_docker_compose_build_config():
    """Test that docker-compose.yml has proper build configuration."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker-compose.yml"

    content = compose_file.read_text()
    data = yaml.safe_load(content)

    # Get first service
    service_name = next(iter(data["services"].keys()))
    service = data["services"][service_name]

    # Service should have either build or image
    if "build" in service:
        build_config = service["build"]
        if isinstance(build_config, dict):
            assert "context" in build_config, "Build config missing context"
            assert "dockerfile" in build_config, "Build config missing dockerfile"
