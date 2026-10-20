"""Smart Setup Wizard, QR check-in and printer profiles (migration 0015).

Synthetic clinics/patients only. Every request runs as ``hms_app`` (RLS on);
raw-SQL assertions use the superuser connection."""
from __future__ import annotations

import itertools
import re
import threading
import time as _time
from datetime import datetime, time, timedelta, timezone

import psycopg2
import pytest

from app import ratelimit
from app.services.setup_rules import (
    Session,
    generate_slots,
    hash_checkin_token,
    new_checkin_token,
    normalize_checkin_code,
    working_hours_errors,
)
from app.timeutil import clinic_day_bounds, clinic_today, clinic_tz
from tests.conftest import PG_HOST, PG_PORT, PG_SUPERUSER, TEST_DB, _auth

PASSWORD = "Str0ngPassphrase!"
API = "/api/v1"
_seq = itertools.count(1)


def _sql(stmt, params=()):
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_SUPERUSER, dbname=TEST_DB)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(stmt, params)
        rows = cur.fetchall() if cur.description else None
    conn.close()
    return rows


def _clinic(client, tag="setup"):
    slug = f"{tag}-{next(_seq)}-{int(_time.time()) % 100000}"
    r = client.post(f"{API}/auth/register", json={
        "organization_name": slug.title(), "organization_slug": slug,
        "full_name": "Dr. Setup Owner", "email": f"owner@{slug}.example.com",
        "password": PASSWORD})
    assert r.status_code == 201, r.text
    data = r.json()
    h = _auth(data)
    b = client.post(f"{API}/branches", json={"name": "Main", "code": "MAIN"}, headers=h)
    assert b.status_code == 201, b.text
    return {"h": h, "branch": b.json(), "auth": data, "slug": slug}


def _member(client, clinic, role):
    email = f"{role}{next(_seq)}@{clinic['slug']}.example.com"
    r = client.post(f"{API}/members", json={"email": email, "full_name": f"Synthetic {role}",
                                            "password": PASSWORD, "role_key": role},
                    headers=clinic["h"])
    assert r.status_code == 201, r.text
    login = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return r.json(), _auth(login.json())


def _patient(client, clinic, name=None):
    n = next(_seq)
    r = client.post(f"{API}/patients", json={
        "full_name": name or f"Synthetic Patient {n}", "gender": "female",
        "phone": f"97{n:08d}", "date_of_birth": "1990-01-01T00:00:00Z",
        "allow_duplicates": True}, headers=clinic["h"])
    assert r.status_code == 201, r.text
    return r.json()


def _today_window():
    """A short window inside TODAY's clinic day (in the past, so it never
    spills into tomorrow whatever time the suite runs)."""
    start, _ = clinic_day_bounds(clinic_today())
    now = datetime.now(timezone.utc)
    s = start + max((now - start) / 2, timedelta(minutes=1))
    return s, s + timedelta(minutes=5)


def _appointment(client, clinic, patient, *, starts=None, ends=None, provider=None):
    if starts is None:
        starts, ends = _today_window()
    body = {"patient_id": patient["id"], "branch_id": clinic["branch"]["id"],
            "starts_at": starts.isoformat(), "ends_at": ends.isoformat(),
            "reason": "Synthetic follow-up"}
    if provider:
        body["provider_user_id"] = provider
    r = client.post(f"{API}/appointments", json=body, headers=clinic["h"])
    assert r.status_code == 201, r.text
    return r.json()


def _issue(client, h, appt_id):
    return client.post(f"{API}/checkin/appointments/{appt_id}/token", headers=h)


@pytest.fixture(scope="module")
def clinic(client):
    return _clinic(client)


@pytest.fixture(scope="module")
def other(client):
    return _clinic(client, "other")


# =========================== pure rules ========================================
def test_working_hours_rules():
    ok = [Session(0, time(9), time(13)), Session(0, time(17), time(20)),
          Session(1, time(9), time(18), time(13), time(14))]
    assert working_hours_errors(ok) == []
    assert "overlap" in working_hours_errors(
        [Session(0, time(9), time(13)), Session(0, time(12), time(15))])[0]
    assert "after opening" in working_hours_errors([Session(2, time(18), time(9))])[0]
    assert "inside" in working_hours_errors([Session(2, time(9), time(12), time(11),
                                                     time(13))])[0]
    assert "both" in working_hours_errors([Session(2, time(9), time(12), time(10))])[0]
    assert working_hours_errors([Session(7, time(9), time(12))])


def test_slot_generation_skips_break_and_remainder():
    day = datetime(2026, 10, 19).date()  # a Monday
    slots = generate_slots(day, [Session(0, time(9), time(12, 10), time(10), time(10, 30))],
                           30, clinic_tz())
    local = [s.astimezone(clinic_tz()).strftime("%H:%M") for s, _ in slots]
    assert local == ["09:00", "09:30", "10:30", "11:00", "11:30"]
    assert generate_slots(day, [Session(1, time(9), time(12))], 30, clinic_tz()) == []


def test_checkin_token_is_random_and_normalised():
    raw, digest = new_checkin_token()
    assert re.fullmatch(r"[A-Z2-7]{26}", raw)
    assert digest == hash_checkin_token(raw) and raw not in digest
    assert new_checkin_token()[0] != raw
    spaced = "-".join(raw[i:i + 4] for i in range(0, 26, 4)).lower()
    assert normalize_checkin_code(spaced) == raw
    assert normalize_checkin_code("not a code") is None


# =========================== settings + wizard ==================================
def test_settings_defaults_validation_and_versioned_storage(client, clinic):
    h = clinic["h"]
    got = client.get(f"{API}/setup/settings", headers=h).json()
    assert got["settings"]["version"] == 1
    assert got["settings"]["schedule"] == {"slot_minutes": 15, "max_per_slot": 1,
                                           "online_booking_enabled": False}
    assert got["settings"]["prescription"]["paper_size"] == "A4"

    bad = [
        {"prescription": {"paper_size": "Letter"}},
        {"billing": {"invoice_prefix": "bad prefix!"}},
        {"billing": {"default_payment_methods": ["cash", "cash"]}},
        {"billing": {"default_payment_methods": ["bitcoin"]}},
        {"schedule": {"slot_minutes": 7}},
        {"schedule": {"max_per_slot": 0}},
        {"schedule": {"unknown": 1}},
        {"theme": {}},
    ]
    for body in bad:
        r = client.patch(f"{API}/setup/settings", json=body, headers=h)
        assert r.status_code == 422, (body, r.text)

    r = client.patch(f"{API}/setup/settings", json={
        "prescription": {"header_text": "Synthetic Clinic — OPD", "footer_text": "Get well soon",
                         "paper_size": "A5", "language": "mr",
                         "show_registration_number": True},
        "billing": {"invoice_prefix": "SYN-", "show_gstin": False,
                    "default_payment_methods": ["upi", "cash"],
                    "receipt_footer": "धन्यवाद"}}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["settings"]["prescription"]["paper_size"] == "A5"
    stored = _sql("SELECT schema_version, settings FROM org_settings o "
                  "JOIN organizations g ON g.id = o.organization_id WHERE g.slug = %s",
                  (clinic["slug"],))[0]
    assert stored[0] == 1 and stored[1]["version"] == 1
    assert stored[1]["billing"]["receipt_footer"] == "धन्यवाद"
    # untouched section kept its defaults
    assert stored[1]["schedule"]["slot_minutes"] == 15


def test_wizard_progress_is_persisted_and_resumable(client):
    c = _clinic(client, "wiz")
    h = c["h"]
    w = client.get(f"{API}/setup/wizard", headers=h).json()
    assert w["should_show"] is True and w["finished"] is False
    assert [s["key"] for s in w["steps"]][:3] == ["identity", "branch", "staff"]
    assert w["current_step"] == "identity" and w["progress_percent"] == 0
    branch = next(s for s in w["steps"] if s["key"] == "branch")
    assert branch["data_ready"] is True  # the clinic already has a branch

    assert client.post(f"{API}/setup/wizard/steps/identity", json={"status": "done"},
                       headers=h).status_code == 200
    r = client.post(f"{API}/setup/wizard/steps/branch", json={"status": "skipped"}, headers=h)
    assert r.json()["current_step"] == "staff"
    assert client.post(f"{API}/setup/wizard/steps/nope", json={"status": "done"},
                       headers=h).status_code == 422
    assert client.post(f"{API}/setup/wizard/steps/staff", json={"status": "maybe"},
                       headers=h).status_code == 422

    # resume from a "different device": fresh GET sees the same state
    again = client.get(f"{API}/setup/wizard", headers=h).json()
    marks = {s["key"]: s["status"] for s in again["steps"]}
    assert marks["identity"] == "done" and marks["branch"] == "skipped"
    assert marks["staff"] == "todo" and again["current_step"] == "staff"
    assert again["progress_percent"] == round(100 * 2 / 11)

    # saving the pre-filled defaults counts as having configured the section
    client.patch(f"{API}/setup/settings", json={"schedule": {}}, headers=h)
    sched = next(s for s in client.get(f"{API}/setup/wizard", headers=h).json()["steps"]
                 if s["key"] == "schedule")
    assert sched["data_ready"] is True

    done = client.patch(f"{API}/setup/wizard", json={"finished": True}, headers=h).json()
    assert done["finished"] is True and done["should_show"] is False
    reopened = client.patch(f"{API}/setup/wizard", json={"finished": False}, headers=h).json()
    assert reopened["finished"] is False
    actions = {r[0] for r in _sql(
        "SELECT action FROM audit_events a JOIN organizations o ON o.id = a.organization_id "
        "WHERE o.slug = %s AND action LIKE 'setup.%%'", (c["slug"],))}
    assert {"setup.wizard_step", "setup.wizard_finished", "setup.wizard_reopened",
            "setup.settings_updated"} <= actions


def test_setup_permissions(client, clinic):
    _, rh = _member(client, clinic, "receptionist")
    _, nh = _member(client, clinic, "nurse")
    w = client.get(f"{API}/setup/wizard", headers=rh)
    assert w.status_code == 200 and w.json()["should_show"] is False
    assert client.post(f"{API}/setup/wizard/steps/identity", json={"status": "done"},
                       headers=rh).status_code == 403
    assert client.patch(f"{API}/setup/settings", json={"schedule": {}},
                        headers=rh).status_code == 403
    assert client.put(f"{API}/setup/fees/default", json={"consultation_fee": 1},
                      headers=nh).status_code == 403
    assert client.post(f"{API}/setup/printers", json={"name": "x", "kind": "a4"},
                       headers=rh).status_code == 403
    # check-in needs checkin.manage (receptionist yes, nurse no)
    assert client.post(f"{API}/checkin/verify", json={"code": "A" * 26},
                       headers=nh).status_code == 403
    assert client.post(f"{API}/checkin/verify", json={"code": "A" * 26},
                       headers=rh).status_code == 404
    assert client.get(f"{API}/setup/wizard").status_code == 401


# =========================== working hours + slots ==============================
def test_working_hours_put_validation_and_isolation(client, clinic, other):
    url = f"{API}/setup/branches/{clinic['branch']['id']}/working-hours"
    h = clinic["h"]
    week = [{"weekday": d, "opens_at": "09:00", "closes_at": "18:00",
             "break_starts_at": "13:00", "break_ends_at": "14:00"} for d in range(6)]
    r = client.put(url, json={"sessions": week}, headers=h)
    assert r.status_code == 200, r.text
    assert len(r.json()["sessions"]) == 6
    for bad in (
        [{"weekday": 0, "opens_at": "09:00", "closes_at": "13:00"},
         {"weekday": 0, "opens_at": "12:30", "closes_at": "15:00"}],          # overlap
        [{"weekday": 1, "opens_at": "18:00", "closes_at": "09:00"}],          # inverted
        [{"weekday": 1, "opens_at": "09:00", "closes_at": "12:00",
          "break_starts_at": "11:00", "break_ends_at": "12:30"}],             # break outside
        [{"weekday": 1, "opens_at": "09:00", "closes_at": "12:00",
          "break_starts_at": "11:00"}],                                       # half a break
        [{"weekday": 9, "opens_at": "09:00", "closes_at": "12:00"}],          # weekday
    ):
        assert client.put(url, json={"sessions": bad}, headers=h).status_code == 422, bad
    # unchanged after rejected writes
    assert len(client.get(url, headers=h).json()["sessions"]) == 6
    # two sessions a day (morning + evening) are fine
    split = [{"weekday": 6, "opens_at": "09:00", "closes_at": "12:00"},
             {"weekday": 6, "opens_at": "17:00", "closes_at": "20:00"}]
    assert client.put(url, json={"sessions": week + split}, headers=h).status_code == 200
    # another clinic cannot read or write this branch
    assert client.get(url, headers=other["h"]).status_code == 404
    assert client.put(url, json={"sessions": []}, headers=other["h"]).status_code == 404
    assert len(client.get(url, headers=h).json()["sessions"]) == 8


def test_slots_helper(client):
    c = _clinic(client, "slots")
    h, branch = c["h"], c["branch"]["id"]
    doctor, _ = _member(client, c, "doctor")
    day = clinic_today() + timedelta(days=7)
    url = f"{API}/appointments/slots?branch_id={branch}&date={day.isoformat()}"
    empty = client.get(url, headers=h).json()
    assert empty["configured"] is False and empty["slots"] == []

    client.put(f"{API}/setup/branches/{branch}/working-hours", json={"sessions": [
        {"weekday": day.weekday(), "opens_at": "09:00", "closes_at": "12:00",
         "break_starts_at": "10:00", "break_ends_at": "10:30"}]}, headers=h)
    client.patch(f"{API}/setup/settings", json={"schedule": {"slot_minutes": 30,
                                                             "max_per_slot": 2}}, headers=h)
    s = client.get(url, headers=h).json()
    assert s["configured"] is True and s["slot_minutes"] == 30
    local = [datetime.fromisoformat(x["starts_at"]).astimezone(clinic_tz()).strftime("%H:%M")
             for x in s["slots"]]
    assert local == ["09:00", "09:30", "10:30", "11:00", "11:30"]

    tz = clinic_tz()
    start = datetime.combine(day, time(9, 30), tzinfo=tz)
    _appointment(client, c, _patient(client, c), starts=start,
                 ends=start + timedelta(minutes=30), provider=doctor["user_id"])
    branch_view = client.get(url, headers=h).json()["slots"][1]
    assert branch_view["booked"] == 1 and branch_view["available"] is True  # 1 < 2
    doc_view = client.get(f"{url}&provider_user_id={doctor['user_id']}",
                          headers=h).json()["slots"]
    assert doc_view[1]["available"] is False and doc_view[0]["available"] is True
    # booking semantics unchanged: provider overlap is still rejected by POST
    r = client.post(f"{API}/appointments", json={
        "patient_id": _patient(client, c)["id"], "branch_id": branch,
        "provider_user_id": doctor["user_id"], "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(minutes=30)).isoformat()}, headers=h)
    assert r.status_code == 409
    assert client.get(f"{API}/appointments/slots?branch_id={branch}&date=bad",
                      headers=h).status_code == 422


# =========================== fees ===============================================
def test_fee_master(client, clinic, other):
    h = clinic["h"]
    doctor, _ = _member(client, clinic, "doctor")
    other_doc, _ = _member(client, other, "doctor")
    assert client.get(f"{API}/setup/fees/effective", headers=h).json()["source"] == "none"
    r = client.put(f"{API}/setup/fees/default", json={
        "consultation_fee": "300.00", "follow_up_fee": 150, "follow_up_valid_days": 7},
        headers=h)
    assert r.status_code == 200, r.text
    assert client.put(f"{API}/setup/fees/default", json={"consultation_fee": 350},
                      headers=h).status_code == 200  # upsert, not a second row
    assert client.put(f"{API}/setup/fees/providers/{doctor['user_id']}",
                      json={"consultation_fee": 500}, headers=h).status_code == 200
    for bad in ({"consultation_fee": -1}, {"consultation_fee": 2_000_000},
                {"consultation_fee": "1.234"}, {"consultation_fee": 100,
                                                "follow_up_valid_days": 400}):
        assert client.put(f"{API}/setup/fees/default", json=bad,
                          headers=h).status_code == 422, bad
    # a doctor of another clinic is not ours to price
    assert client.put(f"{API}/setup/fees/providers/{other_doc['user_id']}",
                      json={"consultation_fee": 1}, headers=h).status_code == 422
    fees = client.get(f"{API}/setup/fees", headers=h).json()
    assert float(fees["default"]["consultation_fee"]) == 350
    assert fees["default"]["follow_up_fee"] is None
    assert [float(p["consultation_fee"]) for p in fees["providers"]] == [500]
    eff = client.get(f"{API}/setup/fees/effective?provider_user_id={doctor['user_id']}",
                     headers=h).json()
    assert eff["source"] == "provider" and float(eff["consultation_fee"]) == 500
    eff = client.get(f"{API}/setup/fees/effective?provider_user_id={other_doc['user_id']}",
                     headers=h).json()
    assert eff["source"] == "default"
    assert client.get(f"{API}/setup/fees", headers=other["h"]).json()["default"] is None
    assert client.delete(f"{API}/setup/fees/providers/{doctor['user_id']}",
                         headers=h).status_code == 204
    assert client.delete(f"{API}/setup/fees/providers/{doctor['user_id']}",
                         headers=h).status_code == 404


# =========================== QR check-in ========================================
def test_qr_token_is_opaque_and_hashed_at_rest(client, clinic):
    name = "Synthetic Opaque Patient"
    p = _patient(client, clinic, name=name)
    appt = _appointment(client, clinic, p)
    r = _issue(client, clinic["h"], appt["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["token"]
    assert set(body) == {"appointment_id", "token", "expires_at"}
    assert re.fullmatch(r"[A-Z2-7]{26}", token)
    lowered = token.lower()
    for fragment in (name.lower(), "synthetic", p["phone"], p["uhid"].lower(),
                     appt["id"].replace("-", "")[:8], clinic["slug"][:6]):
        assert fragment not in lowered
    assert name not in r.text and p["phone"] not in r.text and p["uhid"] not in r.text

    rows = _sql("SELECT token_hash, row_to_json(t)::text FROM checkin_tokens t "
                "WHERE appointment_id = %s", (appt["id"],))
    assert len(rows) == 1
    assert rows[0][0] == hash_checkin_token(token)
    assert token not in rows[0][1]  # raw token stored nowhere
    # expiry = end of the appointment's clinic day
    _, day_end = clinic_day_bounds(clinic_today())
    assert datetime.fromisoformat(body["expires_at"]) == day_end


def test_no_phi_on_unauthenticated_routes(client, clinic):
    p = _patient(client, clinic, name="Synthetic Unauth Patient")
    token = _issue(client, clinic["h"], _appointment(client, clinic, p)["id"]).json()["token"]
    for path in ("/checkin/verify", "/checkin/confirm", "/checkin/kiosk"):
        r = client.post(f"{API}{path}", json={"code": token})
        assert r.status_code == 401
        assert "Synthetic" not in r.text and p["uhid"] not in r.text
    # the code still works afterwards (nothing was consumed)
    v = client.post(f"{API}/checkin/verify", json={"code": token}, headers=clinic["h"])
    assert v.status_code == 200 and v.json()["status"] == "ready"


def test_verify_then_confirm_single_use_and_idempotent(client, clinic):
    _, rh = _member(client, clinic, "receptionist")
    p = _patient(client, clinic, name="Synthetic Checkin Patient")
    appt = _appointment(client, clinic, p)
    token = _issue(client, rh, appt["id"]).json()["token"]
    pretty = " ".join(token[i:i + 4] for i in range(0, 26, 4)).lower()

    v = client.post(f"{API}/checkin/verify", json={"code": pretty}, headers=rh)
    assert v.status_code == 200, v.text
    vb = v.json()
    assert vb["status"] == "ready" and vb["patient_display_name"] == "Synthetic Checkin Patient"
    assert vb["branch_name"] == "Main" and vb["queue_token_number"] is None
    assert "uhid" not in vb and "phone" not in vb  # minimal context only

    c1 = client.post(f"{API}/checkin/confirm", json={"code": token}, headers=rh)
    assert c1.status_code == 200, c1.text
    assert c1.json()["status"] == "checked_in"
    q = c1.json()["queue_entry"]
    c2 = client.post(f"{API}/checkin/confirm", json={"code": token}, headers=rh)
    assert c2.json()["status"] == "already_checked_in"
    assert c2.json()["queue_entry"]["token_number"] == q["token_number"]
    assert c2.json()["queue_entry"]["id"] == q["id"]
    v2 = client.post(f"{API}/checkin/verify", json={"code": token}, headers=rh).json()
    assert v2["status"] == "already_checked_in" and v2["queue_token_number"] == q["token_number"]

    assert client.get(f"{API}/appointments/{appt['id']}",
                      headers=rh).json()["status"] == "checked_in"
    board = client.get(f"{API}/opd/queue", headers=rh).json()["items"]
    mine = [e for e in board if e["patient_id"] == p["id"]]
    assert len(mine) == 1 and mine[0]["appointment_id"] == appt["id"]
    # a used appointment cannot get a fresh code
    assert _issue(client, rh, appt["id"]).status_code == 409

    audit = _sql("SELECT action, metadata FROM audit_events WHERE resource_id = %s "
                 "ORDER BY id", (appt["id"],))
    actions = [a for a, _ in audit]
    assert {"checkin.token_issued", "checkin.verified", "checkin.confirmed",
            "checkin.duplicate"} <= set(actions)
    for _, meta in audit:  # the raw code is never written to the audit trail
        assert token not in str(meta)


def test_kiosk_reveals_only_the_queue_number(client, clinic):
    p = _patient(client, clinic, name="Synthetic Kiosk Patient")
    token = _issue(client, clinic["h"], _appointment(client, clinic, p)["id"]).json()["token"]
    r = client.post(f"{API}/checkin/kiosk", json={"code": token}, headers=clinic["h"])
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"status", "token_number"} and r.json()["status"] == "checked_in"
    again = client.post(f"{API}/checkin/kiosk", json={"code": token}, headers=clinic["h"])
    assert again.json() == {"status": "already_checked_in",
                            "token_number": r.json()["token_number"]}
    bad = client.post(f"{API}/checkin/kiosk", json={"code": "B" * 26}, headers=clinic["h"])
    assert bad.status_code == 404 and bad.json()["detail"] == "Please see the reception desk"


def test_concurrent_confirms_issue_one_queue_entry(client, clinic):
    p = _patient(client, clinic)
    appt = _appointment(client, clinic, p)
    token = _issue(client, clinic["h"], appt["id"]).json()["token"]
    barrier = threading.Barrier(4)
    results: list = [None] * 4

    def run(i):
        barrier.wait(timeout=10)
        results[i] = client.post(f"{API}/checkin/confirm", json={"code": token},
                                 headers=clinic["h"])

    threads = [threading.Thread(target=run, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert all(r is not None and r.status_code == 200 for r in results), \
        [r.text for r in results if r is not None]
    statuses = sorted(r.json()["status"] for r in results)
    assert statuses == ["already_checked_in"] * 3 + ["checked_in"]
    assert len({r.json()["queue_entry"]["token_number"] for r in results}) == 1
    count = _sql("SELECT count(*) FROM opd_queue WHERE patient_id = %s", (p["id"],))[0][0]
    assert count == 1


def test_existing_queue_entry_is_reused(client, clinic):
    p = _patient(client, clinic)
    appt = _appointment(client, clinic, p)
    manual = client.post(f"{API}/opd/queue", json={"patient_id": p["id"],
                                                    "branch_id": clinic["branch"]["id"]},
                         headers=clinic["h"])
    assert manual.status_code == 201, manual.text
    token = _issue(client, clinic["h"], appt["id"]).json()["token"]
    c = client.post(f"{API}/checkin/confirm", json={"code": token}, headers=clinic["h"]).json()
    assert c["status"] == "checked_in"
    assert c["queue_entry"]["token_number"] == manual.json()["token_number"]


def test_cross_tenant_token_is_a_generic_404(client, clinic, other):
    token = _issue(client, clinic["h"],
                   _appointment(client, clinic, _patient(client, clinic))["id"]).json()["token"]
    missing = client.post(f"{API}/checkin/verify", json={"code": "C" * 26}, headers=other["h"])
    foreign = client.post(f"{API}/checkin/verify", json={"code": token}, headers=other["h"])
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["detail"] == missing.json()["detail"]
    assert client.post(f"{API}/checkin/confirm", json={"code": token},
                       headers=other["h"]).status_code == 404
    # another clinic cannot mint a code for our appointment either
    appt = _appointment(client, clinic, _patient(client, clinic))
    assert _issue(client, other["h"], appt["id"]).status_code == 404
    # and the code still works in its own clinic
    assert client.post(f"{API}/checkin/confirm", json={"code": token},
                       headers=clinic["h"]).json()["status"] == "checked_in"
    rejected = _sql("SELECT count(*) FROM audit_events a JOIN organizations o "
                    "ON o.id = a.organization_id WHERE o.slug = %s "
                    "AND action = 'checkin.rejected'", (other["slug"],))[0][0]
    assert rejected >= 2


def test_expired_replaced_cancelled_and_future_codes(client, clinic):
    h = clinic["h"]
    # expired
    a1 = _appointment(client, clinic, _patient(client, clinic))
    t1 = _issue(client, h, a1["id"]).json()["token"]
    _sql("UPDATE checkin_tokens SET expires_at = now() - interval '1 minute' "
         "WHERE token_hash = %s", (hash_checkin_token(t1),))
    r = client.post(f"{API}/checkin/confirm", json={"code": t1}, headers=h)
    assert r.status_code == 410 and "expired" in r.json()["detail"]
    # replaced by a newer code
    a2 = _appointment(client, clinic, _patient(client, clinic))
    old = _issue(client, h, a2["id"]).json()["token"]
    new = _issue(client, h, a2["id"]).json()["token"]
    assert old != new
    assert client.post(f"{API}/checkin/verify", json={"code": old},
                       headers=h).status_code == 410
    assert client.post(f"{API}/checkin/verify", json={"code": new},
                       headers=h).status_code == 200
    # cancelled after the code was issued
    a3 = _appointment(client, clinic, _patient(client, clinic))
    t3 = _issue(client, h, a3["id"]).json()["token"]
    assert client.patch(f"{API}/appointments/{a3['id']}", json={"status": "cancelled"},
                        headers=h).status_code == 200
    r = client.post(f"{API}/checkin/confirm", json={"code": t3}, headers=h)
    assert r.status_code == 409 and "cancelled" in r.json()["detail"]
    assert _issue(client, h, a3["id"]).status_code == 409
    # future appointment: code can be shared ahead, check-in opens on the day
    start = datetime.combine(clinic_today() + timedelta(days=3), time(10),
                             tzinfo=clinic_tz())
    a4 = _appointment(client, clinic, _patient(client, clinic), starts=start,
                      ends=start + timedelta(minutes=15))
    t4 = _issue(client, h, a4["id"])
    assert t4.status_code == 201
    r = client.post(f"{API}/checkin/confirm", json={"code": t4.json()["token"]}, headers=h)
    assert r.status_code == 409 and "day of the appointment" in r.json()["detail"]
    # past appointment day: no code
    past = datetime.combine(clinic_today() - timedelta(days=2), time(10), tzinfo=clinic_tz())
    a5 = _appointment(client, clinic, _patient(client, clinic), starts=past,
                      ends=past + timedelta(minutes=15))
    assert _issue(client, h, a5["id"]).status_code == 409
    # garbage input
    assert client.post(f"{API}/checkin/verify", json={"code": "x" * 30},
                       headers=h).status_code == 404


def test_checkin_verification_is_rate_limited(client, clinic, monkeypatch):
    member, rh = _member(client, clinic, "receptionist")
    monkeypatch.setenv("RL_CHECKIN_PER_USER", "3")
    org_id = clinic["auth"]["organization"]["id"]
    ratelimit.clear("checkin", f"{org_id}:{member['user_id']}")
    codes = [client.post(f"{API}/checkin/verify", json={"code": "D" * 26}, headers=rh)
             .status_code for _ in range(5)]
    assert codes[:3] == [404, 404, 404]
    assert codes[3] == 429
    # other staff members are unaffected
    owner_key = f"{org_id}:{clinic['auth']['user']['id']}"
    ratelimit.clear("checkin", owner_key)
    assert client.post(f"{API}/checkin/verify", json={"code": "D" * 26},
                       headers=clinic["h"]).status_code == 404
    ratelimit.clear("checkin", f"{org_id}:{member['user_id']}")
    ratelimit.clear("checkin", owner_key)


# =========================== printers ===========================================
def test_printer_profiles_crud_defaults_and_isolation(client, clinic, other):
    h = clinic["h"]
    a5 = client.post(f"{API}/setup/printers", json={
        "name": "Front desk A5", "kind": "a5", "default_for": ["prescription"],
        "margin_top_mm": 8, "font_scale": 1.1}, headers=h)
    assert a5.status_code == 201, a5.text
    thermal = client.post(f"{API}/setup/printers", json={
        "name": "Billing thermal", "kind": "thermal_80mm",
        "default_for": ["receipt", "prescription"], "margin_left_mm": 2,
        "margin_right_mm": 2}, headers=h)
    assert thermal.status_code == 201
    # taking "prescription" moved it off the A5 profile
    profiles = {p["name"]: p for p in client.get(f"{API}/setup/printers", headers=h).json()}
    assert profiles["Front desk A5"]["default_for"] == []
    assert profiles["Billing thermal"]["default_for"] == ["prescription", "receipt"]
    d = client.get(f"{API}/setup/printers/defaults", headers=h).json()
    assert d["prescription"]["name"] == "Billing thermal" and d["lab_report"] is None

    pid = a5.json()["id"]
    upd = client.patch(f"{API}/setup/printers/{pid}", json={"default_for": ["prescription"],
                                                           "kind": "a4"}, headers=h)
    assert upd.status_code == 200 and upd.json()["kind"] == "a4"
    d = client.get(f"{API}/setup/printers/defaults", headers=h).json()
    assert d["prescription"]["id"] == pid and d["receipt"]["name"] == "Billing thermal"

    for bad in ({"name": "x", "kind": "letter"}, {"name": "x", "kind": "a4",
                                                  "margin_top_mm": 60},
                {"name": "x", "kind": "a4", "font_scale": 3},
                {"name": "x", "kind": "a4", "default_for": ["poster"]},
                {"name": "", "kind": "a4"}):
        assert client.post(f"{API}/setup/printers", json=bad,
                           headers=h).status_code == 422, bad
    dup = client.post(f"{API}/setup/printers", json={"name": "front desk a5",
                                                     "kind": "a4"}, headers=h)
    assert dup.status_code == 409

    # tenant isolation
    assert client.get(f"{API}/setup/printers/{pid}", headers=other["h"]).status_code == 404
    assert client.patch(f"{API}/setup/printers/{pid}", json={"name": "hijack"},
                        headers=other["h"]).status_code == 404
    assert client.delete(f"{API}/setup/printers/{pid}", headers=other["h"]).status_code == 404
    assert client.get(f"{API}/setup/printers", headers=other["h"]).json() == []
    # readers (e.g. doctors printing an Rx) can see profiles but not change them
    _, dh = _member(client, clinic, "doctor")
    assert client.get(f"{API}/setup/printers/defaults", headers=dh).status_code == 200
    assert client.delete(f"{API}/setup/printers/{pid}", headers=dh).status_code == 403

    assert client.delete(f"{API}/setup/printers/{pid}", headers=h).status_code == 204
    assert client.get(f"{API}/setup/printers/{pid}", headers=h).status_code == 404
    actions = {r[0] for r in _sql(
        "SELECT action FROM audit_events WHERE resource_type = 'printer_profile' "
        "AND resource_id = %s", (pid,))}
    assert actions == {"printer.created", "printer.updated", "printer.deleted"}


def test_rls_blocks_cross_tenant_rows_at_the_database(client, clinic, other):
    """Even a hand-written query under another tenant's context sees nothing."""
    org_a = clinic["auth"]["organization"]["id"]
    org_b = other["auth"]["organization"]["id"]
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_SUPERUSER, dbname=TEST_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SET ROLE hms_app")
            cur.execute("SELECT set_config('app.current_org_id', %s, false)", (org_b,))
            for table in ("org_settings", "branch_working_hours", "fee_schedule",
                          "checkin_tokens", "printer_profiles"):
                cur.execute(f"SELECT count(*) FROM {table} WHERE organization_id = %s",
                            (org_a,))
                assert cur.fetchone()[0] == 0, table
            with pytest.raises(psycopg2.Error):
                cur.execute("INSERT INTO printer_profiles (organization_id, name, kind) "
                            "VALUES (%s, 'evil', 'a4')", (org_a,))
    finally:
        conn.rollback()
        conn.close()
