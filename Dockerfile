# syntax=docker/dockerfile:1
# ============================================================================
# Backend image — FastAPI API (web) and the arq generation worker.
# Both processes run from THIS image; the worker just overrides the command
# (see docker-compose.prod.yml). Matches the Procfile:
#   web:    uvicorn backend.app:app --host 0.0.0.0 --port $PORT
#   worker: arq backend.worker.WorkerSettings
# ============================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached across code changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application code. config.py resolves the repo root as the parent of backend/,
# so /app is the root and /app/import, /app/services are the artifact dirs.
COPY backend/ ./backend/

# pipeline_runner writes here at import time; in prod these are mounted volumes
# shared between the web and worker containers.
RUN mkdir -p /app/import /app/services

EXPOSE 8000

# Dependency-free healthcheck: FastAPI always serves /openapi.json (no DB needed).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/openapi.json').status==200 else 1)"

# Default = the API. The worker service overrides this with:
#   command: ["arq", "backend.worker.WorkerSettings"]
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
