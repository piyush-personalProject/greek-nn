# Dockerfile
# Multi-stage build for GreekNN Risk System

# Stage 1: Builder
FROM python:3.10-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Production
FROM python:3.10-slim as production

# Create non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup -d /home/appuser -s /bin/bash appuser && \
    mkdir -p /home/appuser && \
    chown -R appuser:appgroup /home/appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appgroup . .

# Create required directories
RUN mkdir -p /app/models /app/logs /app/data /app/cache && \
    chown appuser:appgroup /app/models /app/logs /app/data /app/cache

# Environment defaults for production
ENV ENVIRONMENT=production
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check using FastAPI health endpoint
# Increased start-period to allow app to fully initialize with gunicorn prefork
HEALTHCHECK --interval=60s --timeout=30s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run application with gunicorn for production
# Use 2 workers + 1 for gunicorn master = 3 processes
# --preload loads app in master before forking workers to ensure proper initialization
# --max-requests and --max-requests-jitter prevent memory leaks from request handling
CMD ["sh", "-c", "gunicorn api:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --access-logfile - --error-logfile - --preload --max-requests 1000 --max-requests-jitter 50"]