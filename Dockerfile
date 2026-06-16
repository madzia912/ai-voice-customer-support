# Single image used by both the API and the worker; the compose file picks
# the command to run for each service.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# System deps kept minimal: only certificates for HTTPS calls.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Non-root user for both services. Create /data with the right ownership
# *before* USER switch so the named-volume mount point inherits it.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /srv

USER appuser

COPY --chown=appuser:appuser app ./app

ENV DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8000

# Default to running the API; the worker service overrides this.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
