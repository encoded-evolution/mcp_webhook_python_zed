# Use Python 3.11 slim base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies (if needed)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
# COPY pyproject.toml ./
# RUN pip install --no-cache-dir -e ".[dev]"

# Copy source code
# COPY src/ ./src/

# Create config directory
RUN mkdir -p /app/config

# Expose the configurable port (default: 9000)
EXPOSE 9000

# Set entrypoint
# ENTRYPOINT ["python", "-m", "mcp_webhook.server"]

# Default command (will be overridden by entrypoint script)
# CMD []

# Health check
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', 9000)); s.close()" || exit 1

# NOTE: This is a stub. Uncomment and complete the above lines once the project is fully implemented.
