"""M7.1: tenant administration, editions & entitlements, plan limits,
read-only subscriptions, role-aware MFA, export/offboarding, support tickets
and the platform console — including proof that the platform flag never
exposes patient data."""
from __future__ import annotations

import io
import itertools
import json
import time
import zipfile
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from app.config import get_settings
from app.security import totp_now
from tests.conftest import (
    APP_PASSWORD,
    PG_HOST,
    PG_PORT,
    PG_SUPERUSER,
    TEST_DB,
    _auth,
    login,
)

PASSWORD = "Str0ngPassphrase!"
_seq = itertools.count(1)


def _su():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_SUPERUSER, dbname=TEST_DB)
    conn.autocommit = True
    return conn


def _sql(stmt, params=()):
    conn = _su()
    with conn.cursor() as cur:
        cur.execute(stmt, params)
        rows = cur.fetchall() if cur.description else None
    conn.close()
    return rows


def _register(client, plan_code=None, prefix="m71"):
    n = next(_seq)
    slug = f"{prefix}-{n}-{int(time.time()) % 100000}"
    body = {"organization_name": slug.title(), "organization_slug": slug,
            "full_name": "Dr. M71 Owner", "email": f"owner@{slug}.example.com",
            "password": PASSWORD}
    if plan_code:
        body["plan_code"] = plan_code
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _patient(client, h, name="M71 Patient"):
    return client.post("/api/v1/patients", json={
        "full_name": name, "phone": f"98{next(_seq):08d}", "gender": "female",
        "date_of_birth": "1990-01-01", "allow_duplicates": True}, headers=h)


def _member(client, h, role, email=None):
    email = email or f"{role}{next(_seq)}@m71.example.com"
    r = client.post("/api/v1/members", json={"email": email, "full_name": f"{role} user",
                                             "password": PASSWORD, "role_key": role},
                    headers=h)
    return r, email


def _platform_admin(client):
    """A super-admin with TOTP enrolled, logged in through the MFA step."""
    org = _register(client, prefix="platform")
    email = org["user"]["email"]
    _sql("UPDATE users SET is_superadmin = true WHERE email = %s", (email,))
    h = _auth(org)
    # until enrolled, a super-admin can only reach account self-service
    assert client.get("/api/v1/platform/overview", headers=h).status_code == 403
    secret = client.post("/api/v1/auth/mfa/totp/setup", headers=h).json()["secret"]
    assert client.post("/api/v1/auth/mfa/totp/enable", json={"code": totp_now(secret)},
                       headers=h).status_code == 200
    challenge = login(client, email=email, password=PASSWORD).json()
    ok = client.post("/api/v1/auth/mfa/verify", json={
        "mfa_token": challenge["mfa_token"], "code": totp_now(secret, time.time() + 30)})
    assert ok.status_code == 200, ok.text
    return ok.json(), {"Authorization": f"Bearer {ok.json()['tokens']['access_token']}"}


# --- editions at registration -------------------------------------------------------
def test_signup_starts_a_trial_on_the_default_edition(client):
    org = _register(client)
    me = client.get("/api/v1/auth/me", headers=_auth(org)).json()
    assert me["edition"]["code"] == "hospital_advanced"
    assert me["subscription_status"] == "trialing"
    assert {"pharmacy", "laboratory", "ipd"} <= set(me["features"])
    sub = client.get("/api/v1/subscription", headers=_auth(org)).json()
    ends = datetime.fromisoformat(sub["trial_ends_at"])
    assert timedelta(days=29) < ends - datetime.now(timezone.utc) <= timedelta(days=30)
    assert sub["usage"]["max_users"] == {"limit": 200, "used": 1}


def test_public_plan_catalogue_has_no_hardcoded_prices(client):
    plans = client.get("/api/v1/plans").json()
    codes = [p["code"] for p in plans]
    assert codes == ["rural_clinic", "clinic_starter", "clinic_plus_ai",
                     "multi_specialty_clinic", "hospital_core", "hospital_advanced"]
    assert all(p["price_monthly_paise"] is None for p in plans)  # set by the platform
    rural = plans[0]
    assert "mobile_offline" in rural["features"] and "pharmacy" not in rural["features"]
    assert rural["limits"]["max_users"] == 3


def test_signup_rejects_unknown_or_private_plans(client):
    for code in ("enterprise", "no_such_plan"):
        r = client.post("/api/v1/auth/register", json={
            "organization_name": "Bad Plan", "organization_slug": f"bad-plan-{next(_seq)}",
            "full_name": "Dr Bad", "email": f"bad{next(_seq)}@x.example.com",
            "password": PASSWORD, "plan_code": code})
        assert r.status_code == 422


# --- feature gating & limits ------------------------------------------------------------
def test_rural_clinic_features_are_enforced_server_side(client):
    org = _register(client, plan_code="rural_clinic")
    h = _auth(org)
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["edition"]["code"] == "rural_clinic"
    assert _patient(client, h).status_code == 201
    assert client.get("/api/v1/opd/queue", headers=h).status_code == 200
    for path in ("/api/v1/pharmacy/stock/alerts", "/api/v1/lab/tests", "/api/v1/ipd/wards",
                 "/api/v1/inventory/items", "/api/v1/expenses"):
        r = client.get(path, headers=h)
        assert r.status_code == 403, path
        assert r.json()["detail"].startswith("Feature not included in your plan")


def test_user_and_branch_limits(client):
    org = _register(client, plan_code="rural_clinic")  # 3 users, 1 branch
    h = _auth(org)
    assert _member(client, h, "doctor")[0].status_code == 201
    inv = client.post("/api/v1/members/invitations",
                      json={"email": f"nurse{next(_seq)}@m71.example.com",
                            "role_key": "nurse"}, headers=h)
    assert inv.status_code == 201  # pending invitation reserves the 3rd seat
    r, _ = _member(client, h, "receptionist")
    assert r.status_code == 403 and "max_users" in r.json()["detail"]
    assert client.post("/api/v1/branches", json={"name": "Main", "code": "MAIN"},
                       headers=h).status_code == 201
    second = client.post("/api/v1/branches", json={"name": "Second", "code": "SEC"},
                         headers=h)
    assert second.status_code == 403 and "max_branches" in second.json()["detail"]


def test_expired_trial_is_read_only_not_locked_out(client):
    org = _register(client)
    h = _auth(org)
    assert _patient(client, h).status_code == 201
    _sql("UPDATE subscriptions SET trial_ends_at = now() - interval '1 minute' "
         "WHERE organization_id = %s", (org["organization"]["id"],))
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["subscription_status"] == "read_only"
    assert client.get("/api/v1/patients", headers=h).status_code == 200      # records stay
    assert client.get("/api/v1/opd/queue", headers=h).status_code == 200
    w = _patient(client, h)
    assert w.status_code == 402 and "trial ended" in w.json()["detail"]
    q = client.post("/api/v1/opd/queue", json={"patient_id": "00000000-0000-0000-0000-"
                                               "000000000000", "branch_id": "00000000-0000-"
                                               "0000-0000-000000000000"}, headers=h)
    assert q.status_code == 402
    # account management, export and support keep working
    assert client.get("/api/v1/subscription", headers=h).status_code == 200
    assert client.post("/api/v1/support/tickets", json={
        "subject": "Renew please", "category": "billing", "body": "Trial ended"},
        headers=h).status_code == 201


def test_tenant_cannot_change_its_own_subscription_in_sql(client):
    org = _register(client, plan_code="rural_clinic")
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user="hms_app",
                            password=APP_PASSWORD, dbname=TEST_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_org_id', %s, true)",
                    (org["organization"]["id"],))
        cur.execute("UPDATE subscriptions SET status = 'active', plan_id = "
                    "(SELECT id FROM plans WHERE code = 'enterprise')")
        assert cur.rowcount == 0  # RLS: only the platform may update
        cur.execute("SELECT count(*) FROM subscriptions")
        assert cur.fetchone()[0] == 1  # and it can read its own
        cur.execute("UPDATE plans SET price_monthly_paise = 0")
        assert cur.rowcount == 0  # the catalogue is read-only for tenants
    conn.rollback()
    conn.close()


# --- role-aware MFA ---------------------------------------------------------------------
def test_role_mfa_policy_blocks_until_enrolled(client):
    org = _register(client)
    h = _auth(org)
    r = client.patch("/api/v1/organization", json={"mfa_required_roles": ["doctor"]},
                     headers=h)
    assert r.status_code == 200 and r.json()["mfa_required_roles"] == ["doctor"]
    assert client.patch("/api/v1/organization", json={"mfa_required_roles": ["wizard"]},
                        headers=h).status_code == 422
    _, email = _member(client, h, "doctor")
    doc = _auth(login(client, email=email, password=PASSWORD).json())
    blocked = client.get("/api/v1/patients", headers=doc)
    assert blocked.status_code == 403 and blocked.json()["detail"] == "mfa_enrollment_required"
    me = client.get("/api/v1/auth/me", headers=doc)
    assert me.status_code == 200 and me.json()["mfa_enrollment_required"] is True
    secret = client.post("/api/v1/auth/mfa/totp/setup", headers=doc).json()["secret"]
    assert client.post("/api/v1/auth/mfa/totp/enable", json={"code": totp_now(secret)},
                       headers=doc).status_code == 200
    assert client.get("/api/v1/patients", headers=doc).status_code == 200
    # other roles are unaffected
    _, nurse_email = _member(client, h, "nurse")
    nurse = _auth(login(client, email=nurse_email, password=PASSWORD).json())
    assert client.get("/api/v1/patients", headers=nurse).status_code == 200


# --- organization profile, branches, onboarding --------------------------------------------
def test_organization_profile_and_onboarding(client):
    org = _register(client)
    h = _auth(org)
    steps = {s["key"]: s["done"] for s in
             client.get("/api/v1/organization/onboarding", headers=h).json()["steps"]}
    assert steps == {"profile": False, "branch": False, "staff": False, "mfa_owner": False,
                     "mfa_policy": False, "edition": True}
    bad = client.patch("/api/v1/organization", json={"gstin": "27ABCDE1234F1Z"}, headers=h)
    assert bad.status_code == 422
    ok = client.patch("/api/v1/organization", json={
        "legal_name": "Sunrise Health Pvt Ltd", "address_line1": "12 Synthetic Road",
        "city": "Pune", "state": "Maharashtra", "pincode": "411038",
        "phone": "+91 20 1234 5678", "gstin": "27ABCDE1234F1Z5", "default_language": "mr"},
        headers=h)
    assert ok.status_code == 200, ok.text
    assert ok.json()["gstin"] == "27ABCDE1234F1Z5" and ok.json()["default_language"] == "mr"
    br = client.post("/api/v1/branches", json={"name": "Kothrud", "code": "KTH",
                                               "gstin": "27ABCDE1234F1Z5"}, headers=h).json()
    upd = client.patch(f"/api/v1/branches/{br['id']}", json={"phone": "020-555-0101",
                                                             "status": "inactive"}, headers=h)
    assert upd.status_code == 200 and upd.json()["status"] == "inactive"
    steps = {s["key"]: s["done"] for s in
             client.get("/api/v1/organization/onboarding", headers=h).json()["steps"]}
    assert steps["profile"] is True
    # read-only roles cannot edit
    _, email = _member(client, h, "nurse")
    nurse = _auth(login(client, email=email, password=PASSWORD).json())
    assert client.patch("/api/v1/organization", json={"city": "X"},
                        headers=nurse).status_code == 403
    other = _register(client)
    assert client.patch(f"/api/v1/branches/{br['id']}", json={"name": "Hijack"},
                        headers=_auth(other)).status_code == 404


def test_export_contains_only_own_tenant_data(client):
    a = _register(client)
    b = _register(client)
    assert _patient(client, _auth(a), "Export Alpha").status_code == 201
    assert _patient(client, _auth(b), "Export Bravo").status_code == 201
    r = client.post("/api/v1/organization/export", headers=_auth(a))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert {"MANIFEST.json", "organization.json", "staff.json",
            "tables/patients.json"} <= names
    patients = json.loads(zf.read("tables/patients.json"))
    assert [p["full_name"] for p in patients] == ["Export Alpha"]
    blob = b"".join(zf.read(n) for n in names)
    assert b"Export Bravo" not in blob and b"password_hash" not in blob
    assert b"scrypt$" not in blob and b"token_hash" not in blob
    _, email = _member(client, _auth(a), "admin")
    admin = _auth(login(client, email=email, password=PASSWORD).json())
    assert client.post("/api/v1/organization/export", headers=admin).status_code == 403


def test_offboarding_request_and_cancel(client):
    org = _register(client)
    h = _auth(org)
    assert client.post("/api/v1/organization/offboarding",
                       json={"password": "wrong-pass", "reason": "Closing"},
                       headers=h).status_code == 401
    r = client.post("/api/v1/organization/offboarding",
                    json={"password": PASSWORD, "reason": "Clinic closing (synthetic)"},
                    headers=h)
    assert r.status_code == 200 and r.json()["offboarding_requested_at"]
    assert client.delete("/api/v1/organization/offboarding",
                         headers=h).json()["offboarding_requested_at"] is None


# --- support -------------------------------------------------------------------------------
def test_support_ticket_flow_and_isolation(client):
    a = _register(client)
    b = _register(client)
    t = client.post("/api/v1/support/tickets", json={
        "subject": "Printer setup", "category": "technical", "priority": "high",
        "body": "How do I print an A5 receipt?"}, headers=_auth(a))
    assert t.status_code == 201 and t.json()["number"].startswith("SUP-")
    tid = t.json()["id"]
    assert client.get(f"/api/v1/support/tickets/{tid}", headers=_auth(b)).status_code == 404
    assert client.get("/api/v1/support/tickets", headers=_auth(b)).json() == []
    rep = client.post(f"/api/v1/support/tickets/{tid}/messages", json={"body": "More info"},
                      headers=_auth(a))
    assert len(rep.json()["messages"]) == 2
    assert client.post(f"/api/v1/support/tickets/{tid}/close",
                       headers=_auth(a)).json()["status"] == "closed"
    assert client.post(f"/api/v1/support/tickets/{tid}/messages", json={"body": "x"},
                       headers=_auth(a)).status_code == 409


def test_plan_change_request_opens_billing_ticket(client):
    org = _register(client)
    r = client.post("/api/v1/subscription/change-request", json={
        "plan_code": "clinic_plus_ai", "billing_cycle": "annual"}, headers=_auth(org))
    assert r.status_code == 201 and r.json()["category"] == "billing"
    assert client.post("/api/v1/subscription/change-request", json={
        "plan_code": "enterprise", "billing_cycle": "annual"},
        headers=_auth(org)).status_code == 422


# --- platform console --------------------------------------------------------------------
def test_platform_requires_super_admin_with_mfa(client):
    org = _register(client)
    assert client.get("/api/v1/platform/overview", headers=_auth(org)).status_code == 403
    me, ph = _platform_admin(client)
    assert client.get("/api/v1/auth/me", headers=ph).json()["is_platform_admin"] is True
    assert client.get("/api/v1/platform/overview", headers=ph).status_code == 200


def test_platform_demo_mode_without_mfa_is_dev_only(client, monkeypatch):
    org = _register(client, prefix="pdemo")
    _sql("UPDATE users SET is_superadmin = true WHERE email = %s", (org["user"]["email"],))
    monkeypatch.setattr(get_settings(), "platform_mfa_required", False)
    assert client.get("/api/v1/platform/overview", headers=_auth(org)).status_code == 200
    from app.config import Settings
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret="p" * 48, field_encryption_key="k",
                 platform_mfa_required=False)


def test_platform_manages_tenants_plans_and_subscriptions(client):
    _, ph = _platform_admin(client)
    tenant = _register(client, plan_code="rural_clinic")
    th = _auth(tenant)
    assert _patient(client, th, "Platform Count Patient").status_code == 201
    tid = tenant["organization"]["id"]

    rows = client.get(f"/api/v1/platform/tenants?q={tenant['organization']['slug']}",
                      headers=ph).json()
    assert len(rows) == 1 and rows[0]["plan_code"] == "rural_clinic"
    assert rows[0]["patients"] == 1 and rows[0]["users"] == 1

    # upgrade the tenant; it sees the new features and the history entry
    r = client.put(f"/api/v1/platform/tenants/{tid}/subscription", json={
        "plan_code": "clinic_starter", "status": "active", "billing_cycle": "annual",
        "limit_overrides": {"max_users": 7}, "reason": "Signed annual contract"},
        headers=ph)
    assert r.status_code == 200, r.text
    assert r.json()["subscription"]["usage"]["max_users"]["limit"] == 7
    me = client.get("/api/v1/auth/me", headers=th).json()
    assert me["edition"]["code"] == "clinic_starter" and "pharmacy" in me["features"]
    assert me["subscription_status"] == "active"
    assert client.get("/api/v1/pharmacy/stock/alerts", headers=th).status_code == 200

    # prices are configured by the platform, then visible in the catalogue
    p = client.patch("/api/v1/platform/plans/clinic_starter",
                     json={"price_monthly_paise": 149900, "price_annual_paise": 1499000},
                     headers=ph)
    assert p.status_code == 200 and p.json()["price_monthly_paise"] == 149900
    public = {x["code"]: x for x in client.get("/api/v1/plans").json()}
    assert public["clinic_starter"]["price_monthly_paise"] == 149900
    ov = client.get("/api/v1/platform/overview", headers=ph).json()
    assert ov["mrr_paise"] >= 1499000 // 12

    # suspension takes effect on the tenant's next request
    s = client.patch(f"/api/v1/platform/tenants/{tid}",
                     json={"status": "suspended", "reason": "Non-payment (synthetic)"},
                     headers=ph)
    assert s.status_code == 200 and s.json()["status"] == "suspended"
    assert client.get("/api/v1/auth/me", headers=th).status_code == 403
    client.patch(f"/api/v1/platform/tenants/{tid}",
                 json={"status": "active", "reason": "Paid"}, headers=ph)
    assert client.get("/api/v1/auth/me", headers=th).status_code == 200

    # non-platform users never reach the console, even owners
    assert client.put(f"/api/v1/platform/tenants/{tid}/subscription", json={
        "plan_code": "enterprise", "status": "active", "reason": "self-upgrade"},
        headers=th).status_code == 403
    # reset the shared catalogue price for other tests
    client.patch("/api/v1/platform/plans/clinic_starter",
                 json={"price_monthly_paise": None, "price_annual_paise": None}, headers=ph)


def test_platform_flag_never_exposes_patient_data(client):
    _, ph = _platform_admin(client)
    tenant = _register(client)
    assert _patient(client, _auth(tenant), "Secret Clinic Patient").status_code == 201
    listing = client.get("/api/v1/patients?q=Secret", headers=ph)
    assert listing.status_code == 200 and listing.json()["total"] == 0
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user="hms_app",
                            password=APP_PASSWORD, dbname=TEST_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.platform_admin', 'true', true)")
        for table in ("patients", "encounters", "prescriptions", "invoices", "lab_results",
                      "admissions", "audit_events"):
            cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
            assert cur.fetchone()[0] == 0, table
        cur.execute("SELECT count(*) FROM subscriptions")
        assert cur.fetchone()[0] > 0  # commercial data IS visible
    conn.rollback()
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.Error):
            cur.execute("SELECT * FROM platform_tenant_overview()")  # flag required
    conn.rollback()
    conn.close()


def test_platform_support_internal_notes_hidden_from_tenant(client):
    _, ph = _platform_admin(client)
    tenant = _register(client)
    th = _auth(tenant)
    tid = client.post("/api/v1/support/tickets", json={
        "subject": "Login help", "category": "account", "body": "Cannot sign in"},
        headers=th).json()["id"]
    queue = client.get("/api/v1/platform/support/tickets?status=open", headers=ph).json()
    assert any(t["id"] == tid and t["organization_name"] for t in queue)
    client.post(f"/api/v1/platform/support/tickets/{tid}/messages",
                json={"body": "Customer seems locked out; check rate limits",
                      "internal": True}, headers=ph)
    reply = client.post(f"/api/v1/platform/support/tickets/{tid}/messages",
                        json={"body": "Please reset your password via the link."},
                        headers=ph)
    assert reply.json()["status"] == "waiting_on_customer"
    tenant_view = client.get(f"/api/v1/support/tickets/{tid}", headers=th).json()
    bodies = [m["body"] for m in tenant_view["messages"]]
    assert "Please reset your password via the link." in bodies
    assert not any("rate limits" in b for b in bodies)
    vendor_view = client.get(f"/api/v1/platform/support/tickets/{tid}", headers=ph).json()
    assert any(m["internal"] for m in vendor_view["messages"])
    upd = client.patch(f"/api/v1/platform/support/tickets/{tid}",
                       json={"status": "resolved", "priority": "high"}, headers=ph)
    assert upd.json()["status"] == "resolved"
    # tenants cannot forge vendor/internal messages in SQL
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user="hms_app",
                            password=APP_PASSWORD, dbname=TEST_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_org_id', %s, true)",
                    (tenant["organization"]["id"],))
        with pytest.raises(psycopg2.Error):
            cur.execute("INSERT INTO support_ticket_messages (ticket_id, organization_id, "
                        "author_side, body, internal) VALUES (%s, %s, 'vendor', 'x', true)",
                        (tid, tenant["organization"]["id"]))
    conn.rollback()
    conn.close()


def test_platform_limits_beds_via_override(client):
    _, ph = _platform_admin(client)
    tenant = _register(client)
    th = _auth(tenant)
    client.put(f"/api/v1/platform/tenants/{tenant['organization']['id']}/subscription", json={
        "plan_code": "hospital_core", "status": "active", "limit_overrides": {"max_beds": 1},
        "reason": "Pilot with one bed"}, headers=ph)
    br = client.post("/api/v1/branches", json={"name": "Main", "code": "MAIN"},
                     headers=th).json()
    ward = client.post("/api/v1/ipd/wards", json={"branch_id": br["id"], "name": "Ward A",
                                                  "code": "WA"}, headers=th).json()
    assert client.post("/api/v1/ipd/beds", json={"ward_id": ward["id"], "label": "A1"},
                       headers=th).status_code == 201
    second = client.post("/api/v1/ipd/beds", json={"ward_id": ward["id"], "label": "A2"},
                         headers=th)
    assert second.status_code == 403 and "max_beds" in second.json()["detail"]


def test_platform_overrides_are_kept_unless_given_and_status_filter(client):
    _, ph = _platform_admin(client)
    tenant = _register(client)
    tid = tenant["organization"]["id"]
    base = {"plan_code": "hospital_core", "status": "active", "reason": "contract"}
    client.put(f"/api/v1/platform/tenants/{tid}/subscription",
               json={**base, "limit_overrides": {"max_users": 77}}, headers=ph)
    again = client.put(f"/api/v1/platform/tenants/{tid}/subscription",
                       json={**base, "billing_cycle": "annual", "reason": "cycle change"},
                       headers=ph).json()
    assert again["limit_overrides"] == {"max_users": 77}  # omitted -> kept
    assert again["subscription"]["usage"]["max_users"]["limit"] == 77
    cleared = client.put(f"/api/v1/platform/tenants/{tid}/subscription",
                         json={**base, "limit_overrides": {}, "reason": "reset"},
                         headers=ph).json()
    assert cleared["limit_overrides"] == {}
    slug = tenant["organization"]["slug"]
    assert [t["slug"] for t in client.get(f"/api/v1/platform/tenants?q={slug}&status=active",
                                          headers=ph).json()] == [slug]
    assert client.get(f"/api/v1/platform/tenants?q={slug}&status=trialing",
                      headers=ph).json() == []
