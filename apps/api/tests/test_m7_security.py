"""M7.0 security hardening: abuse limits, MFA, passwords, sessions, members,
invitations, PHI-read auditing, error mapping and communications providers.

Each test names the AUDIT_REPORT.md finding it closes where applicable.
"""
from __future__ import annotations

import itertools
import json
import time

import psycopg2
import pytest
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import comms, ratelimit
from app.comms.providers import BrevoEmailProvider, DltSmsProvider, MetaWhatsAppProvider
from app.config import Settings, get_settings
from app.db import get_db
from app.main import app, create_app
from app.security import (
    decrypt_field,
    encrypt_field,
    hash_password,
    totp_now,
    verify_totp,
)
from tests.conftest import (
    APP_PASSWORD,
    PG_HOST,
    PG_PORT,
    PG_SUPERUSER,
    TEST_DB,
    _auth,
    login,
    register_org,
)

PASSWORD = "Str0ngPassphrase!"
_seq = itertools.count(1)


def _su():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_SUPERUSER, dbname=TEST_DB)
    conn.autocommit = True
    return conn


def _fresh_org(client, prefix="sec"):
    n = next(_seq)
    data = register_org(client, slug=f"{prefix}-{n}-{int(time.time()) % 100000}")
    return data


def _outbox_link(client, email, marker):
    rows = client.get("/api/v1/dev/outbox?limit=200").json()
    body = next(m["body"] for m in rows if m["to"] == email and marker in m["body"])
    return body.split(marker)[1].split()[0]


def _audit_actions(org_id):
    conn = _su()
    with conn.cursor() as cur:
        cur.execute("SELECT action, resource_type, resource_id, ip_address, metadata "
                    "FROM audit_events WHERE organization_id = %s ORDER BY id", (org_id,))
        rows = cur.fetchall()
    conn.close()
    return rows


# --- H15: correlation id ------------------------------------------------------
def test_oversized_request_id_is_replaced_not_500(client):
    org = _fresh_org(client)
    h = {**_auth(org), "X-Request-ID": "a" * 200}
    r = client.post("/api/v1/branches", json={"name": "Rid Branch", "code": "RID"}, headers=h)
    assert r.status_code == 201, r.text
    rid = r.headers["X-Request-ID"]
    assert rid != "a" * 200 and len(rid) == 32
    ok = client.get("/api/v1/auth/me", headers={**_auth(org), "X-Request-ID": "trace-123"})
    assert ok.headers["X-Request-ID"] == "trace-123"


# --- H17: configuration --------------------------------------------------------
def test_production_refuses_default_or_short_secrets():
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret="insecure-dev-only-secret-change-me",
                 field_encryption_key="x" * 43)
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret="s" * 20, field_encryption_key="x")
    with pytest.raises(ValueError):  # encryption key required too
        Settings(environment="production", jwt_secret="p" * 48)
    ok = Settings(environment="production", jwt_secret="p" * 48, field_encryption_key="k")
    assert not ok.is_dev


def test_documented_ttl_env_names_are_honoured(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "900")
    monkeypatch.setenv("JWT_REFRESH_TTL_SECONDS", "3600")
    s = Settings()
    assert s.access_token_ttl_seconds == 900
    assert s.refresh_token_ttl_seconds == 3600


# --- H16: rate limiting & lockout -----------------------------------------------
def test_login_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rl_login_per_ip", 3)
    ratelimit.clear("login-ip", "testclient")
    try:
        codes = [login(client, email=f"nobody{i}@x.example.com", password="whatever-pw").status_code
                 for i in range(4)]
        assert codes[:3] == [401, 401, 401]
        assert codes[3] == 429
        r = login(client, email="nobody9@x.example.com", password="whatever-pw")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    finally:
        ratelimit.clear("login-ip", "testclient")


def test_account_lockout_is_enumeration_safe(client):
    org = _fresh_org(client)
    email = org["user"]["email"]
    ghost = f"ghost-{next(_seq)}@nowhere.example.com"
    for target in (email, ghost):
        for _ in range(5):
            assert login(client, email=target, password="wrong-password").status_code == 401
        # locked: even the right password is refused, identically for both
        locked = login(client, email=target, password=PASSWORD)
        assert locked.status_code == 429
        assert locked.json()["detail"] == "Too many attempts. Try again later."
    ratelimit.clear("login-fail", email)
    assert login(client, email=email, password=PASSWORD).status_code == 200
    actions = [a for a, *_ in _audit_actions(org["organization"]["id"])]
    assert "auth.login" in actions


def test_register_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rl_register_per_ip", 1)
    ratelimit.clear("register-ip", "testclient")
    try:
        _fresh_org(client)
        r = client.post("/api/v1/auth/register", json={
            "organization_name": "Too Many", "organization_slug": f"too-many-{next(_seq)}",
            "full_name": "Dr. Spam", "email": f"spam{next(_seq)}@x.example.com",
            "password": PASSWORD,
        })
        assert r.status_code == 429
    finally:
        ratelimit.clear("register-ip", "testclient")


# --- password hashing -------------------------------------------------------------
def test_legacy_password_hash_upgraded_on_login(client):
    import base64
    import hashlib
    import secrets as _s

    org = _fresh_org(client)
    salt = _s.token_bytes(16)
    digest = hashlib.scrypt(PASSWORD.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    legacy = (f"scrypt$16384$8$1${base64.b64encode(salt).decode()}$"
              f"{base64.b64encode(digest).decode()}")
    conn = _su()
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s",
                    (legacy, org["user"]["id"]))
    assert login(client, email=org["user"]["email"], password=PASSWORD).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (org["user"]["id"],))
        upgraded = cur.fetchone()[0]
    conn.close()
    assert upgraded.startswith("scrypt$32768$8$3$")
    assert hash_password("x").startswith("scrypt$32768$8$3$")


# --- MFA ---------------------------------------------------------------------------
def test_totp_matches_rfc6238_vector():
    # RFC 6238 appendix B, SHA-1 seed "12345678901234567890", T=59 -> 94287082
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_now(secret, at=59) == "287082"
    assert verify_totp(secret, "287082", last_step=None, at=59) == 1
    assert verify_totp(secret, "287082", last_step=1, at=59) is None  # replay


def test_field_encryption_round_trip_and_context_binding():
    sealed = encrypt_field("JBSWY3DPEHPK3PXP", context="totp:a")
    assert "JBSWY3DP" not in sealed
    assert decrypt_field(sealed, context="totp:a") == "JBSWY3DPEHPK3PXP"
    with pytest.raises(Exception):
        decrypt_field(sealed, context="totp:b")
    assert encrypt_field("x", context="c") != encrypt_field("x", context="c")  # fresh nonce


def _enable_totp(client, h):
    setup = client.post("/api/v1/auth/mfa/totp/setup", headers=h)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    bad = client.post("/api/v1/auth/mfa/totp/enable", json={"code": "000000"}, headers=h)
    assert bad.status_code == 422
    enabled = client.post("/api/v1/auth/mfa/totp/enable",
                          json={"code": totp_now(secret)}, headers=h)
    assert enabled.status_code == 200, enabled.text
    codes = enabled.json()["recovery_codes"]
    assert len(codes) == 10
    return secret, codes


def test_mfa_enrolment_login_replay_and_recovery(client):
    org = _fresh_org(client)
    email, h = org["user"]["email"], _auth(org)
    assert client.get("/api/v1/auth/mfa/status", headers=h).json() == {
        "totp_enabled": False, "recovery_codes_remaining": 0}
    secret, codes = _enable_totp(client, h)
    assert client.get("/api/v1/auth/mfa/status", headers=h).json()["totp_enabled"] is True

    # seed is encrypted at rest
    conn = _su()
    with conn.cursor() as cur:
        cur.execute("SELECT mfa_totp_secret_enc FROM users WHERE id = %s", (org["user"]["id"],))
        stored = cur.fetchone()[0]
    conn.close()
    assert stored and secret not in stored

    # password alone no longer yields tokens
    first = login(client, email=email, password=PASSWORD)
    assert first.status_code == 200
    challenge = first.json()
    assert challenge["mfa_required"] is True and "tokens" not in challenge

    wrong = client.post("/api/v1/auth/mfa/verify",
                        json={"mfa_token": challenge["mfa_token"], "code": "123456"})
    assert wrong.status_code == 401
    # the enable step consumed the current step; the next step's code is
    # inside the accepted +-1 drift window and has never been used
    code = totp_now(secret, at=time.time() + 30)
    ok = client.post("/api/v1/auth/mfa/verify",
                     json={"mfa_token": challenge["mfa_token"], "code": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["tokens"]["access_token"]

    # replaying the same code is refused
    again = login(client, email=email, password=PASSWORD).json()
    replay = client.post("/api/v1/auth/mfa/verify",
                         json={"mfa_token": again["mfa_token"], "code": code})
    assert replay.status_code == 401

    # recovery code works exactly once
    rec = client.post("/api/v1/auth/mfa/verify",
                      json={"mfa_token": again["mfa_token"], "code": codes[0]})
    assert rec.status_code == 200
    third = login(client, email=email, password=PASSWORD).json()
    reused = client.post("/api/v1/auth/mfa/verify",
                         json={"mfa_token": third["mfa_token"], "code": codes[0]})
    assert reused.status_code == 401
    h2 = {"Authorization": f"Bearer {rec.json()['tokens']['access_token']}"}
    assert client.get("/api/v1/auth/mfa/status", headers=h2).json()[
        "recovery_codes_remaining"] == 9

    # disabling needs password + a second factor
    assert client.post("/api/v1/auth/mfa/disable",
                       json={"password": "nope-nope", "code": codes[1]},
                       headers=h2).status_code == 401
    off = client.post("/api/v1/auth/mfa/disable",
                      json={"password": PASSWORD, "code": codes[1]}, headers=h2)
    assert off.status_code == 200
    plain = login(client, email=email, password=PASSWORD)
    assert "tokens" in plain.json()

    actions = [a for a, *_ in _audit_actions(org["organization"]["id"])]
    for expected in ("auth.mfa_enabled", "auth.mfa_challenge", "auth.mfa_failed",
                     "auth.mfa_disabled"):
        assert expected in actions, expected


def test_mfa_challenge_attempts_are_limited(client, monkeypatch):
    org = _fresh_org(client)
    _enable_totp(client, _auth(org))
    monkeypatch.setattr(get_settings(), "rl_mfa_attempts", 2)
    challenge = login(client, email=org["user"]["email"], password=PASSWORD).json()
    codes = [client.post("/api/v1/auth/mfa/verify",
                         json={"mfa_token": challenge["mfa_token"], "code": "111111"}).status_code
             for _ in range(3)]
    assert codes == [401, 401, 429]


def test_forged_mfa_token_rejected(client):
    r = client.post("/api/v1/auth/mfa/verify",
                    json={"mfa_token": "x" * 40, "code": "123456"})
    assert r.status_code == 401
    org = _fresh_org(client)
    # an access token is not an MFA challenge
    r = client.post("/api/v1/auth/mfa/verify",
                    json={"mfa_token": org["tokens"]["access_token"], "code": "123456"})
    assert r.status_code == 401


# --- passwords ------------------------------------------------------------------------
def test_password_change_revokes_other_sessions(client):
    org = _fresh_org(client)
    email = org["user"]["email"]
    other = login(client, email=email, password=PASSWORD).json()
    h = _auth(org)
    assert client.post("/api/v1/auth/password/change",
                       json={"current_password": "wrong-one", "new_password": "N3wPassphrase!!"},
                       headers=h).status_code == 401
    r = client.post("/api/v1/auth/password/change",
                    json={"current_password": PASSWORD, "new_password": "N3wPassphrase!!"},
                    headers=h)
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200  # current kept
    assert client.get("/api/v1/auth/me", headers=_auth(other)).status_code == 401
    assert login(client, email=email, password=PASSWORD).status_code == 401
    assert login(client, email=email, password="N3wPassphrase!!").status_code == 200


def test_password_reset_flow_is_single_use_and_enumeration_safe(client):
    org = _fresh_org(client)
    email = org["user"]["email"]
    unknown = client.post("/api/v1/auth/password/forgot",
                          json={"email": f"ghost{next(_seq)}@x.example.com"})
    known = client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()

    token = _outbox_link(client, email, "reset-password?token=")
    assert client.post("/api/v1/auth/password/reset",
                       json={"token": token, "new_password": "short"}).status_code == 422
    ok = client.post("/api/v1/auth/password/reset",
                     json={"token": token, "new_password": "R3setPassphrase!"})
    assert ok.status_code == 200
    assert client.post("/api/v1/auth/password/reset",
                       json={"token": token, "new_password": "Another0nePass!"}).status_code == 400
    # every session of the user was revoked
    assert client.get("/api/v1/auth/me", headers=_auth(org)).status_code == 401
    assert login(client, email=email, password="R3setPassphrase!").status_code == 200


def test_password_reset_rate_limited_per_account(client):
    org = _fresh_org(client)
    email = org["user"]["email"]
    codes = [client.post("/api/v1/auth/password/forgot", json={"email": email}).status_code
             for _ in range(4)]
    assert codes == [202, 202, 202, 429]


# --- sessions ---------------------------------------------------------------------------
def test_session_listing_and_revocation(client):
    org = _fresh_org(client)
    email = org["user"]["email"]
    second = login(client, email=email, password=PASSWORD).json()
    h = _auth(org)
    sessions = client.get("/api/v1/auth/sessions", headers=h).json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    other_id = next(s["id"] for s in sessions if not s["current"])
    assert client.post(f"/api/v1/auth/sessions/{other_id}/revoke",
                       headers=h).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_auth(second)).status_code == 401

    third = login(client, email=email, password=PASSWORD).json()
    r = client.post("/api/v1/auth/sessions/revoke-others", headers=h)
    assert r.json()["revoked"] == 1
    assert client.get("/api/v1/auth/me", headers=_auth(third)).status_code == 401

    # someone else's session id is 404
    stranger = _fresh_org(client)
    sid = client.get("/api/v1/auth/sessions", headers=_auth(stranger)).json()[0]["id"]
    assert client.post(f"/api/v1/auth/sessions/{sid}/revoke", headers=h).status_code == 404


def test_absolute_session_lifetime_enforced(client):
    org = _fresh_org(client)
    conn = _su()
    with conn.cursor() as cur:
        cur.execute("UPDATE auth_sessions SET absolute_expires_at = now() - interval '1 second' "
                    "WHERE user_id = %s", (org["user"]["id"],))
    conn.close()
    assert client.get("/api/v1/auth/me", headers=_auth(org)).status_code == 401
    r = client.post("/api/v1/auth/refresh",
                    json={"refresh_token": org["tokens"]["refresh_token"]})
    assert r.status_code == 401


def test_rotation_never_extends_absolute_deadline(client):
    org = _fresh_org(client)
    r = client.post("/api/v1/auth/refresh",
                    json={"refresh_token": org["tokens"]["refresh_token"]})
    assert r.status_code == 200
    conn = _su()
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT absolute_expires_at FROM auth_sessions WHERE user_id = %s",
                    (org["user"]["id"],))
        deadlines = cur.fetchall()
    conn.close()
    assert len(deadlines) == 1


def test_suspended_organization_loses_access_immediately(client):
    org = _fresh_org(client)
    h = _auth(org)
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    conn = _su()
    with conn.cursor() as cur:
        cur.execute("UPDATE organizations SET status = 'suspended' WHERE id = %s",
                    (org["organization"]["id"],))
    try:
        assert client.get("/api/v1/auth/me", headers=h).status_code == 403
        assert client.post("/api/v1/auth/refresh",
                           json={"refresh_token": org["tokens"]["refresh_token"]}
                           ).status_code == 403
    finally:
        with conn.cursor() as cur:
            cur.execute("UPDATE organizations SET status = 'active' WHERE id = %s",
                        (org["organization"]["id"],))
        conn.close()


# --- H14: members & invitations ---------------------------------------------------------
def test_admin_cannot_attach_another_tenants_account(client):
    a = _fresh_org(client)
    b = _fresh_org(client)
    victim = b["user"]["email"]
    r = client.post("/api/v1/members", json={
        "email": victim, "full_name": "Attacker Chosen", "password": "whatever-123456",
        "role_key": "receptionist"}, headers=_auth(a))
    assert r.status_code == 409
    assert "Dr. Test Owner" not in r.text  # victim's identity not disclosed
    members = client.get("/api/v1/members", headers=_auth(a)).json()
    assert victim not in [m["email"] for m in members]
    # the victim's own login is unaffected (no forced multi-org ambiguity)
    assert login(client, email=victim, password=PASSWORD).status_code == 200


def test_member_suspend_role_change_and_guards(client):
    org = _fresh_org(client)
    h = _auth(org)
    email = f"nurse{next(_seq)}@staff.example.com"
    created = client.post("/api/v1/members", json={
        "email": email, "full_name": "Nurse Synthetic", "password": PASSWORD,
        "role_key": "nurse"}, headers=h)
    assert created.status_code == 201
    mid = created.json()["membership_id"]
    staff = login(client, email=email, password=PASSWORD).json()
    sh = _auth(staff)
    assert client.get("/api/v1/auth/me", headers=sh).json()["role"] == "nurse"

    role = client.patch(f"/api/v1/members/{mid}", json={"role_key": "doctor"}, headers=h)
    assert role.status_code == 200 and role.json()["role_key"] == "doctor"
    assert client.get("/api/v1/auth/me", headers=sh).json()["role"] == "doctor"

    sus = client.patch(f"/api/v1/members/{mid}", json={"status": "suspended"}, headers=h)
    assert sus.status_code == 200 and sus.json()["status"] == "suspended"
    assert client.get("/api/v1/auth/me", headers=sh).status_code == 401
    assert login(client, email=email, password=PASSWORD).status_code == 403

    client.patch(f"/api/v1/members/{mid}", json={"status": "active"}, headers=h)
    assert login(client, email=email, password=PASSWORD).status_code == 200

    owner_mid = next(m["membership_id"] for m in client.get("/api/v1/members", headers=h).json()
                     if m["role_key"] == "owner")
    assert client.patch(f"/api/v1/members/{owner_mid}", json={"status": "suspended"},
                        headers=h).status_code == 403
    assert client.patch(f"/api/v1/members/{mid}", json={"role_key": "owner"},
                        headers=h).status_code == 403
    # another tenant cannot touch this member
    other = _fresh_org(client)
    assert client.patch(f"/api/v1/members/{mid}", json={"status": "suspended"},
                        headers=_auth(other)).status_code == 404
    assert client.post(f"/api/v1/members/{mid}/sessions/revoke",
                       headers=h).status_code == 200


def test_invitation_new_user_and_revocation(client):
    org = _fresh_org(client)
    h = _auth(org)
    email = f"invitee{next(_seq)}@staff.example.com"
    inv = client.post("/api/v1/members/invitations",
                      json={"email": email, "role_key": "pharmacist"}, headers=h)
    assert inv.status_code == 201 and inv.json()["status"] == "pending"
    token = _outbox_link(client, email, "accept-invite?token=")
    assert client.post("/api/v1/auth/invitations/accept",
                       json={"token": token, "password": PASSWORD}).status_code == 422
    ok = client.post("/api/v1/auth/invitations/accept",
                     json={"token": token, "password": PASSWORD, "full_name": "Pharm Synthetic"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["role"] == "pharmacist"
    assert ok.json()["organization"]["id"] == org["organization"]["id"]
    # single use
    assert client.post("/api/v1/auth/invitations/accept",
                       json={"token": token, "password": PASSWORD,
                             "full_name": "Again"}).status_code == 400

    # a revoked invitation cannot be used
    email2 = f"invitee{next(_seq)}@staff.example.com"
    inv2 = client.post("/api/v1/members/invitations",
                       json={"email": email2, "role_key": "nurse"}, headers=h).json()
    token2 = _outbox_link(client, email2, "accept-invite?token=")
    assert client.post(f"/api/v1/members/invitations/{inv2['id']}/revoke",
                       headers=h).json()["status"] == "revoked"
    assert client.post("/api/v1/auth/invitations/accept",
                       json={"token": token2, "password": PASSWORD,
                             "full_name": "Too Late"}).status_code == 400
    listed = client.get("/api/v1/members/invitations", headers=h).json()
    assert {i["status"] for i in listed} == {"accepted", "revoked"}


def test_invitation_existing_account_needs_its_own_password(client):
    org = _fresh_org(client)
    existing = _fresh_org(client)
    email = existing["user"]["email"]
    client.post("/api/v1/members/invitations",
                json={"email": email, "role_key": "doctor"}, headers=_auth(org))
    token = _outbox_link(client, email, "accept-invite?token=")
    assert client.post("/api/v1/auth/invitations/accept",
                       json={"token": token, "password": "guessed-password"}).status_code == 401
    ok = client.post("/api/v1/auth/invitations/accept",
                     json={"token": token, "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["role"] == "doctor"


def test_invitations_are_tenant_isolated_at_db_level(client):
    org = _fresh_org(client)
    client.post("/api/v1/members/invitations",
                json={"email": f"iso{next(_seq)}@x.example.com", "role_key": "nurse"},
                headers=_auth(org))
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user="hms_app",
                            password=APP_PASSWORD, dbname=TEST_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM member_invitations")
        assert cur.fetchone()[0] == 0  # no tenant context -> nothing visible
    conn.close()


# --- H18: PHI reads are audited -------------------------------------------------------------
def test_phi_reads_are_audited_without_query_strings(client):
    org = _fresh_org(client)
    h = _auth(org)
    p = client.post("/api/v1/patients", json={
        "full_name": "Audit Readpatient", "phone": "9876500001", "gender": "female",
        "date_of_birth": "1990-05-05", "allow_duplicates": True}, headers=h).json()
    assert client.get(f"/api/v1/patients/{p['id']}", headers=h).status_code == 200
    assert client.get("/api/v1/patients?q=Readpatient", headers=h).status_code == 200
    reads = [r for r in _audit_actions(org["organization"]["id"]) if r[0] == "phi.read"]
    assert any(r[1] == "patients" and r[2] == p["id"] for r in reads)
    for r in reads:
        assert "Readpatient" not in json.dumps(r[4])


def test_forwarded_for_ignored_from_untrusted_peer(client):
    org = _fresh_org(client)
    client.get("/api/v1/auth/me", headers=_auth(org))
    client.post("/api/v1/auth/logout",
                headers={**_auth(org), "X-Forwarded-For": "203.0.113.9"})
    rows = [r for r in _audit_actions(org["organization"]["id"]) if r[0] == "auth.logout"]
    assert rows and rows[-1][3] == "testclient"


def test_audit_function_rejects_tenant_events_without_context(client):
    org = _fresh_org(client)
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user="hms_app",
                            password=APP_PASSWORD, dbname=TEST_DB)
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.Error):
            cur.execute("SELECT insert_audit_event(%s, NULL, 'forged', NULL, NULL, "
                        "'{}'::jsonb, NULL, NULL)", (org["organization"]["id"],))
    conn.rollback()
    with conn.cursor() as cur:  # system (org-NULL) events still allowed
        cur.execute("SELECT insert_audit_event(NULL, NULL, 'system.probe', NULL, NULL, "
                    "'{}'::jsonb, NULL, NULL)")
    conn.rollback()
    conn.close()


# --- error handling & transaction ordering ------------------------------------------------
def test_commit_happens_before_the_response(client):
    """A failing commit must surface as an error, never as a 2xx."""
    def boom_db(db=Depends(get_db, scope="function")):
        def fail():
            raise RuntimeError("commit failed")
        db.commit = fail
        return db

    app.add_api_route("/api/v1/_probe_commit", lambda db=Depends(boom_db): {"ok": True})
    try:
        local = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(
            app, raise_server_exceptions=False)
        r = local.get("/api/v1/_probe_commit")
        assert r.status_code == 500
    finally:
        app.router.routes.pop()


def test_db_trigger_and_constraint_errors_map_to_client_errors(client):
    class Orig(Exception):
        def __init__(self, pgcode, msg):
            super().__init__(msg)
            self.pgcode = pgcode

            class Diag:
                message_primary = msg
            self.diag = Diag()

    def raiser(code, msg):
        def route():
            raise DBAPIError("stmt", {}, Orig(code, msg))
        return route

    cases = [("P0001", "signed prescription is immutable", 409),
             ("23505", "dup", 409), ("23514", "chk", 422), ("XX000", "boom", 500)]
    for code, msg, expected in cases:
        app.add_api_route(f"/api/v1/_probe_{code}", raiser(code, msg))
    try:
        local = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(
            app, raise_server_exceptions=False)
        for code, msg, expected in cases:
            r = local.get(f"/api/v1/_probe_{code}")
            assert r.status_code == expected, (code, r.text)
            if code == "P0001":
                assert r.json()["detail"] == msg
            if expected == 500:
                assert msg not in r.text
    finally:
        del app.router.routes[-len(cases):]


def test_dev_outbox_not_mounted_outside_development(monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    paths = create_app().openapi()["paths"]
    assert "/api/v1/dev/outbox" not in paths
    assert "/api/v1/auth/login" in paths
    monkeypatch.setattr(get_settings(), "environment", "test")
    assert "/api/v1/dev/outbox" in create_app().openapi()["paths"]


# --- communications providers ------------------------------------------------------------------
class _FakeHttp:
    def __init__(self, status=201, body=b'{"messageId": "m-1"}'):
        self.calls = []
        self.status, self.body = status, body

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, json.loads(body)))
        return self.status, self.body


def test_brevo_request_shape():
    s = Settings(brevo_api_key="test-key", comms_email_from="clinic@example.invalid")
    http = _FakeHttp()
    res = BrevoEmailProvider(http).send(
        comms.Message(channel="email", to="p@example.invalid", subject="Hi", body="Body"), s)
    url, headers, payload = http.calls[0]
    assert url == "https://api.brevo.com/v3/smtp/email"
    assert headers["api-key"] == "test-key"
    assert payload["to"] == [{"email": "p@example.invalid"}] and payload["subject"] == "Hi"
    assert res.status == "sent" and res.provider_message_id == "m-1"


def test_whatsapp_and_dlt_sms_require_templates():
    s = Settings(whatsapp_phone_number_id="123", whatsapp_access_token="tok",
                 sms_dlt_endpoint="https://sms.example.invalid/send", sms_dlt_api_key="k",
                 sms_dlt_sender_id="ABCHMS", sms_dlt_entity_id="1101")
    msg = comms.Message(channel="whatsapp", to="919800000000", body="x")
    with pytest.raises(ValueError):
        MetaWhatsAppProvider(_FakeHttp()).build(msg, s)
    http = _FakeHttp(200, b'{"messages": [{"id": "wamid.1"}]}')
    res = MetaWhatsAppProvider(http).send(
        comms.Message(channel="whatsapp", to="919800000000", body="x",
                      template="appointment_reminder", variables=["Asha", "10:30"]), s)
    url, headers, payload = http.calls[0]
    assert url == "https://graph.facebook.com/v21.0/123/messages"
    assert payload["template"]["name"] == "appointment_reminder"
    assert [p["text"] for p in payload["template"]["components"][0]["parameters"]] == [
        "Asha", "10:30"]
    assert res.provider_message_id == "wamid.1"

    sms_http = _FakeHttp(200, b"{}")
    DltSmsProvider(sms_http).send(
        comms.Message(channel="sms", to="919800000000", body="OTP 1234",
                      template="1107000000000000001", variables=["1234"]), s)
    _url, _h, sms = sms_http.calls[0]
    assert sms["template_id"] == "1107000000000000001" and sms["entity_id"] == "1101"


def test_live_providers_are_suppressed_until_enabled(client):
    s = Settings(comms_email_provider="brevo", brevo_api_key="k", comms_live_enabled=False)
    res = comms.send(comms.Message(channel="email", to="gate@example.invalid",
                                   subject="Gate", body="should not leave"), s)
    assert res.status == "suppressed"
    rows = client.get("/api/v1/dev/outbox?limit=50").json()
    assert any(r["to"] == "gate@example.invalid" and r["status"] == "suppressed" for r in rows)


def test_sensitive_bodies_redacted_outside_development():
    s = Settings(environment="production", jwt_secret="p" * 48, field_encryption_key="k")
    comms.send(comms.Message(channel="email", to="redact@example.invalid", subject="Reset",
                             body="link https://x/reset?token=SECRET", sensitive=True), s)
    conn = _su()
    with conn.cursor() as cur:
        cur.execute("SELECT body FROM comms_messages WHERE recipient = 'redact@example.invalid'")
        body = cur.fetchone()[0]
    conn.close()
    assert "SECRET" not in body


def test_comms_outbox_is_append_only_for_app_role(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        with pytest.raises(Exception):
            db.execute(text("DELETE FROM comms_messages"))
    finally:
        db.rollback()
        db.close()
