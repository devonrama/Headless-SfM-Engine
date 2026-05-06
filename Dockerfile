# Multi-stage Dockerfile for Headless SfM Engine
# Base: official COLMAP image (includes COLMAP binary + CUDA runtime)
# Note: GPU runtime requires --gpus all flag; CPU-only fallback works but slower.

FROM colmap/colmap:latest

# Install Python 3 and pip (COLMAP base image is Ubuntu, no Python by default)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ /app/src/

# Create runtime data directories
RUN mkdir -p /app/data/raw /app/data/output

# Expose API port
EXPOSE 8000

# Healthcheck — verify uvicorn responds
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs').read()" || exit 1

# Run uvicorn
CMD ["python3", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]