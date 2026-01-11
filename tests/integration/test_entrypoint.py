"""Integration tests for entrypoint script and Dockerfile.

These tests verify:
- Entrypoint script syntax and functionality
- Docker configuration
- Container startup behavior
- Configuration loading
"""

import os
import pytest
import subprocess
import shutil
from pathlib import Path


def test_entrypoint_script_exists():
    """Test that entrypoint.sh exists at project root."""
    project_root = Path(__file__).parent.parent.parent
    entrypoint_path = project_root / "entrypoint.sh"
    assert entrypoint_path.exists(), "entrypoint.sh not found at project root"


def test_entrypoint_script_executable():
    """Test that entrypoint.sh has execute permissions (Unix-like systems)."""
    project_root = Path(__file__).parent.parent.parent
    entrypoint_path = project_root / "entrypoint.sh"

    if os.name != "nt":  # Skip on Windows
        assert os.access(entrypoint_path, os.X_OK), "entrypoint.sh is not executable"


@pytest.mark.skipif(
    os.name == "nt",
    reason="Bash not available on Windows without WSL or Git Bash",
)
def test_entrypoint_bash_syntax():
    """Test that entrypoint.sh has valid bash syntax."""
    project_root = Path(__file__).parent.parent.parent
    entrypoint_path = project_root / "entrypoint.sh"

    result = subprocess.run(
        ["bash", "-n", str(entrypoint_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"entrypoint.sh has syntax errors: {result.stderr}"


def test_dockerfile_exists():
    """Test that Dockerfile exists at project root."""
    project_root = Path(__file__).parent.parent.parent
    dockerfile_path = project_root / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile not found at project root"


def test_dockerfile_from_statement():
    """Test that Dockerfile has a valid FROM statement."""
    project_root = Path(__file__).parent.parent.parent
    dockerfile_path = project_root / "Dockerfile"

    content = dockerfile_path.read_text()
    lines = content.split("\n")

    # Find first non-comment, non-empty line
    from_line = None
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            from_line = stripped
            break

    assert from_line is not None, "Dockerfile has no FROM statement"
    assert from_line.startswith("FROM"), f"First line should be FROM, got: {from_line}"
    assert "python:" in from_line.lower(), "FROM statement should reference Python"


def test_dockerfile_expose_port():
    """Test that Dockerfile exposes a port."""
    project_root = Path(__file__).parent.parent.parent
    dockerfile_path = project_root / "Dockerfile"

    content = dockerfile_path.read_text()
    assert "EXPOSE" in content, "Dockerfile should have EXPOSE directive"
    assert "9000" in content, "Dockerfile should expose port 9000"


def test_dockerfile_entrypoint():
    """Test that Dockerfile has ENTRYPOINT directive."""
    project_root = Path(__file__).parent.parent.parent
    dockerfile_path = project_root / "Dockerfile"

    content = dockerfile_path.read_text()
    assert "ENTRYPOINT" in content, "Dockerfile should have ENTRYPOINT directive"
    assert "entrypoint.sh" in content.lower(), "ENTRYPOINT should reference entrypoint.sh"


def test_dockerfile_healthcheck():
    """Test that Dockerfile has HEALTHCHECK directive."""
    project_root = Path(__file__).parent.parent.parent
    dockerfile_path = project_root / "Dockerfile"

    content = dockerfile_path.read_text()
    assert "HEALTHCHECK" in content, "Dockerfile should have HEALTHCHECK directive"


def test_env_example_exists():
    """Test that .env.example exists."""
    project_root = Path(__file__).parent.parent.parent
    env_example_path = project_root / "config" / ".env.example"
    assert env_example_path.exists(), ".env.example not found in config/"


def test_env_example_has_required_vars():
    """Test that .env.example has required environment variables."""
    project_root = Path(__file__).parent.parent.parent
    env_example_path = project_root / "config" / ".env.example"

    content = env_example_path.read_text()

    required_vars = [
        "PORT",
        "MCP_NAME",
        "WEBHOOK_BEARER_TOKENS",
        "ASYNC_PROCESSING",
        "MAPPING_FILE",
        "LOG_LEVEL",
    ]

    for var in required_vars:
        assert var in content, f".env.example should contain {var}"


def test_entrypoint_displays_config():
    """Test that entrypoint script displays configuration."""
    project_root = Path(__file__).parent.parent.parent
    entrypoint_path = project_root / "entrypoint.sh"

    content = entrypoint_path.read_text()

    # Check that configuration display is present
    assert "Configuration:" in content, "entrypoint.sh should display configuration header"
    assert "Server Name" in content, "entrypoint.sh should display server name"
    assert "Port" in content, "entrypoint.sh should display port"
    assert "Authentication" in content, "entrypoint.sh should display authentication status"


def test_entrypoint_uses_exec():
    """Test that entrypoint script uses exec for proper signal handling."""
    project_root = Path(__file__).parent.parent.parent
    entrypoint_path = project_root / "entrypoint.sh"

    content = entrypoint_path.read_text()

    # Check that exec is used to start the proxy
    assert "exec python" in content, "entrypoint.sh should use exec for signal handling"


@pytest.mark.skipif(
    os.name == "nt",
    reason="Docker not available or tests are Windows-specific",
)
def test_docker_build_sanity_check():
    """Sanity check: verify Dockerfile can be parsed (doesn't attempt full build).

    This is a minimal check that doesn't require Docker to actually build,
    just that the file structure is reasonable.
    """
    project_root = Path(__file__).parent.parent.parent
    dockerfile_path = project_root / "Dockerfile"

    content = dockerfile_path.read_text()

    # Check for key Dockerfile directives
    required_directives = ["FROM", "WORKDIR", "COPY", "RUN", "EXPOSE", "ENTRYPOINT"]
    for directive in required_directives:
        assert directive in content, f"Dockerfile missing {directive} directive"

    # Check that pyproject.toml is copied before pip install
    lines = content.split("\n")
    pyproject_line = None
    pip_line = None

    for i, line in enumerate(lines):
        if "pyproject.toml" in line and "COPY" in line:
            pyproject_line = i
        if "pip install" in line and "RUN" in line:
            pip_line = i

    assert pyproject_line is not None, "Dockerfile should COPY pyproject.toml"
    assert pip_line is not None, "Dockerfile should RUN pip install"
    assert pyproject_line < pip_line, "pyproject.toml should be copied before pip install"


def test_config_directory_created():
    """Test that entrypoint creates config directory."""
    project_root = Path(__file__).parent.parent.parent
    entrypoint_path = project_root / "entrypoint.sh"

    content = entrypoint_path.read_text()

    # Check that mkdir -p /app/config is present
    assert 'mkdir -p /app/config' in content, "entrypoint.sh should create config directory"


def test_mapping_file_warning():
    """Test that entrypoint warns if mapping file is missing."""
    project_root = Path(__file__).parent.parent.parent
    entrypoint_path = project_root / "entrypoint.sh"

    content = entrypoint_path.read_text()

    # Check for mapping file existence check
    assert "MAPPING_FILE" in content, "entrypoint.sh should reference MAPPING_FILE"
    assert "Mapping file not found" in content or "mapping file" in content.lower(), \
        "entrypoint.sh should warn about missing mapping file"


@pytest.mark.parametrize(
    "env_var,expected_default",
    [
        ("PORT", "9000"),
        ("MCP_NAME", "MCP-STDIO-Server"),
        ("ASYNC_PROCESSING", "false"),
        ("LOG_LEVEL", "INFO"),
    ],
)
def test_env_example_has_defaults(env_var, expected_default):
    """Test that .env.example has expected default values."""
    project_root = Path(__file__).parent.parent.parent
    env_example_path = project_root / "config" / ".env.example"

    content = env_example_path.read_text()

    # Check for the variable and its default
    lines = [line.strip() for line in content.split("\n") if line.strip() and not line.strip().startswith("#")]
    var_line = [line for line in lines if line.startswith(f"{env_var}=")]

    assert len(var_line) > 0, f"{env_var} not found in .env.example"
    assert expected_default in var_line[0], f"{env_var} should have default {expected_default}"
