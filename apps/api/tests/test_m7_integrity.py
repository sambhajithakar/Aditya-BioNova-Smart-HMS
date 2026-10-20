"""M7.0 correctness hardening: regression tests for the audit findings.

Each test names the AUDIT_REPORT id it closes. DB guards are proven with raw
SQL as the non-owner ``hms_app`` role (same technique as the M3/M5 suites);
races are exercised with real concurrent requests through threads, where the
fix is a lock rather than a constraint.
"""
from __future__ import annotations

import itertools
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import psycopg2
import pytest
from app.timeutil import clinic_day_bounds, clinic_today
from tests.conftest import PG_HOST, PG_PORT, PG_SUPERUSER, TEST_DB, _auth
from tests.test_m3_clinical_billing import (
    _app_conn,
    _expect_blocked,
    _invoice,
    _patient,
    _set_org,
    _start_encounter,
)
from tests.test_m5_pharmacy_lab import (
    _dispense,
    _drug_id_exact,
    _fresh_org,
    _lab_order,
    _lab_test_id,
    _member,
    _receive,
)

_seq = itertools.count(1)


# --- helpers ----------------------------------------------------------------
def _owner_id(org) -> str:
    return org["auth"]["user"]["id"]


def _org_id(org) -> str:
    return org["auth"]["organization"]["id"]


def _super_conn():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_SUPERUSER,
                            dbname=TEST_DB)
    conn.autocommit = True
    return conn


def _rx(client, h, patient_id, items, **kw):
    body = {"patient_id": patient_id, "diagnosis_text": "M7 test", "items": items}
    body.update(kw)
    return client.post("/api/v1/prescriptions", json=body, headers=h)


def _rx_item(drug_id, **kw):
    item = {"drug_id": drug_id, "dose": "1 tab", "route": "oral",
            "frequency": "BD", "duration_days": 5}
    item.update(kw)
    return item


def _sign(client, h, rx_id, ack=False):
    return client.post(f"/api/v1/prescriptions/{rx_id}/sign",
                       json={"acknowledge_allergies": ack}, headers=h)


def _concurrently(*calls):
    """Start every call at the same moment (barrier) and return results in
    call order. Exceptions are re-raised in the main thread."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)
    errors: list = []

    def run(i, fn):
        try:
            barrier.wait(timeout=10)
            results[i] = fn()
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i, fn))
               for i, fn in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    if errors:
        raise errors[0]
    return results


def _issued_invoice(client, h, org, amount=1000.0):
    p = _patient(client, h)
    inv = _invoice(client, h, p, org["branch"], items=[
        {"item_type": "procedure", "description": "Dressing",
         "quantity": 1, "unit_price": amount, "tax_rate": 0}]).json()
    r = client.post(f"/api/v1/billing/invoices/{inv['id']}/issue", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# --- H1: signed Rx items immutable on INSERT ---------------------------------
def test_h1_signed_rx_rejects_item_insert_raw_sql(client, org_a):
    h = _auth(org_a["auth"])
    p = _patient(client, h)
    para = _drug_id_exact(client, h, "Paracetamol")
    ibu = _drug_id_exact(client, h, "Ibuprofen")
    draft = _rx(client, h, p["id"], [_rx_item(para)]).json()

    insert = ("INSERT INTO prescription_items (organization_id, prescription_id,"
              " drug_id, dose, frequency, duration_days)"
              " VALUES (%s, %s, %s, '1 tab', 'OD', 3)")
    conn = _app_conn()
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        # a DRAFT still takes new items (the draft/amend flows rely on it)
        cur.execute(insert, (_org_id(org_a), draft["id"], ibu))
        conn.rollback()
    finally:
        conn.close()

    assert _sign(client, h, draft["id"]).status_code == 200
    conn = _app_conn()
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        _expect_blocked(cur, insert, (_org_id(org_a), draft["id"], ibu),
                        "immutable")
        conn.rollback()
    finally:
        conn.close()

    # the amendment path (new version, new items) still works
    amended = client.post(f"/api/v1/prescriptions/{draft['id']}/amend", json={
        "reason": "Add analgesic", "items": [_rx_item(para), _rx_item(ibu)],
    }, headers=h)
    assert amended.status_code == 201, amended.text
    assert len(amended.json()["items"]) == 2
    conn = _app_conn()
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        _expect_blocked(cur, insert, (_org_id(org_a), draft["id"], ibu),
                        "immutable")  # superseded v1 too
        conn.rollback()
    finally:
        conn.close()


# --- H2: SpO2 < 85 with an escalation note ----------------------------------
def test_h2_low_spo2_accepted_with_escalation_note(client, org_a):
    h = _auth(org_a["auth"])
    n = next(_seq)
    ward = client.post("/api/v1/ipd/wards", json={
        "branch_id": org_a["branch"]["id"], "name": f"M7 Ward {n}",
        "code": f"M7W{n}"}, headers=h).json()
    bed = client.post("/api/v1/ipd/beds", json={"ward_id": ward["id"],
                                                "label": f"M7B{n}"},
                      headers=h).json()
    p = _patient(client, h)
    adm = client.post("/api/v1/ipd/admissions", json={
        "patient_id": p["id"], "ward_id": ward["id"], "bed_id": bed["id"],
        "reason": "Pneumonia"}, headers=h).json()
    url = f"/api/v1/ipd/admissions/{adm['id']}/nursing"

    assert client.post(url, json={"spo2": 84}, headers=h).status_code == 422
    assert client.post(url, json={"spo2": 84, "note": "ok"},
                       headers=h).status_code == 422  # not an escalation note
    ok = client.post(url, json={
        "note_type": "vitals", "spo2": 84,
        "note": "SpO2 84% on air: duty doctor informed, O2 2 L/min started"},
        headers=h)
    assert ok.status_code == 201, ok.text
    assert ok.json()["spo2"] == 84
    # physiologically impossible values stay rejected even with a note
    for bad in (49, 101):
        assert client.post(url, json={
            "spo2": bad, "note": "Escalated to the duty doctor"},
            headers=h).status_code == 422


# --- H3: merge carries clinical safety data ---------------------------------
def test_h3_merge_allergies_block_signing_on_survivor(client, org_a):
    h = _auth(org_a["auth"])
    amox = _drug_id_exact(client, h, "Amoxicillin 500")
    para = _drug_id_exact(client, h, "Paracetamol")
    retired = _patient(client, h, allergies="Penicillin; Sulfa drugs")
    survivor = _patient(client, h, allergies="sulfa drugs")

    # open work on the retired record + frozen history
    draft_on_retired = _rx(client, h, retired["id"], [_rx_item(para)]).json()
    signed_on_retired = _rx(client, h, retired["id"], [_rx_item(para)]).json()
    assert _sign(client, h, signed_on_retired["id"]).status_code == 200

    merged = client.post(f"/api/v1/patients/{retired['id']}/merge",
                         json={"target_patient_id": survivor["id"]}, headers=h)
    assert merged.status_code == 200, merged.text
    # union, case-insensitive de-duplication
    assert merged.json()["allergies"] == "sulfa drugs, Penicillin"

    # the allergy recorded ONLY on the retired record now blocks signing
    rx = _rx(client, h, survivor["id"], [_rx_item(amox)]).json()
    blocked = _sign(client, h, rx["id"])
    assert blocked.status_code == 409, blocked.text
    assert "Allergy" in blocked.json()["detail"]["message"]

    # open draft moved to the survivor; the signed Rx stays (frozen history)
    moved = client.get(f"/api/v1/prescriptions/{draft_on_retired['id']}",
                       headers=h).json()
    assert moved["patient_id"] == survivor["id"]
    kept = client.get(f"/api/v1/prescriptions/{signed_on_retired['id']}",
                      headers=h).json()
    assert kept["patient_id"] == retired["id"]
    events = client.get("/api/v1/audit-events", params={"limit": 100},
                        headers=h).json()["items"]
    ev = next(e for e in events if e["action"] == "patient.merged"
              and e["resource_id"] == retired["id"])
    assert ev["metadata"]["repointed"]["prescriptions"] == 1
    assert ev["metadata"]["kept_on_source"]["prescriptions"] == 1


def test_h3_gate_reads_records_merged_before_the_fix(client, org_a):
    """A merge recorded before M7.0 never copied allergies: the gate itself
    must look through merged_into_id."""
    h = _auth(org_a["auth"])
    amox = _drug_id_exact(client, h, "Amoxicillin 500")
    legacy = _patient(client, h, allergies="Penicillin")
    survivor = _patient(client, h)
    conn = _app_conn()
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        cur.execute("UPDATE patients SET status = 'merged', merged_into_id = %s"
                    " WHERE id = %s", (survivor["id"], legacy["id"]))
        conn.commit()
    finally:
        conn.close()
    rx = _rx(client, h, survivor["id"], [_rx_item(amox)]).json()
    assert _sign(client, h, rx["id"]).status_code == 409


# --- H4: dispense caps --------------------------------------------------------
def test_h4_dispense_quantity_caps_and_single_dispense(client, org_a):
    h = _auth(org_a["auth"])
    br = org_a["branch"]["id"]
    para = _drug_id_exact(client, h, "Paracetamol")
    ceti = _drug_id_exact(client, h, "Cetirizine")
    _receive(client, h, br, para, f"M7-H4-P{next(_seq)}", 100)
    _receive(client, h, br, ceti, f"M7-H4-C{next(_seq)}", 100)
    p = _patient(client, h)

    for bad in (0, 10001):
        assert _rx(client, h, p["id"], [_rx_item(para, dispense_quantity=bad)]
                   ).status_code == 422
    rx = _rx(client, h, p["id"], [_rx_item(para, dispense_quantity=10),
                                  _rx_item(ceti)]).json()
    assert rx["items"][0]["dispense_quantity"] == 10
    assert rx["items"][1]["dispense_quantity"] is None
    assert _sign(client, h, rx["id"]).status_code == 200

    assert _dispense(client, h, [(para, 6)], prescription_id=rx["id"]).status_code == 201
    over = _dispense(client, h, [(para, 5)], prescription_id=rx["id"])
    assert over.status_code == 409 and "exceeds" in over.json()["detail"]
    assert _dispense(client, h, [(para, 4)], prescription_id=rx["id"]).status_code == 201
    assert _dispense(client, h, [(para, 1)], prescription_id=rx["id"]).status_code == 409
    # no dispense_quantity: exactly one dispense
    assert _dispense(client, h, [(ceti, 3)], prescription_id=rx["id"]).status_code == 201
    assert _dispense(client, h, [(ceti, 1)], prescription_id=rx["id"]).status_code == 409

    # amending does NOT reset what v1 already handed out
    v2 = client.post(f"/api/v1/prescriptions/{rx['id']}/amend", json={
        "reason": "Extend course", "items": [_rx_item(para, dispense_quantity=12)],
    }, headers=h).json()
    assert _dispense(client, h, [(para, 3)], prescription_id=v2["id"]).status_code == 409
    assert _dispense(client, h, [(para, 2)], prescription_id=v2["id"]).status_code == 201


def test_h4_concurrent_dispenses_cannot_both_pass_the_cap(client, org_a):
    h = _auth(org_a["auth"])
    br = org_a["branch"]["id"]
    para = _drug_id_exact(client, h, "Paracetamol")
    _receive(client, h, br, para, f"M7-H4R-{next(_seq)}", 100)
    p = _patient(client, h)
    rx = _rx(client, h, p["id"], [_rx_item(para, dispense_quantity=10)]).json()
    assert _sign(client, h, rx["id"]).status_code == 200
    a, b = _concurrently(
        lambda: _dispense(client, h, [(para, 8)], prescription_id=rx["id"]),
        lambda: _dispense(client, h, [(para, 8)], prescription_id=rx["id"]),
    )
    assert sorted([a.status_code, b.status_code]) == [201, 409]


# --- H5 / contract: prescriber + catalog names --------------------------------
def test_rx_detail_has_prescriber_and_catalog_names_even_if_inactive(client, org_a):
    h = _auth(org_a["auth"])
    iver = _drug_id_exact(client, h, "Ivermectin")
    p = _patient(client, h)
    rx = _rx(client, h, p["id"], [_rx_item(iver, dispense_quantity=2)]).json()
    assert _sign(client, h, rx["id"]).status_code == 200

    sup = _super_conn()
    try:
        cur = sup.cursor()
        cur.execute("UPDATE users SET registration_number = 'MMC-2026-0042'"
                    " WHERE id = %s", (_owner_id(org_a),))
        cur.execute("UPDATE drug_catalog SET is_active = false WHERE id = %s",
                    (iver,))
        detail = client.get(f"/api/v1/prescriptions/{rx['id']}", headers=h)
    finally:
        cur.execute("UPDATE drug_catalog SET is_active = true WHERE id = %s",
                    (iver,))
        sup.close()
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["prescriber"] == {
        "user_id": _owner_id(org_a),
        "full_name": org_a["auth"]["user"]["full_name"],
        "registration_number": "MMC-2026-0042",
    }
    item = body["items"][0]
    assert item["drug_name"] == "Ivermectin 12 mg"
    assert item["generic_name"] == "Ivermectin"
    assert item["strength"] == "12 mg"
    assert item["dispense_quantity"] == 2
    # an unsigned draft has no prescriber yet
    draft = _rx(client, h, p["id"], [_rx_item(_drug_id_exact(client, h, "Paracetamol"))])
    assert draft.json()["prescriber"] is None


# --- C2 + H7: lab order items -------------------------------------------------
def test_lab_order_items_gate_results_and_release(client, org_a):
    h = _auth(org_a["auth"])
    br = org_a["branch"]["id"]
    doctor = _member(client, h, "dr-m7-lab@clinic-a.example.com", "doctor")
    p = _patient(client, h)
    cbc, fbs, lipid = (_lab_test_id(client, h, c) for c in ("CBC", "FBS", "LIPID"))

    od = _lab_order(client, h, p["id"], br, [cbc, fbs]).json()
    assert {(i["test_code"], i["status"]) for i in od["items"]} == {
        ("CBC", "ordered"), ("FBS", "ordered")}
    assert all(i["test_name"] for i in od["items"])
    listed = client.get("/api/v1/lab/orders", params={"patient_id": p["id"]},
                        headers=h).json()["items"]
    assert len(listed[0]["items"]) == 2

    url = f"/api/v1/lab/orders/{od['id']}"
    blood = client.post(f"{url}/specimens", json={"specimen_type": "blood"},
                        headers=h).json()
    # a test that was never ordered cannot be resulted
    stray = client.post(f"{url}/results", json={"results": [
        {"test_id": lipid, "value_numeric": 180}]}, headers=h)
    assert stray.status_code == 422 and "not on this order" in stray.json()["detail"]
    # empty results are rejected
    empty = client.post(f"{url}/results", json={"results": [
        {"test_id": cbc, "value_text": "   "}]}, headers=h)
    assert empty.status_code == 422

    imported = client.post(f"{url}/results", json={
        "specimen_id": blood["id"],
        "results": [{"test_id": cbc, "value_numeric": 12.5}]}, headers=h).json()
    assert {i["test_code"]: i["status"] for i in imported["items"]} == {
        "CBC": "resulted", "FBS": "ordered"}
    cbc_row = imported["results"][0]["id"]
    assert client.post(f"/api/v1/lab/results/{cbc_row}/verify",
                       headers=doctor).status_code == 200
    assert client.post(f"/api/v1/lab/results/{cbc_row}/release",
                       headers=doctor).status_code == 200
    # FBS was ordered but has no result: the order is NOT released
    assert client.get(url, headers=h).json()["status"] == "in_progress"

    conn = _app_conn()
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        _expect_blocked(cur, "UPDATE lab_orders SET status = 'released'"
                             " WHERE id = %s", (od["id"],),
                        "missing a released result")
        _expect_blocked(cur, "DELETE FROM lab_order_items WHERE order_id = %s",
                        (od["id"],), ("permission denied", "permanent"))
        _expect_blocked(cur, "UPDATE lab_order_items SET test_id = %s"
                             " WHERE order_id = %s", (lipid, od["id"]), "frozen")
        conn.rollback()
    finally:
        conn.close()

    # rejected specimen: re-collect on the same order
    assert client.post(f"/api/v1/lab/specimens/{blood['id']}/reject",
                       json={"reason": "Clotted sample"}, headers=h).status_code == 200
    no_specimen = client.post(f"{url}/results", json={"results": [
        {"test_id": fbs, "value_numeric": 92}]}, headers=h)
    assert no_specimen.status_code == 409
    redraw = client.post(f"{url}/specimens", json={"specimen_type": "blood"},
                         headers=h)
    assert redraw.status_code == 201, redraw.text
    fbs_res = client.post(f"{url}/results", json={
        "specimen_id": redraw.json()["id"],
        "results": [{"test_id": fbs, "value_numeric": 92}]}, headers=h).json()
    fbs_row = next(r["id"] for r in fbs_res["results"] if r["test_id"] == fbs)
    assert client.post(f"/api/v1/lab/results/{fbs_row}/verify",
                       headers=doctor).status_code == 200
    assert client.post(f"/api/v1/lab/results/{fbs_row}/release",
                       headers=doctor).status_code == 200
    final = client.get(url, headers=h).json()
    assert final["status"] == "released"
    assert len(final["specimens"]) == 2


def test_lab_cancel_marks_items_cancelled(client, org_a):
    h = _auth(org_a["auth"])
    p = _patient(client, h)
    cbc = _lab_test_id(client, h, "CBC")
    od = _lab_order(client, h, p["id"], org_a["branch"]["id"], [cbc]).json()
    r = client.post(f"/api/v1/lab/orders/{od['id']}/cancel",
                    json={"reason": "Ordered in error"}, headers=h)
    assert r.status_code == 200
    assert [i["status"] for i in r.json()["items"]] == ["cancelled"]


def test_lab_barcodes_unique_under_concurrent_collection(client, org_a):
    h = _auth(org_a["auth"])
    p = _patient(client, h)
    cbc = _lab_test_id(client, h, "CBC")
    orders = [_lab_order(client, h, p["id"], org_a["branch"]["id"], [cbc]).json()
              for _ in range(3)]
    results = _concurrently(*[
        (lambda o=o: client.post(f"/api/v1/lab/orders/{o['id']}/specimens",
                                 json={"specimen_type": "blood"}, headers=h))
        for o in orders
    ])
    assert [r.status_code for r in results] == [201, 201, 201]
    assert len({r.json()["barcode"] for r in results}) == 3


# --- H8: report revenue vs refunds -------------------------------------------
def test_h8_refunded_payment_reports_revenue_refund_and_zero_net(client):
    h, branch_id = _fresh_org(client, "m7-report-org")
    inv = _issued_invoice(client, h, {"branch": {"id": branch_id}}, 1000)
    pay = client.post(f"/api/v1/billing/invoices/{inv['id']}/payments",
                      json={"amount": 1000, "method": "cash"}, headers=h).json()
    assert client.post(f"/api/v1/billing/payments/{pay['id']}/refund",
                       json={"amount": 1000, "reason": "Procedure cancelled"},
                       headers=h).status_code == 201
    today = clinic_today()
    r = client.get("/api/v1/reports/summary",
                   params={"from": today.isoformat(), "to": today.isoformat()},
                   headers=h)
    assert r.status_code == 200, r.text
    fin = r.json()["finance"]
    assert float(fin["revenue"]) == 1000
    assert float(fin["refunds"]) == 1000
    assert float(fin["net"]) == 0


# --- H9: payments under concurrency + reservation ----------------------------
def test_h9_pending_sandbox_payments_reserve_the_balance(client, org_a):
    h = _auth(org_a["auth"])
    inv = _issued_invoice(client, h, org_a, 500)
    url = f"/api/v1/billing/invoices/{inv['id']}/payments"
    first = client.post(url, json={"amount": 500, "method": "upi",
                                   "gateway": "sandbox"}, headers=h)
    assert first.status_code == 201 and first.json()["status"] == "pending"
    # the pending 500 is reserved: a second full-balance payment is refused
    second = client.post(url, json={"amount": 500, "method": "upi",
                                    "gateway": "sandbox"}, headers=h)
    assert second.status_code == 422 and "reserved" in second.json()["detail"]
    # and the invoice cannot be voided under a pending payment
    assert client.post(f"/api/v1/billing/invoices/{inv['id']}/void",
                       headers=h).status_code == 409
    ok = client.post(f"/api/v1/billing/payments/{first.json()['id']}/confirm",
                     headers=h)
    assert ok.status_code == 200
    final = client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=h).json()
    assert final["status"] == "paid" and float(final["amount_paid"]) == 500


def test_h9_confirm_rechecks_balance_and_db_bounds_amount_paid(client, org_a):
    """Two pending payments for the full total (planted with raw SQL, as an
    old build or a gateway race would leave them): only one can settle."""
    h = _auth(org_a["auth"])
    inv = _issued_invoice(client, h, org_a, 300)
    conn = _app_conn()
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        ids = []
        for _ in range(2):
            cur.execute(
                "INSERT INTO payments (organization_id, invoice_id, amount,"
                " method, gateway, status) VALUES (%s, %s, 300, 'upi',"
                " 'sandbox', 'pending') RETURNING id",
                (_org_id(org_a), inv["id"]))
            ids.append(str(cur.fetchone()[0]))
        conn.commit()
    finally:
        conn.close()
    assert client.post(f"/api/v1/billing/payments/{ids[0]}/confirm",
                       headers=h).status_code == 200
    again = client.post(f"/api/v1/billing/payments/{ids[1]}/confirm", headers=h)
    assert again.status_code == 409
    final = client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=h).json()
    assert float(final["amount_paid"]) == 300

    conn = _app_conn()
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        _expect_blocked(cur, "UPDATE invoices SET amount_paid = total + 1"
                             " WHERE id = %s", (inv["id"],),
                        "ck_inv_amount_paid_bound")
        conn.rollback()
    finally:
        conn.close()


def test_h9_concurrent_payments_never_overpay(client, org_a):
    h = _auth(org_a["auth"])
    inv = _issued_invoice(client, h, org_a, 750)
    url = f"/api/v1/billing/invoices/{inv['id']}/payments"
    results = _concurrently(*[
        (lambda: client.post(url, json={"amount": 750, "method": "cash"},
                             headers=h))
        for _ in range(3)
    ])
    assert sorted(r.status_code for r in results) == [201, 422, 422]
    receipt = client.get(f"/api/v1/billing/invoices/{inv['id']}/receipt",
                         headers=h)
    assert receipt.status_code == 200, receipt.text  # ledger consistent
    assert float(receipt.json()["invoice"]["amount_paid"]) == 750


def test_h9_concurrent_refunds_never_exceed_the_payment(client, org_a):
    h = _auth(org_a["auth"])
    inv = _issued_invoice(client, h, org_a, 400)
    pay = client.post(f"/api/v1/billing/invoices/{inv['id']}/payments",
                      json={"amount": 400, "method": "cash"}, headers=h).json()
    url = f"/api/v1/billing/payments/{pay['id']}/refund"
    results = _concurrently(*[
        (lambda: client.post(url, json={"amount": 300, "reason": "Duplicate"},
                             headers=h))
        for _ in range(2)
    ])
    assert sorted(r.status_code for r in results) == [201, 422]


# --- H11 / H12: idempotency ---------------------------------------------------
def test_h11_idempotent_prescription_and_invoice_creation(client, org_a):
    h = _auth(org_a["auth"])
    p = _patient(client, h)
    para = _drug_id_exact(client, h, "Paracetamol")
    key = {**h, "Idempotency-Key": f"m7-rx-{uuid.uuid4()}"}
    body = {"patient_id": p["id"], "items": [_rx_item(para)]}
    r1 = client.post("/api/v1/prescriptions", json=body, headers=key)
    r2 = client.post("/api/v1/prescriptions", json=body, headers=key)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    listed = client.get("/api/v1/prescriptions", params={"patient_id": p["id"]},
                        headers=h).json()
    assert listed["total"] == 1
    other = client.post("/api/v1/prescriptions",
                        json={**body, "diagnosis_text": "changed"}, headers=key)
    assert other.status_code == 409

    ikey = {**h, "Idempotency-Key": f"m7-inv-{uuid.uuid4()}"}
    inv_body = {"patient_id": p["id"], "branch_id": org_a["branch"]["id"],
                "items": [{"item_type": "consultation", "description": "OPD",
                           "quantity": 1, "unit_price": 300, "tax_rate": 0}]}
    i1 = client.post("/api/v1/billing/invoices", json=inv_body, headers=ikey)
    i2 = client.post("/api/v1/billing/invoices", json=inv_body, headers=ikey)
    assert i1.status_code == i2.status_code == 201
    assert i1.json()["id"] == i2.json()["id"]
    assert client.get("/api/v1/billing/invoices", params={"patient_id": p["id"]},
                      headers=h).json()["total"] == 1


def test_h12_overlong_key_rejected_not_truncated(client, org_a):
    h = _auth(org_a["auth"])
    long_key = "k" * 101
    r = client.post("/api/v1/patients", json={
        "full_name": "Long Key Patient", "gender": "female",
        "allow_duplicates": True}, headers={**h, "Idempotency-Key": long_key})
    assert r.status_code == 422


def test_h12_concurrent_same_key_creates_one_record(client, org_a):
    h = _auth(org_a["auth"])
    name = f"Race Patient {uuid.uuid4().hex[:8]}"
    hk = {**h, "Idempotency-Key": f"m7-race-{uuid.uuid4()}"}
    body = {"full_name": name, "gender": "male", "allow_duplicates": True}
    results = _concurrently(*[
        (lambda: client.post("/api/v1/patients", json=body, headers=hk))
        for _ in range(3)
    ])
    assert [r.status_code for r in results] == [201, 201, 201]
    assert len({r.json()["id"] for r in results}) == 1
    found = client.get("/api/v1/patients", params={"q": name}, headers=h).json()
    assert found["total"] == 1
    # every response points at the record that actually exists
    assert client.get(f"/api/v1/patients/{results[0].json()['id']}",
                      headers=h).status_code == 200


# --- invoice / payment / encounter immutability (raw SQL) --------------------
def test_financial_and_encounter_records_are_append_only_raw_sql(client, org_a):
    h = _auth(org_a["auth"])
    inv = _issued_invoice(client, h, org_a, 200)
    pay = client.post(f"/api/v1/billing/invoices/{inv['id']}/payments",
                      json={"amount": 200, "method": "cash"}, headers=h).json()
    refund = client.post(f"/api/v1/billing/payments/{pay['id']}/refund",
                         json={"amount": 50, "reason": "Partial refund"},
                         headers=h).json()
    p = _patient(client, h)
    enc = _start_encounter(client, h, p, org_a["branch"]).json()
    done = client.post(f"/api/v1/encounters/{enc['id']}/complete", headers=h)
    assert done.status_code == 200, done.text

    conn = _app_conn()
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        _expect_blocked(cur, "UPDATE invoices SET status = 'draft' WHERE id = %s",
                        (inv["id"],), "illegal status change")
        _expect_blocked(cur, "DELETE FROM invoices WHERE id = %s", (inv["id"],),
                        "cannot be deleted")
        _expect_blocked(cur, "UPDATE payments SET amount = 1 WHERE id = %s",
                        (pay["id"],), "append-only")
        _expect_blocked(cur, "UPDATE payments SET invoice_id = %s WHERE id = %s",
                        (str(uuid.uuid4()), pay["id"]), "append-only")
        _expect_blocked(cur, "UPDATE payments SET status = 'pending' WHERE id = %s",
                        (pay["id"],), "illegal status change")
        _expect_blocked(cur, "DELETE FROM payments WHERE id = %s", (pay["id"],),
                        "append-only")
        _expect_blocked(cur, "UPDATE refunds SET amount = 1 WHERE id = %s",
                        (refund["id"],), "append-only")
        _expect_blocked(cur, "DELETE FROM refunds WHERE id = %s", (refund["id"],),
                        "append-only")
        _expect_blocked(cur, "DELETE FROM encounters WHERE id = %s", (enc["id"],),
                        "cannot be deleted")
        conn.rollback()
    finally:
        conn.close()


# --- GST on the post-discount value --------------------------------------------
def test_gst_charged_on_discounted_value_unit():
    from app.services.billing import compute_invoice_totals

    # 200 @0% + 15 x 4.50 @12%, discount 50 -> pro rata 37.38 / 12.62
    subtotal, disc, tax, total, lines = compute_invoice_totals(
        [(1, 200, 0), (15, 4.5, 12)], 50)
    assert (subtotal, disc, tax, total) == (
        Decimal("267.50"), Decimal("50.00"), Decimal("6.59"), Decimal("224.09"))
    assert lines == [Decimal("200.00"), Decimal("74.09")]
    assert sum(lines) - disc == total

    # full discount: nothing taxable remains
    _, _, tax, total, _ = compute_invoice_totals([(1, 0.01, 18), (1, 100, 18)],
                                                 100.01)
    assert (tax, total) == (Decimal("0.00"), Decimal("0.00"))

    # allocations always sum to the discount exactly (odd paise, 3 lines)
    _, _, tax, total, _ = compute_invoice_totals(
        [(1, 33.33, 5), (1, 33.33, 5), (1, 33.34, 5)], 10)
    assert tax == Decimal("4.50") and total == Decimal("94.50")
    with pytest.raises(Exception):
        compute_invoice_totals([(1, 10, 0)], 10.01)


# --- cross-tenant foreign ids ----------------------------------------------------
def test_cross_tenant_foreign_ids_are_rejected(client, org_a, org_b):
    h = _auth(org_a["auth"])
    hb = _auth(org_b["auth"])
    br_a = org_a["branch"]["id"]
    br_b = org_b["branch"]["id"]
    p = _patient(client, h)
    other = _patient(client, h)
    pb = _patient(client, hb)
    start = datetime(2027, 1, 5, 4, 0, tzinfo=timezone.utc)
    appt_b = client.post("/api/v1/appointments", json={
        "patient_id": pb["id"], "branch_id": br_b,
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(minutes=15)).isoformat()}, headers=hb)
    assert appt_b.status_code == 201, appt_b.text
    enc_b = _start_encounter(client, hb, pb, org_b["branch"]).json()
    enc_other = _start_encounter(client, h, other, org_a["branch"]).json()
    para = _drug_id_exact(client, h, "Paracetamol")
    cbc = _lab_test_id(client, h, "CBC")
    user_b = _owner_id(org_b)

    checks = [
        ("POST", "/api/v1/pharmacy/stock/batches", {
            "branch_id": br_b, "drug_id": para, "batch_number": "M7-XT-1",
            "expiry_date": (date.today() + timedelta(days=90)).isoformat(),
            "quantity": 5}, 404),
        ("POST", "/api/v1/lab/orders", {
            "patient_id": p["id"], "branch_id": br_b, "test_ids": [cbc]}, 404),
        ("POST", "/api/v1/lab/orders", {
            "patient_id": p["id"], "branch_id": br_a, "test_ids": [cbc],
            "encounter_id": enc_b["id"]}, 404),
        ("POST", "/api/v1/lab/orders", {
            "patient_id": p["id"], "branch_id": br_a, "test_ids": [cbc],
            "encounter_id": enc_other["id"]}, 422),
        ("POST", "/api/v1/ipd/wards", {
            "branch_id": br_b, "name": "Foreign", "code": "XT1"}, 404),
        ("POST", "/api/v1/inventory/items", {
            "branch_id": br_b, "name": "Foreign gloves"}, 404),
        ("POST", "/api/v1/opd/queue", {
            "patient_id": p["id"], "branch_id": br_a,
            "appointment_id": appt_b.json()["id"]}, 404),
        ("POST", "/api/v1/encounters", {
            "patient_id": p["id"], "branch_id": br_a,
            "appointment_id": appt_b.json()["id"]}, 404),
        ("POST", "/api/v1/encounters", {
            "patient_id": p["id"], "branch_id": br_a,
            "provider_user_id": user_b}, 422),
        ("POST", "/api/v1/prescriptions", {
            "patient_id": p["id"], "encounter_id": enc_b["id"],
            "items": [_rx_item(para)]}, 404),
        ("POST", "/api/v1/prescriptions", {
            "patient_id": p["id"], "encounter_id": enc_other["id"],
            "items": [_rx_item(para)]}, 422),
        ("POST", "/api/v1/billing/invoices", {
            "patient_id": p["id"], "branch_id": br_a,
            "encounter_id": enc_other["id"],
            "items": [{"item_type": "other", "description": "x",
                       "quantity": 1, "unit_price": 1}]}, 422),
        ("POST", "/api/v1/appointments", {
            "patient_id": p["id"], "branch_id": br_a,
            "provider_user_id": user_b,
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=10)).isoformat()}, 422),
    ]
    for method, path, body, expected in checks:
        r = client.request(method, path, json=body, headers=h)
        assert r.status_code == expected, (path, body, r.status_code, r.text)

    n = next(_seq)
    ward = client.post("/api/v1/ipd/wards", json={
        "branch_id": br_a, "name": f"M7 XT Ward {n}", "code": f"M7X{n}"},
        headers=h).json()
    bed = client.post("/api/v1/ipd/beds", json={"ward_id": ward["id"],
                                                "label": f"X{n}"},
                      headers=h).json()
    adm = client.post("/api/v1/ipd/admissions", json={
        "patient_id": p["id"], "ward_id": ward["id"], "bed_id": bed["id"],
        "reason": "Observation", "attending_user_id": user_b}, headers=h)
    assert adm.status_code == 422


# --- races: appointments + OPD queue ------------------------------------------
def test_provider_double_booking_race(client, org_a):
    h = _auth(org_a["auth"])
    p1, p2 = _patient(client, h), _patient(client, h)
    start = datetime(2027, 2, 1, 5, 0, tzinfo=timezone.utc) + timedelta(
        hours=next(_seq))

    def book(patient):
        return client.post("/api/v1/appointments", json={
            "patient_id": patient["id"], "branch_id": org_a["branch"]["id"],
            "provider_user_id": _owner_id(org_a),
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=20)).isoformat()}, headers=h)

    a, b = _concurrently(lambda: book(p1), lambda: book(p2))
    assert sorted([a.status_code, b.status_code]) == [201, 409]


def test_opd_queue_duplicate_active_entry_race(client, org_a):
    h = _auth(org_a["auth"])
    p = _patient(client, h)
    body = {"patient_id": p["id"], "branch_id": org_a["branch"]["id"]}
    a, b = _concurrently(
        lambda: client.post("/api/v1/opd/queue", json=body, headers=h),
        lambda: client.post("/api/v1/opd/queue", json=body, headers=h),
    )
    assert sorted([a.status_code, b.status_code]) == [201, 409]
    entry = a.json() if a.status_code == 201 else b.json()
    # the service day is the CLINIC day (IST), not the UTC date
    # (QueueEntryOut types service_date as datetime: compare the date part)
    assert entry["service_date"][:10] == clinic_today().isoformat()

    conn = _app_conn()  # DB backstop: one active entry per patient per day
    try:
        cur = conn.cursor()
        _set_org(cur, _org_id(org_a))
        _expect_blocked(
            cur,
            "INSERT INTO opd_queue (organization_id, branch_id, patient_id,"
            " service_date, token_number) VALUES (%s, %s, %s, %s, 9999)",
            (_org_id(org_a), org_a["branch"]["id"], p["id"],
             entry["service_date"][:10]),
            "uq_queue_one_active")
        conn.rollback()
    finally:
        conn.close()


# --- IST day boundaries -------------------------------------------------------
def test_clinic_day_is_ist_not_utc():
    late_utc = datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc)  # 00:30 IST
    assert clinic_today(late_utc) == date(2026, 10, 21)
    assert clinic_today(datetime(2026, 10, 20, 18, 29, tzinfo=timezone.utc)) == \
        date(2026, 10, 20)
    start, end = clinic_day_bounds(date(2026, 10, 21))
    assert start == datetime(2026, 10, 20, 18, 30, tzinfo=timezone.utc)
    assert end - start == timedelta(days=1)
