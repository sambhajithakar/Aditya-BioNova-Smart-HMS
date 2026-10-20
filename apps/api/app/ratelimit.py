"""Fixed-window rate limiting and account lockout, stored in PostgreSQL.

Counters live in ``rate_limit_counters`` (migration 0009) so limits hold
across API instances without extra infrastructure. Keys are SHA-256 hashed:
no raw e-mail address or IP is stored. Every hit is written in its OWN
committed transaction, because the requests being counted (failed logins,
bad MFA codes) usually end in a rollback.

Lockout is keyed by the *submitted e-mail*, whether or not an account
exists, so the 429 response never reveals which e-mails are registered.
"""
from __future__ import annotations

import hashlib
import time

from fastapi import HTTPException, status
from sqlalchemy import text

from .config import get_settings

_UPSERT = text(
    """
    INSERT INTO rate_limit_counters (key_hash, window_start, hits, expires_at)
    VALUES (:k, to_timestamp(:ws), 1, to_timestamp(:exp))
    ON CONFLICT (key_hash, window_start)
    DO UPDATE SET hits = rate_limit_counters.hits + 1
    RETURNING hits
    """
)
_PEEK = text(
    "SELECT hits FROM rate_limit_counters "
    "WHERE key_hash = :k AND window_start = to_timestamp(:ws)"
)
_CLEAR = text("DELETE FROM rate_limit_counters WHERE key_hash = :k")
_PRUNE = text("DELETE FROM rate_limit_counters WHERE expires_at < now()")


def _key(scope: str, ident: str) -> str:
    return hashlib.sha256(f"{scope}:{ident.lower()}".encode()).hexdigest()


def _window(window_seconds: int) -> tuple[int, int]:
    now = int(time.time())
    start = now - now % window_seconds
    return start, start + window_seconds


def too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many attempts. Try again later.",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _run(stmt, params: dict) -> int | None:
    from .db import SessionLocal

    db = SessionLocal()
    try:
        result = db.execute(stmt, params)
        row = result.first() if result.returns_rows else None
        db.commit()
        return row[0] if row else None
    finally:
        db.close()


def hit(scope: str, ident: str | None, *, limit: int, window_seconds: int) -> None:
    """Count one request; raise 429 once ``limit`` is exceeded in the window."""
    if not get_settings().rate_limit_enabled or not ident:
        return
    start, end = _window(window_seconds)
    hits = _run(_UPSERT, {"k": _key(scope, ident), "ws": start, "exp": end}) or 0
    if hits % 500 == 1:  # cheap opportunistic cleanup
        _run(_PRUNE, {})
    if hits > limit:
        raise too_many(end - int(time.time()))


def check(scope: str, ident: str | None, *, limit: int, window_seconds: int) -> None:
    """Raise 429 if the counter is already at ``limit`` (does not count)."""
    if not get_settings().rate_limit_enabled or not ident:
        return
    start, end = _window(window_seconds)
    hits = _run(_PEEK, {"k": _key(scope, ident), "ws": start}) or 0
    if hits >= limit:
        raise too_many(end - int(time.time()))


def record(scope: str, ident: str | None, *, window_seconds: int) -> None:
    """Count one event without enforcing (paired with ``check``)."""
    if not get_settings().rate_limit_enabled or not ident:
        return
    start, end = _window(window_seconds)
    _run(_UPSERT, {"k": _key(scope, ident), "ws": start, "exp": end})


def clear(scope: str, ident: str | None) -> None:
    if not ident:
        return
    _run(_CLEAR, {"k": _key(scope, ident)})
