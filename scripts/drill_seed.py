"""Synthetic data for the backup/restore drill — driven through the real API.

Run from apps/api with DATABASE_URL (hms_app role) and JWT_SECRET set:
    python ../../scripts/drill_seed.py seed     # 2 tenants, branches, patients
    python ../../scripts/drill_seed.py login    # owner login works (post-restore)

All data is synthetic (no real people). Writes go through FastAPI + the
non-owner role, so RLS, audit triggers and sequences are exercised exactly
as in production.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = "Drill-Synthetic-Passphrase-1"
TENANTS = ("drill-clinic-a", "drill-clinic-b")
PATIENTS_PER_TENANT = 6


def _ok(resp, code: int, what: str):
    if resp.status_code != code:
        sys.exit(f"drill_seed: {what} -> HTTP {resp.status_code}")
    return resp.json()


def seed(client: TestClient) -> None:
    for t, slug in enumerate(TENANTS):
        reg = _ok(client.post("/api/v1/auth/register", json={
            "organization_name": slug.replace("-", " ").title(),
            "organization_slug": slug,
            "full_name": "Dr. Drill Owner",
            "email": f"owner@{slug}.example.com",
            "password": PASSWORD,
        }), 201, f"register {slug}")
        h = {"Authorization": f"Bearer {reg['tokens']['access_token']}"}
        _ok(client.post("/api/v1/branches", json={"name": "Main", "code": "MAIN"},
                        headers=h), 201, "branch")
        for i in range(PATIENTS_PER_TENANT):
            _ok(client.post("/api/v1/patients", json={
                "full_name": f"Synthetic Drill Patient {t}-{i}",
                "phone": f"97{t}{str(i).zfill(7)}",
                "gender": "female" if i % 2 else "male",
                "date_of_birth": f"19{70 + i}-01-1{t}",
                "address": "Synthetic Village",
            }, headers=h), 201, "patient")
        _ok(client.get("/api/v1/patients", headers=h), 200, "list patients")
    print(f"drill_seed: seeded {len(TENANTS)} tenants x {PATIENTS_PER_TENANT} patients via API")


def login(client: TestClient) -> None:
    for slug in TENANTS:
        tok = _ok(client.post("/api/v1/auth/login", json={
            "email": f"owner@{slug}.example.com", "password": PASSWORD,
            "organization_slug": slug,
        }), 200, f"login {slug}")
        h = {"Authorization": f"Bearer {tok['tokens']['access_token']}"}
        total = _ok(client.get("/api/v1/patients", headers=h), 200, "list patients")["total"]
        if total != PATIENTS_PER_TENANT:
            sys.exit(f"drill_seed: {slug} sees {total} patients, expected {PATIENTS_PER_TENANT}")
    print(f"drill_seed: owner login + tenant-scoped patient list OK for {len(TENANTS)} tenants")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "seed"
    with TestClient(app) as c:
        {"seed": seed, "login": login}[mode](c)
