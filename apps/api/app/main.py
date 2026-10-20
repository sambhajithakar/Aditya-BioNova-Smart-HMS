"""FastAPI application factory: middleware, routers, error handling."""
from __future__ import annotations

import logging
import re
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import get_settings
from .entitlements import enforce_writable, require_feature
from .routers import (
    ai,
    audit,
    appointments,
    auth,
    billing,
    branches,
    dev,
    encounters,
    expenses,
    health,
    inventory,
    ipd,
    lab,
    members,
    opd_queue,
    organization,
    patients,
    pharmacy,
    platform,
    prescriptions,
    reports,
    subscription,
    support,
)

logger = logging.getLogger("hms.api")

BASE_PREFIX = "/api/v1"

# Client-supplied correlation ids are echoed into logs and audit rows
# (varchar(64)); anything else is replaced by a server-generated id.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

# GET endpoints that disclose patient health information. A successful read
# is audited as ``phi.read`` (path only — query strings may hold names or
# phone numbers and are never logged).
_PHI_PATH_RE = re.compile(
    r"^/api/v1/(patients|encounters|prescriptions|lab|ipd|opd|appointments"
    r"|billing/invoices|billing/payments|pharmacy/dispenses)(/|$)"
)
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# PostgreSQL SQLSTATEs translated into client errors instead of a bare 500.
_PG_ERRORS = {
    "23505": (409, "Conflicts with an existing record"),
    "23P01": (409, "Conflicts with an existing record"),
    "23503": (422, "A referenced record does not exist"),
    "23514": (422, "A value violates a data rule"),
    "23502": (422, "A required value is missing"),
    "22001": (422, "A value is too long"),
    "22003": (422, "A numeric value is out of range"),
    "40001": (409, "Concurrent update; retry the request"),
    "40P01": (409, "Concurrent update; retry the request"),
}


def _audit_phi_read(request: Request) -> None:
    from .auditing import record_security_event

    principal = request.state.principal
    path = request.url.path
    ids = _UUID_RE.findall(path)
    record_security_event(
        action="phi.read",
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type=_PHI_PATH_RE.match(path).group(1),
        resource_id=ids[-1] if ids else None,
        metadata={"path": path[:300], "role": principal.role_key},
        correlation_id=getattr(request.state, "correlation_id", None),
        ip_address=request.client.host[:60] if request.client else None,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Aditya BioNova Smart HMS — multi-tenant clinic & hospital "
            "management API. Synthetic/development data only; no real patient data."
        ),
        openapi_url=f"{BASE_PREFIX}/openapi.json",
        docs_url=f"{BASE_PREFIX}/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or ""
        if not _REQUEST_ID_RE.match(rid):
            rid = uuid.uuid4().hex
        request.state.correlation_id = rid
        response = await call_next(request)
        if (
            request.method == "GET"
            and 200 <= response.status_code < 300
            and getattr(request.state, "principal", None) is not None
            and _PHI_PATH_RE.match(request.url.path)
        ):
            try:
                await run_in_threadpool(_audit_phi_read, request)
            except Exception:
                # fail closed: no audit trail, no PHI
                logger.exception("phi.read audit failed rid=%s", rid)
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "Internal server error", "correlation_id": rid},
                )
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    async def _with_correlation(request: Request, response: JSONResponse) -> JSONResponse:
        """Add ``correlation_id`` to FastAPI's standard error bodies (same
        ``detail`` shape as before, so existing clients are unaffected)."""
        import json

        body = json.loads(response.body)
        body["correlation_id"] = getattr(request.state, "correlation_id", "")
        return JSONResponse(status_code=response.status_code, content=body,
                            headers={k: v for k, v in response.headers.items()
                                     if k.lower() not in ("content-length", "content-type")})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return await _with_correlation(request, await http_exception_handler(request, exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return await _with_correlation(
            request, await request_validation_exception_handler(request, exc))

    @app.exception_handler(DBAPIError)
    async def db_error(request: Request, exc: DBAPIError) -> JSONResponse:
        rid = getattr(request.state, "correlation_id", "")
        code = getattr(exc.orig, "pgcode", None)
        if code == "P0001":
            # our own trigger guards (immutability, ledgers, state machines):
            # their messages are written for humans and contain no data
            msg = str(getattr(exc.orig, "diag", None) and exc.orig.diag.message_primary
                      or "Operation not allowed")
            return JSONResponse(status_code=409,
                                content={"detail": msg[:300], "correlation_id": rid})
        if code in _PG_ERRORS:
            http_status, msg = _PG_ERRORS[code]
            logger.info("db constraint %s rid=%s path=%s", code, rid, request.url.path)
            return JSONResponse(status_code=http_status,
                                content={"detail": msg, "correlation_id": rid})
        logger.exception("database error rid=%s path=%s", rid, request.url.path)
        return JSONResponse(status_code=500,
                            content={"detail": "Internal server error", "correlation_id": rid})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "correlation_id", "")
        logger.exception("unhandled error rid=%s path=%s", rid, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "correlation_id": rid},
        )

    # Account, administration and vendor surfaces stay reachable whatever the
    # subscription state (a lapsed clinic can still manage, export and pay).
    for r in (health.router, auth.router, branches.router, members.router, audit.router,
              organization.router, subscription.router, support.router, platform.router):
        app.include_router(r, prefix=BASE_PREFIX)

    # Clinical/operational modules: gated by the edition's features; writes
    # need a writable subscription (reads always work — records stay accessible).
    app.include_router(patients.router, prefix=BASE_PREFIX,
                       dependencies=[Depends(enforce_writable)])
    gated = [
        (appointments.router, "appointments"), (opd_queue.router, "opd_queue"),
        (encounters.router, "consultation"), (prescriptions.router, "consultation"),
        (billing.router, "billing"), (pharmacy.router, "pharmacy"),
        (lab.router, "laboratory"), (ipd.router, "ipd"), (inventory.router, "inventory"),
        (expenses.router, "expenses"), (reports.router, "reports_basic"),
    ]
    for r, feature in gated:
        app.include_router(r, prefix=BASE_PREFIX,
                           dependencies=[Depends(require_feature(feature))])
    # AI: questions are reads, so they keep working on a read-only subscription
    app.include_router(ai.router, prefix=BASE_PREFIX, dependencies=[
        Depends(require_feature("ai_copilot", writes_need_writable=False))])
    if settings.is_dev:
        app.include_router(dev.router, prefix=BASE_PREFIX)
    return app


app = create_app()
