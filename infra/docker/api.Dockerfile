# syntax=docker/dockerfile:1
# Aditya BioNova Smart HMS — API image.
# Build from the repository root (context = repo root, see .dockerignore):
#   docker build -f infra/docker/api.Dockerfile -t hms-api:local .
#
# * Dependencies come ONLY from the hash-locked apps/api/requirements.lock.
# * Runs as an unprivileged user; no secrets are baked in (all via env).
# * Does NOT run migrations on start: use the separate `migrate` one-shot
#   job (`alembic upgrade head`, see docker-compose.yml / DEPLOYMENT.md).

# Base: python:3.12.15-slim pinned by multi-arch index digest (resolved
# 2026-10-20). Bump tag+digest together (both FROM lines) when patching.
FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS deps
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY apps/api/requirements.lock /tmp/requirements.lock
# --require-hashes: every artefact must match the lock; --no-deps: nothing
# outside the lock can be pulled in.
RUN /opt/venv/bin/pip install --require-hashes --no-deps -r /tmp/requirements.lock

FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS runtime
# uvicorn reads FORWARDED_ALLOW_IPS (--forwarded-allow-ips) and
# WEB_CONCURRENCY (--workers) from the environment. Set FORWARDED_ALLOW_IPS
# at deploy time to the reverse proxy's address/network so client IPs in the
# audit trail are real; the default trusts only loopback.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    FORWARDED_ALLOW_IPS=127.0.0.1 \
    WEB_CONCURRENCY=2

RUN groupadd --system --gid 10001 hms \
 && useradd --system --uid 10001 --gid hms --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin hms

COPY --from=deps /opt/venv /opt/venv
WORKDIR /app
# Only what the service needs: application package + migrations.
COPY --chown=root:root apps/api/alembic.ini ./alembic.ini
COPY --chown=root:root apps/api/alembic ./alembic
COPY --chown=root:root apps/api/app ./app

USER 10001:10001
EXPOSE 8000

# Liveness only (/health never touches the DB). Orchestrators should use
# /api/v1/health/ready for readiness (503 while the DB is unreachable).
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"]

# Exec form: uvicorn is PID 1 and receives SIGTERM directly (graceful stop).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
