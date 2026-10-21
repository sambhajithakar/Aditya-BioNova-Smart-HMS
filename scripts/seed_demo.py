"""Seed SYNTHETIC demonstration tenants through the real API.

Every person, phone number and address below is invented. Never point this
at a database holding real patient data; it refuses to run unless
ENVIRONMENT is development or test.

Run from apps/api with the same DATABASE_URL / MIGRATION_DATABASE_URL /
JWT_SECRET as the API:
    python ../../scripts/seed_demo.py            # idempotent: skips seeded tenants

Creates, each on its own commercial edition:
  * Sunrise Demo Clinic        (clinic_plus_ai)    OPD, pharmacy, laboratory
  * BioNova Demo Hospital      (hospital_advanced) + wards, beds, admissions
  * Gram Arogya Rural Clinic   (rural_clinic)      offline-first single doctor
  * Aditya BioNova Platform    platform super-admin for the vendor console
    (the super-admin flag is set with the owner/migration DB role — it can
    never be granted through the API)
With the device simulator enabled (development default), each clinic also
gets two SIMULATED Bluetooth devices and two simulated readings waiting for
clinician review on an open consultation (M8.2).
Prints the demo credentials at the end.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import psycopg2  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo-Sunrise-2026!")
VECTORS = Path(__file__).resolve().parents[1] / "packages" / "contracts" / "device_vectors.json"
# M8.2 SIMULATED Bluetooth devices (never real hardware): kind, label, SIM- id
SIM_DEVICES = [("bp_monitor", "Simulated BP monitor (demo)", "SIM-0000B001"),
               ("pulse_oximeter", "Simulated pulse oximeter (demo)", "SIM-0000A001")]
# synthetic payloads from the shared parser vectors, waiting for review
SIM_READINGS = [("SIM-0000B001", "bp minimal mmHg"), ("SIM-0000A001", "spot minimal")]

TENANTS = [
    # slug, name, plan, domain (reserved example domains), staff roles, modules
    ("sunrise-demo", "Sunrise Demo Clinic", "clinic_plus_ai", "sunrise-demo.example.com",
     ["admin", "doctor", "nurse", "receptionist", "pharmacist", "lab_technician", "billing",
      "auditor"], {"pharmacy", "laboratory"}),
    ("bionova-demo-hospital", "BioNova Demo Hospital", "hospital_advanced",
     "demo-hospital.example.com",
     ["admin", "doctor", "nurse", "receptionist", "pharmacist", "lab_technician", "billing"],
     {"pharmacy", "laboratory", "ipd"}),
    ("gram-arogya-rural", "Gram Arogya Rural Clinic", "rural_clinic",
     "rural-demo.example.com", ["doctor"], set()),
]
PLATFORM = ("aditya-bionova-platform", "Aditya BioNova Platform",
            "platform@aditya-bionova.example.com")

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


def _register(c: TestClient, slug: str, name: str, plan: str, email: str, owner: str):
    return ok(c.post("/api/v1/auth/register", json={
        "organization_name": name, "organization_slug": slug, "full_name": owner,
        "email": email, "password": PASSWORD, "plan_code": plan,
    }), 201, f"register {slug}")


def seed_tenant(c: TestClient, idx: int, slug: str, name: str, plan: str, domain: str,
                roles: list[str], modules: set[str]) -> None:
    reg = _register(c, slug, name, plan, f"owner@{domain}", "Dr. Sameer Owner (demo)")
    h = {"Authorization": f"Bearer {reg['tokens']['access_token']}"}
    ok(c.patch("/api/v1/organization", json={
        "legal_name": f"{name} (synthetic demo)", "address_line1": "1 Synthetic Nagar",
        "city": "Pune", "state": "Maharashtra", "pincode": "411038",
        "phone": "+91 20 0000 0000", "default_language": "mr" if "rural" in slug else "en",
    }, headers=h), 200, "organization profile")
    b = ok(c.post("/api/v1/branches", json={"name": "Main OPD", "code": "MAIN"}, headers=h),
           201, "branch")["id"]

    doctor_id = None
    for role in roles:
        m = ok(c.post("/api/v1/members", json={
            "email": f"{role.replace('_', '')}@{domain}", "full_name": f"{role.title()} (demo)",
            "password": PASSWORD, "role_key": role, "branch_id": b,
        }, headers=h), 201, f"member {role}")
        if role == "doctor":
            doctor_id = m["user_id"]
            ok(c.patch(f"/api/v1/members/{m['membership_id']}",
                       json={"registration_number": f"MMC-DEMO-{1000 + idx}"}, headers=h),
               200, "doctor registration number")

    patients = []
    for i, (pname, gender, dob) in enumerate(PATIENTS):
        patients.append(ok(c.post("/api/v1/patients", json={
            "full_name": pname, "phone": f"9000{idx}{i:05d}", "gender": gender,
            "date_of_birth": dob, "address": "Synthetic Nagar, Pune (demo)",
            "allergies": "Penicillin" if i == 1 else "", "allow_duplicates": True,
        }, headers=h), 201, f"patient {pname}"))

    tomorrow = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) \
        + timedelta(days=1)
    for k, p in enumerate(patients[:3]):
        start = tomorrow + timedelta(hours=k)
        ok(c.post("/api/v1/appointments", json={
            "patient_id": p["id"], "branch_id": b, "provider_user_id": doctor_id,
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=15)).isoformat(),
            "reason": "Follow-up (demo)",
        }, headers=h), 201, "appointment")
    for p in patients[3:6]:
        ok(c.post("/api/v1/opd/queue", json={"patient_id": p["id"], "branch_id": b},
                  headers=h), 201, "queue")

    if get_settings().device_simulator:
        seed_simulated_devices(c, h, b, patients[3]["id"])

    if "ipd" in modules:
        ward = ok(c.post("/api/v1/ipd/wards", json={"branch_id": b, "name": "General Ward",
                                                    "code": "GW1"}, headers=h), 201, "ward")
        icu = ok(c.post("/api/v1/ipd/wards", json={"branch_id": b, "name": "ICU",
                                                   "code": "ICU", "ward_type": "icu"},
                        headers=h), 201, "icu")
        beds = [ok(c.post("/api/v1/ipd/beds", json={"ward_id": ward["id"],
                                                    "label": f"GW1-{n}"}, headers=h),
                   201, "bed") for n in range(1, 9)]
        for n in range(1, 4):
            ok(c.post("/api/v1/ipd/beds", json={"ward_id": icu["id"], "label": f"ICU-{n}"},
                      headers=h), 201, "icu bed")
        ok(c.post("/api/v1/ipd/admissions", json={
            "patient_id": patients[6]["id"], "ward_id": ward["id"], "bed_id": beds[0]["id"],
            "reason": "Community-acquired pneumonia — observation (demo)",
            "attending_user_id": doctor_id,
        }, headers=h), 201, "admission")

    if "pharmacy" in modules:
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

    if "laboratory" in modules:
        tests = ok(c.get("/api/v1/lab/tests", headers=h), 200, "lab tests")
        ok(c.post("/api/v1/lab/orders", json={
            "patient_id": patients[4]["id"], "branch_id": b,
            "test_ids": [t["id"] for t in tests[:2]], "clinical_notes": "Routine check (demo)",
        }, headers=h), 201, "lab order")

    # synthetic OPD billing: a few paid consultations (feeds reports & Copilot)
    for k, p in enumerate(patients[:4]):
        fee = 300 + 100 * k
        inv = ok(c.post("/api/v1/billing/invoices", json={
            "patient_id": p["id"], "branch_id": b,
            "items": [{"item_type": "consultation", "description": "OPD consultation (demo)",
                       "quantity": 1, "unit_price": fee, "tax_rate": 0}],
        }, headers=h), 201, "invoice")
        ok(c.post(f"/api/v1/billing/invoices/{inv['id']}/issue", headers=h), 200, "issue")
        ok(c.post(f"/api/v1/billing/invoices/{inv['id']}/payments",
                  json={"amount": fee, "method": "upi" if k % 2 else "cash"}, headers=h),
           201, "payment")
    if "pharmacy" in modules:  # editions with the expenses module
        for cat, amt in (("supplies", 1200), ("utilities", 2500)):
            ok(c.post("/api/v1/expenses", json={
                "branch_id": b, "category": cat, "amount": amt,
                "expense_date": date.today().isoformat(),
                "description": f"{cat.title()} (synthetic demo)"}, headers=h), 201, "expense")

    ok(c.post("/api/v1/support/tickets", json={
        "subject": "How do I print an A5 receipt? (demo)", "category": "technical",
        "body": "Synthetic demo ticket — no patient data."}, headers=h), 201, "ticket")
    print(f"seed_demo: seeded '{slug}' ({plan}) — {len(roles) + 1} accounts, "
          f"{len(patients)} synthetic patients")


def seed_simulated_devices(c: TestClient, h: dict, branch_id: str, patient_id: str) -> None:
    """Register the two SIMULATED devices and leave two simulated readings
    pending clinician review on an open consultation. Nothing is accepted
    automatically: a clinician accepts or rejects them in the demo."""
    vectors = {v["name"]: v for v in json.loads(VECTORS.read_text())["vectors"]}
    ids = {}
    for kind, label, address in SIM_DEVICES:
        ids[address] = ok(c.post("/api/v1/devices", json={
            "kind": kind, "label": label, "ble_address": address, "is_simulator": True,
        }, headers=h), 201, f"simulated device {address}")["id"]
    enc = ok(c.post("/api/v1/encounters", json={
        "patient_id": patient_id, "branch_id": branch_id,
        "chief_complaint": "Giddiness since morning (demo)",
    }, headers=h), 201, "encounter")
    for address, name in SIM_READINGS:
        v = vectors[name]
        ok(c.post("/api/v1/device-readings", json={
            "capture_id": str(uuid.uuid4()), "device_id": ids[address], "ble_address": address,
            "encounter_id": enc["id"], "characteristic": v["characteristic"],
            "raw_hex": v["hex"], "source": "simulator",
            "captured_at": datetime.now(timezone.utc).isoformat(), "app_version": "seed_demo",
        }, headers=h), 201, f"simulated reading {name}")


def seed_platform(c: TestClient) -> None:
    slug, name, email = PLATFORM
    _register(c, slug, name, "hospital_advanced", email, "Platform Operator (demo)")
    dsn = get_settings().migration_database_url.replace("postgresql+psycopg2://",
                                                         "postgresql://")
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET is_superadmin = true WHERE email = %s", (email,))
    print(f"seed_demo: platform super-admin {email} "
          f"(MFA {'required' if get_settings().platform_mfa_required else 'NOT required — demo'})")


def main() -> None:
    if not get_settings().is_dev:
        sys.exit("seed_demo: refusing to run outside ENVIRONMENT=development|test")
    c = TestClient(app)
    for idx, (slug, name, plan, domain, roles, modules) in enumerate(TENANTS, start=1):
        if c.post("/api/v1/auth/login", json={"email": f"owner@{domain}",
                                              "password": PASSWORD}).status_code == 200:
            print(f"seed_demo: '{slug}' already seeded")
            continue
        seed_tenant(c, idx, slug, name, plan, domain, roles, modules)
    if c.post("/api/v1/auth/login", json={"email": PLATFORM[2],
                                          "password": PASSWORD}).status_code == 200:
        print("seed_demo: platform admin already seeded")
    else:
        seed_platform(c)
    print_credentials()


def print_credentials() -> None:
    print("\nDemo accounts (synthetic; password for all: " + PASSWORD + ")")
    print(f"  platform console  {PLATFORM[2]}")
    for _slug, name, plan, domain, roles, _m in TENANTS:
        print(f"  {name} [{plan}]")
        for role in ["owner", *roles]:
            print(f"    {role:<15} {role.replace('_', '')}@{domain}")


if __name__ == "__main__":
    main()
