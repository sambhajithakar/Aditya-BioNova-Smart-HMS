"""Operations probes: liveness vs readiness (M7.0)."""
from __future__ import annotations

from sqlalchemy import create_engine


def test_liveness_does_not_need_auth(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_ok_when_database_reachable(client):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_readiness_503_when_database_unreachable(client, monkeypatch):
    from app import db as db_module

    # Port 1 on loopback: connection refused immediately, no real DB touched.
    dead = create_engine(
        "postgresql+psycopg2://nobody:secret-pw@127.0.0.1:1/nowhere",
        connect_args={"connect_timeout": 2},
    )
    monkeypatch.setattr(db_module, "engine", dead)
    try:
        resp = client.get("/api/v1/health/ready")
    finally:
        dead.dispose()
    assert resp.status_code == 503
    body = resp.json()
    assert body == {"status": "unavailable", "checks": {"database": "fail"}}
    # No connection details leak to unauthenticated callers.
    raw = resp.text
    for leak in ("127.0.0.1", "nobody", "secret-pw", "nowhere", "psycopg2"):
        assert leak not in raw

    # Liveness is unaffected by a database outage.
    assert client.get("/api/v1/health").status_code == 200
