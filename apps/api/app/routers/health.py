"""Liveness and readiness probes (no auth, no sensitive data).

* ``GET /health``        — liveness: the process is up and serving requests.
  Never touches the database, so a DB outage does not get healthy API
  containers restarted in a loop.
* ``GET /health/ready``  — readiness: the API can reach PostgreSQL with its
  runtime (non-owner) role. Returns 503 while the database is unavailable so
  load balancers / orchestrators stop routing traffic to this instance.
  The body never includes connection strings, hostnames or driver errors.
"""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .. import __version__
from .. import db as db_module
from ..config import get_settings
from ..schemas import HealthOut

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    s = get_settings()
    return HealthOut(
        status="ok",
        service=s.app_name,
        version=__version__,
        environment=s.environment,
    )


@router.get(
    "/health/ready",
    responses={
        200: {"description": "Database reachable; instance ready for traffic"},
        503: {"description": "Database unreachable; instance not ready"},
    },
)
def ready() -> JSONResponse:
    try:
        # Looked up at call time so the engine can be swapped in tests.
        with db_module.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any failure means "not ready"
        # Exception class only: driver messages can contain host/user names.
        logger.warning("readiness check failed: database unavailable")
        return JSONResponse(
            status_code=503, content={"status": "unavailable", "checks": {"database": "fail"}}
        )
    return JSONResponse(status_code=200, content={"status": "ready", "checks": {"database": "ok"}})
