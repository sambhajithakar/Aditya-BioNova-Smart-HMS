"""M8.2 medical devices: register (allow-list), capture readings, clinician
review. See docs/DEVICE_INTEGRATION.md.

Safety rules enforced here, whatever the client does:
* a reading is accepted only from an ACTIVE device on the tenant's list whose
  Bluetooth address matches, for an OPEN encounter (patient context first);
* the raw bytes are parsed HERE (app.devices.gatt); a phone whose parse
  differs is refused, as is any reading the device itself marks unusable;
* simulator readings only where the simulator is enabled (never production);
* nothing becomes part of the record without a clinician's explicit accept,
  which goes through the normal encounter-vitals path and its validation;
* readings and decisions are append-only; every step is audited.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auditing import record_event, record_security_event
from ..config import get_settings
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, get_current_principal, \
    require_permission
from ..devices import gatt
from ..models import Branch, EncounterVitals
from ..models_devices import DeviceReading, DeviceReadingDecision, MedicalDevice
from ..schemas import VitalsIn
from ..schemas_devices import AcceptIn, DecisionOut, DeviceIn, DeviceOut, ReadingIn, \
    ReadingOut, RejectIn
from ..timeutil import clinic_tz
from . import encounters as enc_router

router = APIRouter(tags=["devices"])

KIND_FOR_CHAR = {"2a35": "bp_monitor", "2a5e": "pulse_oximeter", "2a5f": "pulse_oximeter"}
CLOCK_SKEW = timedelta(minutes=10)
MAX_FUTURE = timedelta(minutes=5)
MAX_AGE = timedelta(hours=72)  # offline capture synced later


def address_hash(organization_id: uuid.UUID, address: str) -> str:
    """Per-tenant hash: the clear address is never stored or returned."""
    return hashlib.sha256(f"hms-device:{organization_id}:{address.upper()}".encode()).hexdigest()


def _audit(db: Session, principal: Principal, request: Request, action: str,
           resource_type: str, resource_id: str, metadata: dict) -> None:
    record_event(db, action=action, organization_id=str(principal.organization_id),
                 actor_user_id=str(principal.user_id), resource_type=resource_type,
                 resource_id=resource_id, metadata=metadata,
                 correlation_id=get_correlation_id(request), ip_address=get_client_ip(request))


def _need(principal: Principal, *keys: str) -> None:
    missing = [k for k in keys if k not in principal.permissions]
    if missing:
        raise HTTPException(403, detail=f"Missing permission: {missing[0]}")


def _reader_or_reviewer(principal: Principal = Depends(get_current_principal)) -> Principal:
    if not {"device.capture", "device.review"} & set(principal.permissions):
        raise HTTPException(403, detail="Missing permission: device.review")
    return principal


# --- device register -------------------------------------------------------------------
@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def register_device(payload: DeviceIn, request: Request,
                    principal: Principal = Depends(require_permission("device.manage")),
                    db: Session = Depends(get_db, scope="function")) -> MedicalDevice:
    is_sim_address = payload.ble_address.upper().startswith("SIM-")
    if payload.is_simulator != is_sim_address:
        raise HTTPException(422, detail="Simulator devices use a SIM- address; real devices "
                                        "use their Bluetooth address")
    if payload.is_simulator and not get_settings().device_simulator:
        raise HTTPException(403, detail="The device simulator is not enabled here")
    if payload.branch_id is not None:
        branch = db.get(Branch, payload.branch_id)
        if branch is None or branch.organization_id != principal.organization_id:
            raise HTTPException(404, detail="Branch not found")
    device = MedicalDevice(
        organization_id=principal.organization_id, branch_id=payload.branch_id,
        kind=payload.kind, label=payload.label, manufacturer=payload.manufacturer,
        model=payload.model, serial=payload.serial, firmware=payload.firmware,
        address_hash=address_hash(principal.organization_id, payload.ble_address),
        is_simulator=payload.is_simulator, registered_by=principal.user_id)
    db.add(device)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise HTTPException(409, detail="This device is already registered") from None
    _audit(db, principal, request, "device.registered", "medical_device", str(device.id),
           {"kind": device.kind, "model": device.model, "simulator": device.is_simulator})
    db.refresh(device)
    return device


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(include_retired: bool = False,
                 principal: Principal = Depends(require_permission("device.read")),
                 db: Session = Depends(get_db, scope="function")) -> list[MedicalDevice]:
    q = select(MedicalDevice).where(MedicalDevice.organization_id == principal.organization_id)
    if not include_retired:
        q = q.where(MedicalDevice.status == "active")
    return db.scalars(q.order_by(MedicalDevice.created_at)).all()


@router.post("/devices/{device_id}/retire", response_model=DeviceOut)
def retire_device(device_id: uuid.UUID, request: Request,
                  principal: Principal = Depends(require_permission("device.manage")),
                  db: Session = Depends(get_db, scope="function")) -> MedicalDevice:
    device = _device(db, principal, device_id)
    if device.status != "active":
        raise HTTPException(409, detail="Device is already retired")
    device.status, device.retired_at = "retired", datetime.now(timezone.utc)
    device.retired_by = principal.user_id
    db.flush()
    _audit(db, principal, request, "device.retired", "medical_device", str(device.id), {})
    return device


def _device(db: Session, principal: Principal, device_id: uuid.UUID) -> MedicalDevice:
    device = db.get(MedicalDevice, device_id)
    if device is None or device.organization_id != principal.organization_id:
        raise HTTPException(404, detail="Device not found")
    return device


# --- capture ------------------------------------------------------------------------------
def _device_time(parsed: dict) -> datetime | None:
    if not parsed.get("device_time"):
        return None
    # devices report local wall-clock time without a zone: the clinic's zone
    return datetime.fromisoformat(parsed["device_time"]).replace(tzinfo=clinic_tz())


@router.post("/device-readings", response_model=ReadingOut,
             status_code=status.HTTP_201_CREATED)
def capture_reading(payload: ReadingIn, request: Request, response: Response,
                    principal: Principal = Depends(require_permission("device.capture")),
                    db: Session = Depends(get_db, scope="function")) -> ReadingOut:
    existing = db.scalar(select(DeviceReading).where(
        DeviceReading.organization_id == principal.organization_id,
        DeviceReading.capture_id == payload.capture_id))
    if existing is not None:
        # sync replay of the same capture: same answer, nothing new stored
        if existing.raw_hex != payload.raw_hex.lower() or \
                existing.encounter_id != payload.encounter_id:
            raise HTTPException(409, detail="capture_id was already used for another reading")
        response.status_code = status.HTTP_200_OK
        return _out(db, existing)

    device = _device(db, principal, payload.device_id)
    if device.status != "active":
        raise HTTPException(403, detail="This device is retired; register it again to use it")
    if device.address_hash != address_hash(principal.organization_id, payload.ble_address):
        raise HTTPException(403, detail="The connected device is not the registered device")
    if KIND_FOR_CHAR[payload.characteristic] != device.kind:
        raise HTTPException(422, detail="This characteristic does not belong to this device "
                                        "type")
    simulated = payload.source == "simulator"
    if simulated != device.is_simulator:
        raise HTTPException(422, detail="Reading source does not match the device")
    if simulated and not get_settings().device_simulator:
        raise HTTPException(403, detail="The device simulator is not enabled here")

    enc = enc_router._get_encounter(db, principal, payload.encounter_id)
    enc_router._require_open(enc)
    if device.branch_id is not None and device.branch_id != enc.branch_id:
        raise HTTPException(409, detail="This device is registered to another branch")

    now = datetime.now(timezone.utc)
    if payload.captured_at > now + MAX_FUTURE:
        raise HTTPException(422, detail="captured_at is in the future")
    if payload.captured_at < now - MAX_AGE:
        raise HTTPException(422, detail="The reading is too old to record; measure again")

    raw_hex = payload.raw_hex.lower()
    try:
        parsed = gatt.parse(payload.characteristic, raw_hex)
    except gatt.GattError as exc:
        raise HTTPException(422, detail=f"Unusable device payload: {exc}") from None
    refusal = gatt.refusal_reason(parsed)
    if refusal:
        # own transaction: the 422 below rolls the request back
        record_security_event(
            action="device.reading_refused", organization_id=str(principal.organization_id),
            actor_user_id=str(principal.user_id), resource_type="encounter",
            resource_id=str(enc.id),
            metadata={"device_id": str(device.id), "reason": refusal,
                      "raw_sha256": hashlib.sha256(bytes.fromhex(raw_hex)).hexdigest()},
            correlation_id=get_correlation_id(request), ip_address=get_client_ip(request))
        raise HTTPException(422, detail=f"Reading not recorded: {refusal}")
    if payload.client_parsed is not None and payload.client_parsed != parsed:
        raise HTTPException(422, detail="The app's parse of this reading differs from the "
                                        "server's; update the app and measure again")

    device_time = _device_time(parsed)
    skew = "device_clock_not_set" in parsed["flags"] or (
        device_time is not None and abs(device_time - payload.captured_at) > CLOCK_SKEW)
    reading = DeviceReading(
        organization_id=principal.organization_id, device_id=device.id,
        patient_id=enc.patient_id, encounter_id=enc.id, capture_id=payload.capture_id,
        kind=parsed["kind"], characteristic=payload.characteristic, raw_hex=raw_hex,
        raw_sha256=hashlib.sha256(bytes.fromhex(raw_hex)).hexdigest(), parsed=parsed,
        source=payload.source, device_time=device_time, captured_at=payload.captured_at,
        clock_skew=skew, captured_by=principal.user_id, app_version=payload.app_version)
    db.add(reading)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:  # concurrent replay of the same capture
        raise HTTPException(409, detail="This capture is being recorded; retry") from None
    _audit(db, principal, request, "device.reading_captured", "device_reading", str(reading.id),
           {"encounter_id": str(enc.id), "device_id": str(device.id), "kind": reading.kind,
            "source": reading.source, "clock_skew": skew, "flags": parsed["flags"]})
    db.refresh(reading)
    return _out(db, reading)


# --- review -------------------------------------------------------------------------------
def _decision(db: Session, reading_id: uuid.UUID) -> DeviceReadingDecision | None:
    return db.scalar(select(DeviceReadingDecision).where(
        DeviceReadingDecision.reading_id == reading_id))


def _out(db: Session, r: DeviceReading) -> ReadingOut:
    device = db.get(MedicalDevice, r.device_id)
    d = _decision(db, r.id)
    p = r.parsed
    return ReadingOut(
        id=r.id, device_id=r.device_id, device_label=device.label,
        device_is_simulator=device.is_simulator, patient_id=r.patient_id,
        encounter_id=r.encounter_id, capture_id=r.capture_id, kind=r.kind,
        characteristic=r.characteristic, values=p["values"], exact=p["exact"], unit=p["unit"],
        flags=p["flags"], raw_hex=r.raw_hex, raw_sha256=r.raw_sha256, source=r.source,
        device_time=r.device_time, captured_at=r.captured_at, received_at=r.received_at,
        clock_skew=r.clock_skew, captured_by=r.captured_by, app_version=r.app_version,
        status="pending_review" if d is None else d.decision,
        decision=None if d is None else DecisionOut(
            decision=d.decision, reason=d.reason, surface=d.surface, vitals_id=d.vitals_id,
            decided_by=d.decided_by, decided_at=d.decided_at))


def _reading(db: Session, principal: Principal, reading_id: uuid.UUID) -> DeviceReading:
    r = db.get(DeviceReading, reading_id)
    if r is None or r.organization_id != principal.organization_id:
        raise HTTPException(404, detail="Device reading not found")
    return r


@router.get("/device-readings", response_model=list[ReadingOut])
def list_readings(encounter_id: uuid.UUID,
                  status_: str = Query("all", alias="status",
                                       pattern="^(all|pending_review|accepted|rejected)$"),
                  principal: Principal = Depends(_reader_or_reviewer),
                  db: Session = Depends(get_db, scope="function")) -> list[ReadingOut]:
    rows = db.scalars(select(DeviceReading).where(
        DeviceReading.organization_id == principal.organization_id,
        DeviceReading.encounter_id == encounter_id).order_by(DeviceReading.received_at)).all()
    out = [_out(db, r) for r in rows]
    return out if status_ == "all" else [o for o in out if o.status == status_]


@router.get("/device-readings/{reading_id}", response_model=ReadingOut)
def get_reading(reading_id: uuid.UUID, principal: Principal = Depends(_reader_or_reviewer),
                db: Session = Depends(get_db, scope="function")) -> ReadingOut:
    return _out(db, _reading(db, principal, reading_id))


def _lock_undecided(db: Session, principal: Principal, reading_id: uuid.UUID) -> DeviceReading:
    reading = _reading(db, principal, reading_id)
    # readings are append-only (no UPDATE grant, so no FOR UPDATE): serialise
    # decisions on the reading with an advisory lock, the unique index backs it
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
               {"k": f"device-reading:{reading.id}"})
    if _decision(db, reading.id) is not None:
        raise HTTPException(409, detail="This reading has already been reviewed")
    return reading


def _vitals_for(reading: DeviceReading, note: str) -> VitalsIn:
    v = reading.parsed["values"]
    fields = ({"bp_systolic": v["systolic"], "bp_diastolic": v["diastolic"],
               "pulse": v.get("pulse")} if reading.kind == "blood_pressure"
              else {"spo2": v["spo2"], "pulse": v["pulse"]})
    flags = ", ".join(reading.parsed["flags"])
    text_ = (f"{'SIMULATED ' if reading.source == 'simulator' else ''}device reading "
             f"{reading.id}" + (f"; device flags: {flags}" if flags else "")
             + ("; device clock differs" if reading.clock_skew else "")
             + (f"; {note}" if note else ""))
    try:
        return VitalsIn(**fields, notes=text_[:500])
    except ValidationError as exc:
        raise HTTPException(422, detail="A value is outside the range the record accepts; "
                                        "reject this reading and measure again or record it "
                                        "manually after checking the patient") from exc


@router.post("/device-readings/{reading_id}/accept", response_model=ReadingOut)
def accept_reading(reading_id: uuid.UUID, payload: AcceptIn, request: Request,
                   principal: Principal = Depends(require_permission("device.review")),
                   db: Session = Depends(get_db, scope="function")) -> ReadingOut:
    """The clinician confirms the reading belongs to this patient, now; it is
    written to the encounter's vitals through the normal vitals path (same
    validation, guards and audit event as manual entry)."""
    _need(principal, "encounter.write")
    if not payload.confirm_patient:
        raise HTTPException(422, detail="Confirm that this reading belongs to this patient")
    reading = _lock_undecided(db, principal, reading_id)
    if reading.source == "simulator" and not get_settings().device_simulator:
        raise HTTPException(403, detail="Simulated readings cannot enter the record here")
    vitals_in = _vitals_for(reading, payload.note)
    vitals = enc_router.record_vitals(encounter_id=reading.encounter_id, payload=vitals_in,
                                      request=request, principal=principal, db=db)
    row = db.get(EncounterVitals, vitals.id)
    row.device_reading_id = reading.id
    db.add(DeviceReadingDecision(organization_id=principal.organization_id,
                                 reading_id=reading.id, decision="accepted",
                                 reason=payload.note, surface=payload.surface,
                                 vitals_id=vitals.id, decided_by=principal.user_id))
    db.flush()
    _audit(db, principal, request, "device.reading_accepted", "device_reading",
           str(reading.id), {"encounter_id": str(reading.encounter_id),
                             "vitals_id": str(vitals.id), "surface": payload.surface})
    return _out(db, reading)


@router.post("/device-readings/{reading_id}/reject", response_model=ReadingOut)
def reject_reading(reading_id: uuid.UUID, payload: RejectIn, request: Request,
                   principal: Principal = Depends(require_permission("device.review")),
                   db: Session = Depends(get_db, scope="function")) -> ReadingOut:
    reading = _lock_undecided(db, principal, reading_id)
    db.add(DeviceReadingDecision(organization_id=principal.organization_id,
                                 reading_id=reading.id, decision="rejected",
                                 reason=payload.reason, surface=payload.surface,
                                 decided_by=principal.user_id))
    db.flush()
    _audit(db, principal, request, "device.reading_rejected", "device_reading",
           str(reading.id), {"encounter_id": str(reading.encounter_id),
                             "surface": payload.surface})
    return _out(db, reading)
