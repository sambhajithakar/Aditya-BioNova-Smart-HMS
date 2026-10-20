"""Seed a SYNTHETIC demonstration clinic through the real API.

Every person, phone number and address below is invented. Never point this
at a database holding real patient data; it refuses to run unless
ENVIRONMENT is development or test.

Run from apps/api with the same DATABASE_URL / JWT_SECRET as the API:
    python ../../scripts/seed_demo.py            # idempotent: skips if seeded

Creates one clinic ("Sunrise Demo Clinic", slug ``sunrise-demo``) with a
branch, one account per staff role, synthetic patients, appointments, an OPD
queue, ward/beds with one admission, pharmacy stock, an inventory item and a
lab order. Prints the demo credentials at the end.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

SLUG = "sunrise-demo"
DOMAIN = "sunrise-demo.example.com"   # reserved example domain: never deliverable
PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo-Sunrise-2026!")

STAFF = [  # (role, full name)
    ("admin", "Asha Admin (demo)"),
    ("doctor", "Dr. Meera Kulkarni (demo)"),
    ("nurse", "Sunita Pawar (demo)"),
    ("receptionist", "Rahul Shinde (demo)"),
    ("pharmacist", "Kiran Joshi (demo)"),
    ("lab_technician", "Vikas More (demo)"),
    ("billing", "Neha Deshmukh (demo)"),
    ("auditor", "Arun Auditor (demo)"),
]
PATIENTS = [  # synthetic names / numbers in the reserved 90000xxxxx range
    ("Ganesh Patil", "male", "1972-03-14"),
    ("Savita Jadhav", "female", "1985-07-02"),
    ("Aarav Deshpande", "male", "2016-11-20"),
    ("Lata Gaikwad", "female", "1958-01-09"),
    ("Imran Shaikh", "male", "1990-05-30"),
    ("Priya Nair", "female", "1994-09-17"),
    ("Baburao Kale", "male", "1949-12-25"),
    ("Fatima Sayyed", "female", "1979-04-04"),
]


def ok(resp, code: int, what: str):
    if resp.status_code != code:
        sys.exit(f"seed_demo: {what} -> HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def main() -> None:
    if not get_settings().is_dev:
        sys.exit("seed_demo: refusing to run outside ENVIRONMENT=development|test")
    c = TestClient(app)

    owner_email = f"owner@{DOMAIN}"
    probe = c.post("/api/v1/auth/login", json={"email": owner_email, "password": PASSWORD})
    if probe.status_code == 200:
        print("seed_demo: demo clinic already seeded")
        return print_credentials()

    reg = ok(c.post("/api/v1/auth/register", json={
        "organization_name": "Sunrise Demo Clinic",
        "organization_slug": SLUG,
        "full_name": "Dr. Sameer Owner (demo)",
        "email": owner_email,
        "password": PASSWORD,
    }), 201, "register clinic")
    h = {"Authorization": f"Bearer {reg['tokens']['access_token']}"}
    branch = ok(c.post("/api/v1/branches", json={"name": "Kothrud OPD", "code": "KOTHRUD"},
                       headers=h), 201, "branch")
    b = branch["id"]

    doctor_id = None
    for role, name in STAFF:
        m = ok(c.post("/api/v1/members", json={
            "email": f"{role.replace('_', '')}@{DOMAIN}", "full_name": name,
            "password": PASSWORD, "role_key": role, "branch_id": b,
        }, headers=h), 201, f"member {role}")
        if role == "doctor":
            doctor_id = m["user_id"]

    patients = []
    for i, (name, gender, dob) in enumerate(PATIENTS):
        patients.append(ok(c.post("/api/v1/patients", json={
            "full_name": name, "phone": f"90000{i:05d}", "gender": gender,
            "date_of_birth": dob, "address": "Synthetic Nagar, Pune (demo)",
            "allergies": "Penicillin" if i == 1 else "",
            "allow_duplicates": True,
        }, headers=h), 201, f"patient {name}"))

    tomorrow = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) \
        + timedelta(days=1)
    for k, p in enumerate(patients[:3]):
        start = tomorrow + timedelta(hours=k)
        ok(c.post("/api/v1/appointments", json={
            "patient_id": p["id"], "branch_id": b, "provider_user_id": doctor_id,
            "starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=15)).isoformat(),
            "reason": "Follow-up (demo)",
        }, headers=h), 201, "appointment")
    for p in patients[3:6]:
        ok(c.post("/api/v1/opd/queue", json={"patient_id": p["id"], "branch_id": b},
                  headers=h), 201, "queue")

    ward = ok(c.post("/api/v1/ipd/wards", json={"branch_id": b, "name": "General Ward",
                                                "code": "GW1"}, headers=h), 201, "ward")
    beds = [ok(c.post("/api/v1/ipd/beds", json={"ward_id": ward["id"], "label": f"GW1-{n}"},
                      headers=h), 201, "bed") for n in range(1, 5)]
    ok(c.post("/api/v1/ipd/admissions", json={
        "patient_id": patients[6]["id"], "ward_id": ward["id"], "bed_id": beds[0]["id"],
        "reason": "Community-acquired pneumonia — observation (demo)",
        "attending_user_id": doctor_id,
    }, headers=h), 201, "admission")

    drugs = ok(c.get("/api/v1/prescriptions/drugs?limit=5", headers=h), 200, "drugs")
    for n, d in enumerate(drugs[:3]):
        ok(c.post("/api/v1/pharmacy/stock/batches", json={
            "branch_id": b, "drug_id": d["id"], "batch_number": f"DEMO-{n + 1:03d}",
            "expiry_date": (date.today() + timedelta(days=300 + 30 * n)).isoformat(),
            "quantity": 200, "unit_cost": 1.5 + n, "supplier": "Synthetic Pharma (demo)",
        }, headers=h), 201, "stock")

    ok(c.post("/api/v1/inventory/items", json={
        "branch_id": b, "name": "Surgical gloves (box)", "sku": "GLV-M", "unit": "box",
        "reorder_level": 10, "unit_cost": 350,
    }, headers=h), 201, "inventory item")

    tests = ok(c.get("/api/v1/lab/tests", headers=h), 200, "lab tests")
    ok(c.post("/api/v1/lab/orders", json={
        "patient_id": patients[4]["id"], "branch_id": b,
        "test_ids": [t["id"] for t in tests[:2]], "clinical_notes": "Routine check (demo)",
    }, headers=h), 201, "lab order")

    print(f"seed_demo: seeded clinic '{SLUG}' — {len(STAFF) + 1} accounts, "
          f"{len(patients)} synthetic patients")
    print_credentials()


def print_credentials() -> None:
    print("\nDemo accounts (synthetic; password for all: " + PASSWORD + ")")
    print(f"  owner           owner@{DOMAIN}")
    for role, _name in STAFF:
        print(f"  {role:<15} {role.replace('_', '')}@{DOMAIN}")


if __name__ == "__main__":
    main()
