"""M8.2b: device register, reading capture with provenance, clinician review.
Synthetic clinics, patients and SIMULATED device payloads only."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from tests.conftest import APP_PASSWORD, PG_HOST, PG_PORT, TEST_DB, _auth
from tests.test_ai1_api import _member, _register
from tests.test_m3_clinical_billing import _patient, _start_encounter
from tests.test_m71_tenancy_saas import _sql

API = "/api/v1"
VECTORS = {v["name"]: v for v in json.loads(
    (Path(__file__).resolve().parents[3] / "packages" / "contracts" / "device_vectors.json")
    .read_text(encoding="utf-8"))["vectors"]}
BP = VECTORS["bp all fields"]
SPOT = VECTORS["spot minimal"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clinic(client):
    org = _register(client, plan="clinic_starter")
    h = _auth(org)
    br = client.post(f"{API}/branches", json={"name": "Main", "code": "MAIN"}, headers=h)
    assert br.status_code == 201, br.text
    return org, h, br.json()


def _encounter(client, h, br):
    p = _patient(client, h)
    r = _start_encounter(client, h, p, br)
    assert r.status_code == 201, r.text
    return r.json()


def _device(client, h, kind="bp_monitor", address=None, **kw):
    body = {"kind": kind, "label": f"Sim {kind}", "is_simulator": True,
            "ble_address": address or f"SIM-{uuid.uuid4().hex[:8].upper()}",
            "manufacturer": "Aditya BioNova (simulator)", "model": "SIM-1", **kw}
    r = client.post(f"{API}/devices", json=body, headers=h)
    assert r.status_code == 201, r.text
    return {**r.json(), "address": body["ble_address"]}


def _capture(client, h, dev, enc, vector=BP, **kw):
    body = {"capture_id": str(uuid.uuid4()), "device_id": dev["id"],
            "ble_address": dev["address"], "encounter_id": enc["id"],
            "characteristic": vector["characteristic"], "raw_hex": vector["hex"],
            "source": "simulator", "captured_at": _now(), "app_version": "test", **kw}
    return client.post(f"{API}/device-readings", json=body, headers=h), body


@pytest.fixture
def clinic(client):
    org, h, br = _clinic(client)
    return {"org": org, "h": h, "br": br, "enc": _encounter(client, h, br),
            "bp": _device(client, h), "ox": _device(client, h, kind="pulse_oximeter")}


# --- register --------------------------------------------------------------------------
def test_register_list_retire_and_address_never_returned(client, clinic):
    h = clinic["h"]
    listed = client.get(f"{API}/devices", headers=h).json()
    assert {d["kind"] for d in listed} == {"bp_monitor", "pulse_oximeter"}
    assert all(d["hardware_validated"] is False for d in listed)
    assert all("address" not in json.dumps(d).lower() for d in listed)
    # the same address cannot be registered twice while active
    dup = client.post(f"{API}/devices", headers=h, json={
        "kind": "bp_monitor", "label": "Dup", "is_simulator": True,
        "ble_address": clinic["bp"]["address"]})
    assert dup.status_code == 409
    # real devices use a Bluetooth address, simulators a SIM- id
    assert client.post(f"{API}/devices", headers=h, json={
        "kind": "bp_monitor", "label": "X", "is_simulator": False,
        "ble_address": "SIM-0000ABCD"}).status_code == 422
    assert client.post(f"{API}/devices", headers=h, json={
        "kind": "bp_monitor", "label": "X", "ble_address": "not-an-address"}).status_code == 422
    r = client.post(f"{API}/devices/{clinic['bp']['id']}/retire", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "retired"
    assert client.post(f"{API}/devices/{clinic['bp']['id']}/retire",
                       headers=h).status_code == 409
    resp, _ = _capture(client, h, clinic["bp"], clinic["enc"])
    assert resp.status_code == 403 and "retired" in resp.json()["detail"]
    # hashed at rest
    (hashes,) = _sql("SELECT array_agg(address_hash) FROM medical_devices WHERE "
                     "organization_id = %s", (clinic["org"]["organization"]["id"],))[0]
    assert all(len(x) == 64 and "SIM" not in x for x in hashes)


def test_permissions_per_role(client, clinic):
    h = clinic["h"]
    reception = _member(client, h, "receptionist")
    nurse = _member(client, h, "nurse")
    admin = _member(client, h, "admin")
    assert client.get(f"{API}/devices", headers=reception).status_code == 403
    assert client.post(f"{API}/devices", headers=nurse, json={
        "kind": "bp_monitor", "label": "N", "is_simulator": True,
        "ble_address": "SIM-12345678"}).status_code == 403
    # admin manages devices but cannot capture or review clinical readings
    assert client.get(f"{API}/devices", headers=admin).status_code == 200
    assert _capture(client, admin, clinic["bp"], clinic["enc"])[0].status_code == 403
    r, _ = _capture(client, nurse, clinic["bp"], clinic["enc"])
    assert r.status_code == 201, r.text
    assert client.post(f"{API}/device-readings/{r.json()['id']}/accept", headers=admin,
                       json={"surface": "web", "confirm_patient": True}).status_code == 403
    assert client.get(f"{API}/device-readings?encounter_id={clinic['enc']['id']}",
                      headers=reception).status_code == 403


# --- capture ---------------------------------------------------------------------------
def test_capture_is_parsed_on_the_server_with_provenance(client, clinic):
    r, body = _capture(client, clinic["h"], clinic["bp"], clinic["enc"])
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "pending_review" and out["decision"] is None
    assert out["values"] == BP["expect"]["values"] and out["exact"]["systolic"] == "132.5"
    assert out["flags"] == ["body_movement", "irregular_pulse"]
    assert out["raw_hex"] == BP["hex"] and len(out["raw_sha256"]) == 64
    assert out["source"] == "simulator" and out["device_is_simulator"] is True
    assert out["patient_id"] == clinic["enc"]["patient_id"]
    # the device's 2026-10-21 09:30 clock differs from "now": flagged, not hidden
    assert out["clock_skew"] is True
    # replaying the same capture (offline sync) returns the same reading
    again = client.post(f"{API}/device-readings", json=body, headers=clinic["h"])
    assert again.status_code == 200 and again.json()["id"] == out["id"]
    clash = client.post(f"{API}/device-readings", json={**body, "raw_hex": SPOT["hex"]},
                        headers=clinic["h"])
    assert clash.status_code == 409
    # nothing reached the encounter's vitals
    enc = client.get(f"{API}/encounters/{clinic['enc']['id']}", headers=clinic["h"]).json()
    assert enc["vitals"] == []


def test_capture_refusals(client, clinic):
    h, enc, bp, ox = clinic["h"], clinic["enc"], clinic["bp"], clinic["ox"]
    cases = [
        (dict(ble_address="SIM-00000000"), 403, "not the registered device"),
        (dict(characteristic="2a5e", raw_hex=SPOT["hex"]), 422, "does not belong"),
        (dict(source="ble"), 422, "source does not match"),
        (dict(raw_hex=VECTORS["bp NaN systolic"]["hex"]), 422, "NaN"),
        (dict(raw_hex=VECTORS["bp truncated"]["hex"]), 422, "shorter"),
        (dict(captured_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()),
         422, "future"),
        (dict(captured_at=(datetime.now(timezone.utc) - timedelta(days=4)).isoformat()),
         422, "too old"),
        (dict(captured_at="2026-10-21T09:30:00"), 422, "time zone"),
        (dict(client_parsed={"values": {"systolic": 999}}), 422, "differs"),
        (dict(encounter_id=str(uuid.uuid4())), 404, "Encounter"),
    ]
    for override, code, text in cases:
        r, _ = _capture(client, h, bp, enc, **override)
        assert r.status_code == code and text in json.dumps(r.json()), (override, r.text)
    # the device itself marks the reading unusable: refused and audited
    stored = VECTORS["spot from storage is reported (and refused by policy)"]
    r, _ = _capture(client, h, ox, enc, vector=stored)
    assert r.status_code == 422 and "from_device_storage" in r.json()["detail"]
    (n,) = _sql("SELECT count(*) FROM audit_events WHERE action = 'device.reading_refused' "
                "AND resource_id = %s", (enc["id"],))[0]
    assert n == 1
    # the phone's own parse, when sent, must equal the server's
    ok, _ = _capture(client, h, bp, enc, client_parsed=BP["expect"])
    assert ok.status_code == 201, ok.text
    # completed encounters are read-only
    assert client.post(f"{API}/encounters/{enc['id']}/complete", headers=h).status_code in (
        200, 201)
    closed, _ = _capture(client, h, bp, enc)
    assert closed.status_code == 409


def test_branch_bound_device(client):
    org, h, br = _clinic(client)
    _sql("UPDATE subscriptions SET limit_overrides = '{\"max_branches\": 5}' "
         "WHERE organization_id = %s", (org["organization"]["id"],))
    other = client.post(f"{API}/branches", json={"name": "Two", "code": "TWO"}, headers=h)
    assert other.status_code == 201, other.text
    dev = _device(client, h, branch_id=other.json()["id"])
    r, _ = _capture(client, h, dev, _encounter(client, h, br))
    assert r.status_code == 409 and "another branch" in r.json()["detail"]


def test_simulator_is_refused_when_disabled(client, clinic, monkeypatch):
    monkeypatch.setattr(get_settings(), "device_simulator_enabled", False)
    r, _ = _capture(client, clinic["h"], clinic["bp"], clinic["enc"])
    assert r.status_code == 403 and "simulator" in r.json()["detail"]
    assert client.post(f"{API}/devices", headers=clinic["h"], json={
        "kind": "bp_monitor", "label": "Sim", "is_simulator": True,
        "ble_address": "SIM-ABCDEF12"}).status_code == 403
    # and production cannot switch it on at all
    base = {"jwt_secret": "x" * 40, "database_url": "postgresql+psycopg2://a:b@h/d",
            "field_encryption_key": "k" * 44, "payments_provider": "razorpay"}
    with pytest.raises(ValueError, match="DEVICE_SIMULATOR"):
        Settings(**base, environment="production", device_simulator_enabled=True)
    assert Settings(**base, environment="production").device_simulator is False


# --- review ----------------------------------------------------------------------------
def test_accept_writes_vitals_through_the_normal_path(client, clinic):
    h = clinic["h"]
    r, _ = _capture(client, h, clinic["bp"], clinic["enc"])
    rid = r.json()["id"]
    assert client.post(f"{API}/device-readings/{rid}/accept", headers=h, json={
        "surface": "web", "confirm_patient": False}).status_code == 422
    ok = client.post(f"{API}/device-readings/{rid}/accept", headers=h,
                     json={"surface": "android", "confirm_patient": True,
                           "note": "repeat in 10 min"})
    assert ok.status_code == 200, ok.text
    d = ok.json()
    assert d["status"] == "accepted" and d["decision"]["surface"] == "android"
    enc = client.get(f"{API}/encounters/{clinic['enc']['id']}", headers=h).json()
    (v,) = enc["vitals"]
    assert (v["bp_systolic"], v["bp_diastolic"], v["pulse"]) == (133, 85, 72)
    assert v["device_reading_id"] == rid and v["id"] == d["decision"]["vitals_id"]
    assert "SIMULATED device reading" in v["notes"] and "irregular_pulse" in v["notes"]
    assert "repeat in 10 min" in v["notes"]
    # exactly one decision, ever
    assert client.post(f"{API}/device-readings/{rid}/accept", headers=h, json={
        "surface": "web", "confirm_patient": True}).status_code == 409
    assert client.post(f"{API}/device-readings/{rid}/reject", headers=h, json={
        "surface": "web", "reason": "changed my mind"}).status_code == 409
    actions = [a for (a,) in _sql("SELECT action FROM audit_events WHERE organization_id = %s "
                                  "ORDER BY id", (clinic["org"]["organization"]["id"],))]
    assert {"device.reading_captured", "encounter.vitals_recorded",
            "device.reading_accepted"} <= set(actions)


def test_spo2_accept_and_out_of_range_refusal(client, clinic):
    h = clinic["h"]
    r, _ = _capture(client, h, clinic["ox"], clinic["enc"], vector=SPOT)
    ok = client.post(f"{API}/device-readings/{r.json()['id']}/accept", headers=h,
                     json={"surface": "web", "confirm_patient": True})
    assert ok.status_code == 200, ok.text
    vit = client.get(f"{API}/encounters/{clinic['enc']['id']}", headers=h).json()["vitals"]
    assert [(x["spo2"], x["pulse"]) for x in vit] == [(97, 72)]
    # a parseable but physiologically impossible value never enters the record
    wild = "00" + "e803" + "4800"   # SpO2 1000 %, pulse 72
    r2, _ = _capture(client, h, clinic["ox"], clinic["enc"],
                     vector={"characteristic": "2a5e", "hex": wild})
    assert r2.status_code == 201
    bad = client.post(f"{API}/device-readings/{r2.json()['id']}/accept", headers=h,
                      json={"surface": "web", "confirm_patient": True})
    assert bad.status_code == 422 and "outside the range" in bad.json()["detail"]
    assert client.get(f"{API}/device-readings/{r2.json()['id']}",
                      headers=h).json()["status"] == "pending_review"


def test_reject_needs_a_reason_and_listing_filters(client, clinic):
    h, enc = clinic["h"], clinic["enc"]
    a, _ = _capture(client, h, clinic["bp"], enc)
    b, _ = _capture(client, h, clinic["ox"], enc, vector=SPOT)
    assert client.post(f"{API}/device-readings/{a.json()['id']}/reject", headers=h,
                       json={"surface": "web", "reason": ""}).status_code == 422
    rej = client.post(f"{API}/device-readings/{a.json()['id']}/reject", headers=h,
                      json={"surface": "web", "reason": "cuff was on the wrong arm"})
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    q = f"{API}/device-readings?encounter_id={enc['id']}"
    assert [x["id"] for x in client.get(q + "&status=pending_review", headers=h).json()] == [
        b.json()["id"]]
    assert len(client.get(q, headers=h).json()) == 2
    vit = client.get(f"{API}/encounters/{enc['id']}", headers=h).json()["vitals"]
    assert vit == []  # rejected and pending readings never touch the record


def test_concurrent_accepts_record_one_vitals_row(client, clinic):
    h = clinic["h"]
    r, _ = _capture(client, h, clinic["bp"], clinic["enc"])
    codes = []

    def accept():
        with TestClient(app) as c:
            codes.append(c.post(f"{API}/device-readings/{r.json()['id']}/accept", headers=h,
                                json={"surface": "web", "confirm_patient": True}).status_code)

    threads = [threading.Thread(target=accept) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(codes) == [200, 409, 409, 409]
    assert len(client.get(f"{API}/encounters/{clinic['enc']['id']}",
                          headers=h).json()["vitals"]) == 1


# --- database guarantees ---------------------------------------------------------------
def _app_cur(org_id):
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user="hms_app", password=APP_PASSWORD,
                            dbname=TEST_DB)
    cur = conn.cursor()
    cur.execute("SELECT set_config('app.current_org_id', %s, false)", (org_id,))
    return conn, cur


def test_append_only_immutable_identity_and_tenant_isolation(client, clinic):
    r, _ = _capture(client, clinic["h"], clinic["bp"], clinic["enc"])
    client.post(f"{API}/device-readings/{r.json()['id']}/reject", headers=clinic["h"],
                json={"surface": "web", "reason": "test reason"})
    org_id = clinic["org"]["organization"]["id"]
    for stmt in ("UPDATE device_readings SET raw_hex = '00'",
                 "DELETE FROM device_readings",
                 "UPDATE device_reading_decisions SET decision = 'accepted'",
                 "DELETE FROM device_reading_decisions",
                 "DELETE FROM medical_devices",
                 "UPDATE medical_devices SET address_hash = repeat('0', 64)"):
        conn, cur = _app_cur(org_id)
        with pytest.raises(psycopg2.Error):
            cur.execute(stmt)
        conn.rollback()
        conn.close()
    with pytest.raises(psycopg2.Error, match="append-only"):
        _sql("UPDATE device_readings SET raw_hex = '00' WHERE id = %s", (r.json()["id"],))
    with pytest.raises(psycopg2.Error, match="immutable"):
        _sql("UPDATE medical_devices SET model = 'other' WHERE id = %s", (clinic["bp"]["id"],))
    # another clinic sees nothing and cannot use the device
    _, h2, br2 = _clinic(client)
    assert client.get(f"{API}/device-readings/{r.json()['id']}", headers=h2).status_code == 404
    other_enc = _encounter(client, h2, br2)
    resp, _ = _capture(client, h2, clinic["bp"], other_enc)
    assert resp.status_code == 404
    conn, cur = _app_cur(str(uuid.uuid4()))
    cur.execute("SELECT count(*) FROM device_readings")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_phi_reads_are_audited(client, clinic):
    r, _ = _capture(client, clinic["h"], clinic["bp"], clinic["enc"])
    client.get(f"{API}/device-readings/{r.json()['id']}", headers=clinic["h"])
    (n,) = _sql("SELECT count(*) FROM audit_events WHERE action = 'phi.read' AND "
                "resource_type = 'device-readings' AND resource_id = %s", (r.json()["id"],))[0]
    assert n == 1
