# syntax=docker/dockerfile:1
# SYNTHETIC-DATA DEMO ONLY: one-shot job that loads the demo clinics
# (scripts/seed_demo.py) — used by docker-compose.demo.yml, never deployed.
# The seed drives the real API in-process through FastAPI's TestClient, which
# needs httpx from the hash-locked DEV lock; that is why this is a separate
# image and the production API image stays without dev dependencies. The
# script itself refuses to run unless ENVIRONMENT is development or test.
FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY apps/api/requirements-dev.lock /tmp/requirements-dev.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements-dev.lock
RUN groupadd --system --gid 10001 hms \
 && useradd --system --uid 10001 --gid hms --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin hms
WORKDIR /app/apps/api
COPY --chown=root:root apps/api/app ./app
COPY --chown=root:root scripts/seed_demo.py /app/scripts/seed_demo.py
COPY --chown=root:root packages/contracts/device_vectors.json /app/packages/contracts/device_vectors.json
USER 10001:10001
CMD ["python", "../../scripts/seed_demo.py"]
