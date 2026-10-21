"""Communications v2 + follow-up CRM. Synthetic data only; every send goes to
the mock provider (dev outbox) — nothing is ever delivered to anyone."""
from __future__ import annotations

import itertools
import json
import time
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from app.comms import engine
from app.comms import templates as tpl
from tests.conftest import APP_PASSWORD, PG_HOST, PG_PORT, PG_SUPERUSER, TEST_DB, _auth
from tests.test_m3_clinical_billing import _patient

PASSWORD = "Str0ngPassphrase!"
IST = timezone(timedelta(hours=5, minutes=30))
_seq = itertools.count(1)
API = "/api/v1"


# --------------------------------------------------------------------- helpers
def _clinic(client, plan="hospital_advanced"):
    slug = f"cm-{next(_seq)}-{int(time.time() * 1000) % 10**7}"
    r = client.post(f"{API}/auth/register", json={
        "organization_name": slug.title(), "organization_slug": slug,
        "full_name": "Dr Comms Owner", "email": f"owner@{slug}.example.com",
        "password": PASSWORD, "plan_code": plan})
    assert r.status_code == 201, r.text
    org = r.json()
    h = _auth(org)
    br = client.post(f"{API}/branches", json={"name": "Main", "code": "MAIN"}, headers=h)
    assert br.status_code == 201, br.text
    return {"org": org, "h": h, "branch": br.json(), "slug": slug}


def _member(client, c, role):
    email = f"{role}{next(_seq)}@{c['slug']}.example.com"
    r = client.post(f"{API}/members", json={"email": email, "full_name": f"Staff {role}",
                                            "password": PASSWORD, "role_key": role},
                    headers=c["h"])
    assert r.status_code == 201, r.text
    login = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return _auth(login.json())


def _appt(client, c, patient, starts_at, minutes=15, provider=None):
    body = {"patient_id": patient["id"], "branch_id": c["branch"]["id"],
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(minutes=minutes)).isoformat()}
    if provider:
        body["provider_user_id"] = provider
    r = client.post(f"{API}/appointments", json=body, headers=c["h"])
    assert r.status_code == 201, r.text
    return r.json()


def _consent(client, c, patient, channel="sms", status="opted_in", source="registration_form"):
    return client.put(f"{API}/comms/patients/{patient['id']}/consent",
                      json={"channel": channel, "status": status, "source": source},
                      headers=c["h"])


def _run(client, h, **kw):
    r = client.post(f"{API}/comms/reminders/run", json=kw, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _log(client, h, **params):
    r = client.get(f"{API}/comms/delivery-log", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _daytime():
    """Tomorrow 10:00 IST — always in the future and outside quiet hours."""
    d = (datetime.now(IST) + timedelta(days=1)).date()
    return datetime(d.year, d.month, d.day, 10, 0, tzinfo=IST)


@pytest.fixture
def clock(monkeypatch):
    state = {"now": _daytime()}
    monkeypatch.setattr(engine, "utcnow", lambda: state["now"].astimezone(timezone.utc))
    return state


def _su():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_SUPERUSER, dbname=TEST_DB)
    conn.autocommit = True
    return conn


def _set_limits(org_id, limits):
    conn = _su()
    with conn.cursor() as cur:
        cur.execute("UPDATE subscriptions SET limit_overrides = %s WHERE organization_id = %s",
                    (json.dumps(limits), org_id))
    conn.close()


# --------------------------------------------------------------------- templates
def test_placeholder_whitelist_unit():
    assert tpl.validate_template("sms", "Hi {patient_first_name} at {clinic_name}") == []
    errs = tpl.validate_template("sms", "Your {diagnosis} and {medicines}")
    assert len(errs) == 2 and all("not allowed" in e for e in errs)
    assert "unknown placeholder" in tpl.validate_template("sms", "Hi {nickname}")[0]
    assert "unbalanced" in tpl.validate_template("sms", "Hi {patient_first_name")[0]
    assert tpl.validate_template("email", "ok", "About your {lab_result}")
    assert tpl.render("Hi {patient_first_name}", {"patient_first_name": "Asha"}) == "Hi Asha"
    # every seeded default is itself valid
    for channel, d, body in tpl.default_templates():
        assert tpl.validate_template(channel, body, d.subject if channel == "email" else "") == []
    assert engine.mask_recipient("sms", "9876543210") == "******3210"
    assert engine.mask_recipient("email", "asha@example.com") == "a***@example.com"
    assert engine.in_quiet_hours(datetime(2026, 1, 1, 22, 0), 21, 8)
    assert engine.in_quiet_hours(datetime(2026, 1, 1, 7, 59), 21, 8)
    assert not engine.in_quiet_hours(datetime(2026, 1, 1, 8, 0), 21, 8)
    assert engine.first_name("Dr. Asha Patil") == "Asha"


def test_default_templates_seeded_lazily_in_three_languages(client):
    c = _clinic(client)
    rows = client.get(f"{API}/comms/templates", headers=c["h"]).json()
    assert len(rows) == 27  # 3 channels x 3 purposes x 3 languages
    assert {r["language"] for r in rows} == {"en", "mr", "hi"}
    mr = next(r for r in rows if r["language"] == "mr" and r["channel"] == "sms"
              and r["purpose"] == "appointment_reminder")
    assert "नमस्कार" in mr["body"] and "{appointment_time}" in mr["body"]
    # second call does not seed again
    assert len(client.get(f"{API}/comms/templates", headers=c["h"]).json()) == 27


def test_template_validation_rejects_clinical_placeholders(client):
    c = _clinic(client)
    base = {"channel": "sms", "purpose": "appointment_reminder", "language": "en",
            "name": "Custom"}
    bad = client.post(f"{API}/comms/templates", headers=c["h"],
                      json={**base, "body": "Hi {patient_first_name}, about your {diagnosis}"})
    assert bad.status_code == 422 and "not allowed" in bad.json()["detail"]
    unknown = client.post(f"{API}/comms/templates", headers=c["h"],
                          json={**base, "body": "Hi {first}"})
    assert unknown.status_code == 422 and "unknown placeholder" in unknown.json()["detail"]
    dlt = client.post(f"{API}/comms/templates", headers=c["h"],
                      json={**base, "body": "Hi", "dlt_template_id": "abc"})
    assert dlt.status_code == 422
    ok = client.post(f"{API}/comms/templates", headers=c["h"], json={
        **base, "body": "Hi {patient_first_name}, see you {appointment_date} {appointment_time}",
        "dlt_template_id": "1107160000000000001"})
    assert ok.status_code == 201, ok.text
    assert ok.json()["placeholders"] == ["appointment_date", "appointment_time",
                                         "patient_first_name"]
    active = client.get(f"{API}/comms/templates", params={
        "channel": "sms", "purpose": "appointment_reminder", "language": "en"},
        headers=c["h"]).json()
    assert [t["id"] for t in active] == [ok.json()["id"]]  # replaced the default
    patch = client.patch(f"{API}/comms/templates/{ok.json()['id']}", headers=c["h"],
                         json={"body": "Your {lab_result} is ready"})
    assert patch.status_code == 422
    prev = client.post(f"{API}/comms/templates/preview", headers=c["h"], json={
        "channel": "sms", "body": "Hi {patient_first_name} at {clinic_name} {notes}"})
    assert prev.status_code == 200
    assert prev.json()["body"].startswith("Hi Asha at Demo Clinic")
    assert prev.json()["errors"] and prev.json()["sms_segments"] == 1


# --------------------------------------------------------------------- consent
def test_consent_is_required_and_opt_out_always_wins(client, clock):
    c = _clinic(client)
    p = _patient(client, c["h"])
    _appt(client, c, p, clock["now"] + timedelta(hours=2))
    run = _run(client, c["h"])
    assert run["by_status"] == {"skipped_no_consent": 1} and run["sent"] == 0
    assert "mock outbox — not sent" in run["mock_notice"]

    assert _consent(client, c, p).status_code == 200
    run = _run(client, c["h"])
    assert run["by_status"] == {"sent_mock": 1}
    logs = _log(client, c["h"], status="sent_mock")
    assert logs[0]["recipient_masked"] == "******" + p["phone"][-4:]
    assert logs[0]["provider"] == "mock" and logs[0]["cost_paise"] == 0

    out = client.post(f"{API}/comms/patients/{p['id']}/opt-out", json={}, headers=c["h"])
    assert out.status_code == 200
    assert {x["status"] for x in out.json()["consents"]} == {"opted_out"}
    # staff cannot silently re-subscribe; a registration form cannot either
    for src in ("staff_update", "registration_form"):
        assert _consent(client, c, p, source=src).status_code == 409
    _appt(client, c, p, clock["now"] + timedelta(hours=5))
    # first appointment: already reminded; the new one: blocked by the opt-out
    assert _run(client, c["h"])["by_status"] == {"duplicate": 1, "skipped_no_consent": 1}
    # only the patient's own request opts back in
    again = _consent(client, c, p, source="patient_request")
    assert again.status_code == 200
    assert [h["status"] for h in again.json()["history"]][:3] == [
        "opted_in", "opted_out", "opted_out"]


def test_quiet_hours_block_sending_then_retry_later(client, clock):
    c = _clinic(client)
    p = _patient(client, c["h"])
    _consent(client, c, p)
    day = clock["now"]
    _appt(client, c, p, day + timedelta(hours=2))  # tomorrow 12:00 IST
    clock["now"] = (day - timedelta(days=1)).replace(hour=22, minute=30)  # evening before
    night = _run(client, c["h"])
    assert night["quiet_hours"] is True
    assert night["by_status"] == {"skipped_quiet_hours": 1}
    clock["now"] = day.replace(hour=7, minute=45)  # still quiet
    assert _run(client, c["h"])["by_status"] == {"skipped_quiet_hours": 1}
    assert len(_log(client, c["h"], status="skipped_quiet_hours")) == 1  # not re-logged
    clock["now"] = day.replace(hour=8, minute=5)
    assert _run(client, c["h"])["by_status"] == {"sent_mock": 1}


def test_quota_exhaustion_is_skipped_quota_never_silent(client, clock):
    c = _clinic(client)
    _set_limits(c["org"]["organization"]["id"], {"sms_monthly": 1})
    pts = [_patient(client, c["h"]) for _ in range(2)]
    for i, p in enumerate(pts):
        _consent(client, c, p)
        _appt(client, c, p, clock["now"] + timedelta(hours=1 + i))
    run = _run(client, c["h"])
    assert run["by_status"] == {"sent_mock": 1, "skipped_quota": 1}
    skipped = _log(client, c["h"], status="skipped_quota")
    assert "sms_monthly" in skipped[0]["error"]
    ov = client.get(f"{API}/comms/overview", headers=c["h"]).json()
    sms = next(ch for ch in ov["channels"] if ch["channel"] == "sms")
    assert sms["used"] == 1 and sms["limit"] == 1 and sms["mock"] is True
    assert "not sent" in ov["mock_notice"]


def test_spend_cap_blocks_sending(client, clock, monkeypatch):
    monkeypatch.setenv("COMMS_COST_PAISE_SMS", "40")
    c = _clinic(client)
    r = client.put(f"{API}/comms/settings", headers=c["h"], json={
        "monthly_spend_cap_paise": 60, "quiet_start_hour": 21, "quiet_end_hour": 8,
        "reminder_hours_ahead": 24, "reminder_channels": ["sms"]})
    assert r.status_code == 200, r.text
    for i in range(2):
        p = _patient(client, c["h"])
        _consent(client, c, p)
        _appt(client, c, p, clock["now"] + timedelta(hours=1 + i))
    run = _run(client, c["h"])
    assert run["by_status"] == {"sent_mock": 1, "skipped_quota": 1}
    assert _log(client, c["h"], status="skipped_quota")[0]["error"] == "monthly spend cap reached"
    ov = client.get(f"{API}/comms/overview", headers=c["h"]).json()
    assert ov["spend_paise"] == 40 and ov["spend_cap_paise"] == 60


def test_reminder_run_is_idempotent(client, clock):
    c = _clinic(client)
    p = _patient(client, c["h"])
    _consent(client, c, p)
    _consent(client, c, p, channel="whatsapp")
    client.put(f"{API}/comms/settings", headers=c["h"], json={
        "reminder_channels": ["sms", "whatsapp"]})
    a = _appt(client, c, p, clock["now"] + timedelta(hours=3))
    first = _run(client, c["h"])
    second = _run(client, c["h"])
    assert first["by_status"] == {"sent_mock": 2}
    assert second["by_status"] == {"duplicate": 2} and second["sent"] == 0
    sent = _log(client, c["h"], appointment_id=a["id"])
    assert sorted(x["channel"] for x in sent) == ["sms", "whatsapp"]
    # rescheduling opens a new reminder window
    client.patch(f"{API}/appointments/{a['id']}", headers=c["h"], json={
        "starts_at": (clock["now"] + timedelta(hours=6)).isoformat(),
        "ends_at": (clock["now"] + timedelta(hours=6, minutes=15)).isoformat()})
    assert _run(client, c["h"])["by_status"] == {"sent_mock": 2}
    # appointments outside the window are not touched
    _appt(client, c, p, clock["now"] + timedelta(hours=30))
    assert _run(client, c["h"])["appointments"] == 1


def test_replacing_a_template_does_not_resend_reminders(client, clock):
    """M8.1 (M4): the dedupe key no longer contains the template id."""
    c = _clinic(client)
    p = _patient(client, c["h"])
    _consent(client, c, p)
    a = _appt(client, c, p, clock["now"] + timedelta(hours=3))
    assert _run(client, c["h"])["by_status"] == {"sent_mock": 1}
    r = client.post(f"{API}/comms/templates", headers=c["h"], json={
        "channel": "sms", "purpose": "appointment_reminder", "language": "en",
        "name": "Reworded", "is_active": True,
        "body": "Reminder: {clinic_name} at {appointment_time}. Reply STOP to opt out."})
    assert r.status_code == 201, r.text
    again = _run(client, c["h"])
    assert again["by_status"] == {"duplicate": 1} and again["sent"] == 0
    assert len(_log(client, c["h"], appointment_id=a["id"])) == 1


def test_delivery_log_is_append_only_and_tenant_isolated(client, clock):
    a = _clinic(client)
    b = _clinic(client)
    p = _patient(client, a["h"])
    _consent(client, a, p)
    _appt(client, a, p, clock["now"] + timedelta(hours=2))
    _run(client, a["h"])
    a_id, b_id = a["org"]["organization"]["id"], b["org"]["organization"]["id"]
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user="hms_app",
                            password=APP_PASSWORD, dbname=TEST_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_org_id', %s, true)", (b_id,))
        for table in ("comms_delivery_log", "comms_templates", "comms_consents"):
            cur.execute(f"SELECT count(*) FROM {table}")
            assert cur.fetchone()[0] == 0, table
        cur.execute("SELECT set_config('app.current_org_id', %s, true)", (a_id,))
        cur.execute("SELECT count(*) FROM comms_delivery_log")
        assert cur.fetchone()[0] == 1
        for stmt in ("UPDATE comms_delivery_log SET status = 'failed'",
                     "DELETE FROM comms_delivery_log",
                     "UPDATE comms_consent_events SET status = 'opted_in'",
                     "DELETE FROM comms_consent_events",
                     "DELETE FROM comms_templates"):
            cur.execute("SAVEPOINT s")
            with pytest.raises(psycopg2.Error):
                cur.execute(stmt)
            cur.execute("ROLLBACK TO SAVEPOINT s")
        # a forged row for another tenant is refused by RLS
        cur.execute("SAVEPOINT s")
        with pytest.raises(psycopg2.Error):
            cur.execute("INSERT INTO comms_delivery_log (organization_id, channel, purpose, "
                        "provider, status, period) VALUES (%s,'sms','generic','mock',"
                        "'sent_mock','2026-01')", (b_id,))
        cur.execute("ROLLBACK TO SAVEPOINT s")
    conn.rollback()
    conn.close()
    # the trigger holds even for the table owner
    su = _su()
    with su.cursor() as cur, pytest.raises(psycopg2.Error):
        cur.execute("UPDATE comms_delivery_log SET cost_paise = 1 WHERE organization_id = %s",
                    (a_id,))
    su.close()


def test_tenant_isolation_over_the_api(client, clock):
    a = _clinic(client)
    b = _clinic(client)
    pa = _patient(client, a["h"])
    tpl_a = client.get(f"{API}/comms/templates", headers=a["h"]).json()[0]
    tpl_b_ids = {t["id"] for t in client.get(f"{API}/comms/templates", headers=b["h"]).json()}
    assert tpl_a["id"] not in tpl_b_ids
    assert client.patch(f"{API}/comms/templates/{tpl_a['id']}", headers=b["h"],
                        json={"name": "Hijack"}).status_code == 404
    fu = client.post(f"{API}/follow-ups", headers=a["h"], json={
        "patient_id": pa["id"], "due_date": str(clock["now"].date()), "reason": "Review visit"})
    assert fu.status_code == 201, fu.text
    assert client.get(f"{API}/follow-ups/{fu.json()['id']}", headers=b["h"]).status_code == 404
    assert client.post(f"{API}/follow-ups/{fu.json()['id']}/complete", json={},
                       headers=b["h"]).status_code == 404
    assert client.get(f"{API}/follow-ups", headers=b["h"]).json() == []
    assert client.get(f"{API}/comms/patients/{pa['id']}", headers=b["h"]).status_code == 404
    assert _consent(client, b, pa).status_code == 404
    assert client.post(f"{API}/follow-ups", headers=b["h"], json={
        "patient_id": pa["id"], "due_date": str(clock["now"].date()),
        "reason": "Review"}).status_code == 404
    _consent(client, a, pa)
    _appt(client, a, pa, clock["now"] + timedelta(hours=2))
    assert _run(client, b["h"])["appointments"] == 0
    assert _log(client, b["h"]) == []


def test_permissions(client, clock):
    c = _clinic(client)
    p = _patient(client, c["h"])
    doctor, nurse = _member(client, c, "doctor"), _member(client, c, "nurse")
    recep, billing = _member(client, c, "receptionist"), _member(client, c, "billing")
    body = {"patient_id": p["id"], "due_date": str(clock["now"].date() + timedelta(days=7)),
            "reason": "Review visit"}
    for h in (nurse, recep, billing):
        assert client.post(f"{API}/follow-ups", json=body, headers=h).status_code == 403
    fu = client.post(f"{API}/follow-ups", json=body, headers=doctor)
    assert fu.status_code == 201
    assert client.get(f"{API}/follow-ups", headers=nurse).status_code == 200
    assert client.get(f"{API}/follow-ups", headers=billing).status_code == 403
    assert client.post(f"{API}/follow-ups/{fu.json()['id']}/cancel", json={},
                       headers=nurse).status_code == 403
    # comms: reception runs reminders and records consent but cannot edit templates
    assert client.get(f"{API}/comms/overview", headers=recep).status_code == 200
    assert _run(client, recep)["appointments"] == 0
    assert client.put(f"{API}/comms/settings", json={}, headers=recep).status_code == 403
    assert client.post(f"{API}/comms/templates", headers=recep, json={
        "channel": "sms", "purpose": "generic", "language": "en", "name": "x x",
        "body": "Hi"}).status_code == 403
    assert client.get(f"{API}/comms/delivery-log", headers=billing).status_code == 403
    assert client.post(f"{API}/comms/reminders/run", json={},
                       headers=nurse).status_code == 403
    assert client.put(f"{API}/comms/patients/{p['id']}/consent", headers=billing, json={
        "channel": "sms", "status": "opted_in",
        "source": "registration_form"}).status_code == 403
    assert client.put(f"{API}/comms/patients/{p['id']}/consent", headers=recep, json={
        "channel": "sms", "status": "opted_in",
        "source": "registration_form"}).status_code == 200


def test_plan_gates_channels(client, clock):
    c = _clinic(client, plan="rural_clinic")  # comms_sms only
    r = client.post(f"{API}/comms/templates", headers=c["h"], json={
        "channel": "email", "purpose": "generic", "language": "en", "name": "Mail",
        "body": "Hi {patient_first_name}"})
    assert r.status_code == 403 and "comms_email" in r.json()["detail"]
    client.put(f"{API}/comms/settings", headers=c["h"], json={
        "reminder_channels": ["sms", "whatsapp", "email"]})
    p = _patient(client, c["h"])
    for ch in ("sms", "whatsapp"):
        _consent(client, c, p, channel=ch)
    _appt(client, c, p, clock["now"] + timedelta(hours=2))
    run = _run(client, c["h"])
    assert run["channels"] == ["sms"] and run["by_status"] == {"sent_mock": 1}


# --------------------------------------------------------------------- follow-ups
def test_follow_up_lifecycle(client, clock):
    c = _clinic(client)
    p, other = _patient(client, c["h"]), _patient(client, c["h"])
    today = clock["now"].date()
    mk = lambda due, reason="Review visit": client.post(  # noqa: E731
        f"{API}/follow-ups", headers=c["h"],
        json={"patient_id": p["id"], "due_date": str(due), "reason": reason})
    assert mk(today - timedelta(days=1)).status_code == 422  # in the past
    assert mk(today, reason="<script>").status_code == 422
    due_today = mk(today).json()
    upcoming = mk(today + timedelta(days=10), "Dressing change").json()
    assert due_today["bucket"] == "due_today" and upcoming["bucket"] == "upcoming"
    assert due_today["created_by_name"] == "Dr Comms Owner"
    # make one overdue (as if created earlier)
    su = _su()
    with su.cursor() as cur:
        cur.execute("UPDATE follow_ups SET due_date = %s WHERE id = %s",
                    (today - timedelta(days=3), upcoming["id"]))
    su.close()
    lst = lambda b: [f["id"] for f in client.get(  # noqa: E731
        f"{API}/follow-ups", params={"bucket": b}, headers=c["h"]).json()]
    assert lst("due_today") == [due_today["id"]] and lst("overdue") == [upcoming["id"]]
    assert client.get(f"{API}/follow-ups/summary", headers=c["h"]).json()["overdue"] == 1

    fid = due_today["id"]
    foreign_appt = _appt(client, c, other, clock["now"] + timedelta(days=2))
    assert client.post(f"{API}/follow-ups/{fid}/book", headers=c["h"], json={
        "appointment_id": foreign_appt["id"]}).status_code == 422
    appt = _appt(client, c, p, clock["now"] + timedelta(days=2))
    booked = client.post(f"{API}/follow-ups/{fid}/book", headers=c["h"],
                         json={"appointment_id": appt["id"]})
    assert booked.status_code == 200 and booked.json()["status"] == "booked"
    assert booked.json()["appointment_starts_at"] is not None
    done = client.post(f"{API}/follow-ups/{fid}/complete", headers=c["h"], json={})
    assert done.json()["status"] == "completed" and done.json()["bucket"] == "closed"
    for action in ("cancel", "missed", "complete"):
        assert client.post(f"{API}/follow-ups/{fid}/{action}", headers=c["h"],
                           json={}).status_code == 409
    miss = client.post(f"{API}/follow-ups/{upcoming['id']}/missed", headers=c["h"], json={})
    assert miss.json()["status"] == "missed"
    cancel = client.post(f"{API}/follow-ups/{upcoming['id']}/cancel", headers=c["h"],
                         json={"note": "Patient moved away"})
    assert cancel.json()["status"] == "cancelled"
    assert cancel.json()["status_note"] == "Patient moved away"


def test_follow_up_reminders(client, clock):
    c = _clinic(client)
    p = _patient(client, c["h"])
    _consent(client, c, p)
    fu = client.post(f"{API}/follow-ups", headers=c["h"], json={
        "patient_id": p["id"], "due_date": str(clock["now"].date() + timedelta(days=1)),
        "reason": "Review visit"}).json()
    run = _run(client, c["h"])
    assert run["follow_ups"] == 1 and run["by_status"] == {"sent_mock": 1}
    got = client.get(f"{API}/follow-ups/{fu['id']}", headers=c["h"]).json()
    assert got["status"] == "reminded" and got["reminded_at"]
    # a manual reminder for the same due date is a duplicate, not a second message
    again = client.post(f"{API}/follow-ups/{fu['id']}/remind", json={}, headers=c["h"])
    assert again.json()["results"][0]["status"] == "duplicate"
    log = _log(client, c["h"], follow_up_id=fu["id"])
    assert len(log) == 1 and log[0]["purpose"] == "follow_up"


def test_missed_appointment_detection_and_notice(client, clock):
    c = _clinic(client)
    p = _patient(client, c["h"])
    real_now = datetime.now(timezone.utc)
    clock["now"] = real_now.astimezone(IST).replace(hour=12)  # daytime today
    past = _appt(client, c, p, clock["now"] - timedelta(hours=2))
    attended = _appt(client, c, p, clock["now"] - timedelta(hours=4))
    client.patch(f"{API}/appointments/{attended['id']}", json={"status": "checked_in"},
                 headers=c["h"])
    no_show = _appt(client, c, p, clock["now"] - timedelta(hours=6))
    client.patch(f"{API}/appointments/{no_show['id']}", json={"status": "no_show"},
                 headers=c["h"])
    _appt(client, c, p, clock["now"] - timedelta(minutes=10))  # within grace
    _appt(client, c, p, clock["now"] - timedelta(days=10))      # outside the window
    missed = client.get(f"{API}/follow-ups/missed-appointments", headers=c["h"]).json()
    assert {m["appointment_id"] for m in missed} == {past["id"], no_show["id"]}
    assert all(m["notified"] is False for m in missed)

    url = f"{API}/follow-ups/missed-appointments/{past['id']}/notify"
    assert client.post(url, json={}, headers=c["h"]).json()["results"][0]["status"] \
        == "skipped_no_consent"
    _consent(client, c, p)
    sent = client.post(url, json={}, headers=c["h"]).json()
    assert sent["results"][0]["status"] == "sent_mock" and "not sent" in sent["mock_notice"]
    assert client.post(url, json={}, headers=c["h"]).json()["results"][0]["status"] \
        == "duplicate"
    assert client.post(f"{API}/follow-ups/missed-appointments/{attended['id']}/notify",
                       json={}, headers=c["h"]).status_code == 404
    missed = {m["appointment_id"]: m for m in client.get(
        f"{API}/follow-ups/missed-appointments", headers=c["h"]).json()}
    assert missed[past["id"]]["notified"] is True


def test_preferred_language_picks_template_and_email_needs_address(client, clock):
    c = _clinic(client)
    p = _patient(client, c["h"])
    client.put(f"{API}/comms/settings", headers=c["h"], json={
        "reminder_channels": ["sms", "email"]})
    r = client.put(f"{API}/comms/patients/{p['id']}/preferences", headers=c["h"],
                   json={"preferred_language": "hi"})
    assert r.status_code == 200 and r.json()["preferred_language"] == "hi"
    _consent(client, c, p)
    _consent(client, c, p, channel="email")
    _appt(client, c, p, clock["now"] + timedelta(hours=2))
    run = _run(client, c["h"])
    assert run["by_status"] == {"sent_mock": 1, "skipped_no_recipient": 1}
    sms = _log(client, c["h"], channel="sms")[0]
    assert sms["language"] == "hi"
    outbox = client.get(f"{API}/dev/outbox", params={"limit": 5}).json()
    assert any("नमस्ते" in m["body"] and m["to"] == p["phone"] for m in outbox)
