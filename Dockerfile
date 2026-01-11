# Use Python 3.11 slim base image
FROM python:3.11-slim

# Set environment variables
# PYTHONUNBUFFERED ensures logs go to stdout/stderr immediately
# PYTHONDONTWRITEBYTECODE prevents .pyc files from being written
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies if needed
# (none required for this lightweight implementation)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml first for better Docker layer caching
COPY pyproject.toml ./

# Install Python dependencies
# Using --no-deps and explicitly listing dependencies would be faster,
# but pip install -e . works well for development and ensures all dependencies are installed
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source code
COPY src/ ./src/

# Create config directory for mapping.yml and other configs
RUN mkdir -p /app/config

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Expose the configurable port (default: 9000)
# This is the TCP port that the stdio-proxy will listen on
EXPOSE 9000

# Health check to verify the proxy is listening on the configured port
# Checks every 30 seconds with 10 second timeout, starting after startup period
# Retries 3 times before marking container as unhealthy
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', 9000)); s.close()" || exit 1

# Set entrypoint to use the shell script
# The script handles signal propagation and configuration display
ENTRYPOINT ["/app/entrypoint.sh"]

# No CMD needed as the entrypoint script runs the proxy directly
# The proxy is started via: exec python -m mcp_webhook.proxy
