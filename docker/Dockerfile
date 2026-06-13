FROM python:3.10.13-alpine

# Install Chrome/Chromium, chromedriver, and curl
# Use --no-cache to reduce layer size on ARM64
RUN apk update && apk add --no-cache \
    chromium \
    chromium-chromedriver \
    curl \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# Upgrade pip (ARM64 can be slow, use --no-cache to optimize)
RUN pip install --upgrade --no-cache-dir pip

# Copy application files
COPY requirements.txt requirements.txt
COPY src/ src/
COPY run.py run.py

# Install Python requirements with optimizations for ARM64
# --no-cache-dir reduces filesystem overhead
RUN pip install --no-cache-dir -r requirements.txt

# Set display port as an environment variable
ENV DISPLAY=:99

# ARM64/Alpine memory optimization environment variables
# These help prevent OOM kills and /dev/shm saturation on constrained systems
ENV MALLOC_TRIM_THRESHOLD_=128000 \
    MALLOC_MMAP_THRESHOLD_=131072 \
    MALLOC_MMAP_MAX_=65536

# Expose health check port
EXPOSE 8080

# Add health check with extended timeout for ARM64 slow startup
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application with headless flag
CMD ["python", "run.py", "--headless"]
