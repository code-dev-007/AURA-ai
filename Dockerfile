# ══════════════════════════════════════════════════════════════════════
#  AURA AI v2.0 — Optimized Multi-Stage Dockerfile
#  FastAPI + OpenCV + SQLite  ·  ~350 MB final image
# ══════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ─────────────────────────────────────────────────
#    Install build-time deps and compile wheels so the final image
#    stays free of gcc / dev headers.
FROM python:3.12-slim AS builder

# Avoid interactive prompts, bytecode files, and unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System libs required to *build* opencv-python, numpy, bcrypt, etc.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libglib2.0-0 \
        libgl1 \
        libsm6 \
        libxext6 \
        libxrender1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only requirements first to maximise Docker layer cache
COPY requirements.txt .

# Build all wheels into /build/wheels
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir=/build/wheels -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Aura AI Team" \
      description="Aura AI v2.0 — Exam Proctoring System" \
      version="2.0.0"

# Minimal runtime env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Default app config (overridable at runtime via -e / .env)
    HOST=0.0.0.0 \
    PORT=8000 \
    RELOAD=false \
    DATABASE_URL=sqlite:///./data/aura_v2.db

# Runtime-only system libs (OpenCV needs libgl1 + libglib2; no compiler)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Install pre-built wheels from the builder stage (no compilation here)
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels /tmp/wheels/*.whl && \
    rm -rf /tmp/wheels

# Create a non-root user for security
RUN groupadd -r aura && useradd -r -g aura -m -s /bin/bash aura

WORKDIR /app

# Copy application source (order: least-changed → most-changed for cache)
COPY requirements.txt .
COPY routes/ ./routes/
COPY tools/ ./tools/
COPY ui/ ./ui/
COPY app.py .

# Persistent data directory for SQLite DB
RUN mkdir -p /app/data && chown -R aura:aura /app

# Switch to non-root user
USER aura

# Expose the application port
EXPOSE 8000

# Healthcheck — hit the FastAPI docs endpoint every 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fs http://localhost:8000/docs || exit 1

# Run with uvicorn (production: no reload, single process)
CMD ["python", "-m", "uvicorn", "app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
