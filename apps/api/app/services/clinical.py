"""M2 clinical helpers: UHID issuance, duplicate detection, idempotency.

UHID
----
Per-tenant sequential identifier ``P0000001`` (7 digits, unique inside the
organization only). Issuance takes a per-organization advisory transaction
lock so two concurrent registrations can never receive the same number; the
``uq_patient_org_uhid`` constraint remains the hard backstop (one retry on
IntegrityError).

Duplicate detection (supervised)
-------------------------------
Registration searches the tenant's own patients by normalized phone OR by
(lower(full_name), date_of_birth). Candidates are returned to the caller;
creation proceeds only if the operator confirms (``allow_duplicates``) —
matching the blueprint rule that patient merge/dedupe is a supervised,
audited action, never automatic.

Idempotency
-----------
POSTs may carry an ``Idempotency-Key`` header (max 100 chars, else 422). The
first request claims the key, then stores its response (status + JSON) keyed
by (organization, key) in the same transaction; a retry with the same
payload replays the stored response instead of creating a second record, and
a retry with a *different* payload is rejected with 409. Concurrent requests
with one key serialize on the key's unique index (see ``idempotent_replay``).
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import IdempotencyKey, Patient

UHID_ATTEMPTS = 3


def normalize_phone(value: str | None) -> str | None:
    """Digits only, drop a leading country code 91 / trunk 0 (10-digit base)."""
    if not value:
        return None
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def next_uhid(db: Session, organization_id: uuid.UUID) -> str:
    """Allocate the next UHID inside the tenant (serialized by advisory lock)."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"uhid:{organization_id}"},
    )
    last = db.scalar(
        select(func.max(Patient.uhid)).where(
            Patient.organization_id == organization_id
        )
    )
    seq = int(last[1:]) + 1 if last else 1
    return f"P{seq:07d}"


def create_patient_uhid_retry(
    db: Session, organization_id: uuid.UUID
) -> str:
    """Retry once on the (extremely unlikely) UHID race."""
    for attempt in range(UHID_ATTEMPTS):
        uhid = next_uhid(db, organization_id)
        exists = db.scalar(
            select(Patient.id).where(
                Patient.organization_id == organization_id,
                Patient.uhid == uhid,
            )
        )
        if exists is None:
            return uhid
        if attempt == UHID_ATTEMPTS - 1:
            raise HTTPException(status_code=503, detail="UHID allocation busy, retry")
    raise AssertionError("unreachable")


def find_duplicates(
    db: Session,
    *,
    organization_id: uuid.UUID,
    full_name: str,
    phone: str | None,
    date_of_birth,
    exclude_id: uuid.UUID | None = None,
) -> list[tuple[Patient, list[str]]]:
    """Return (patient, matched_fields) pairs from the SAME tenant only."""
    results: dict[uuid.UUID, tuple[Patient, list[str]]] = {}

    if phone:
        rows = db.scalars(
            select(Patient).where(
                Patient.organization_id == organization_id,
                func.lower(func.coalesce(Patient.phone, "")) == phone,
            )
        ).all()
        for row in rows:
            if exclude_id and row.id == exclude_id:
                continue
            results[row.id] = (row, ["phone"])

    if full_name and date_of_birth is not None:
        rows = db.scalars(
            select(Patient).where(
                Patient.organization_id == organization_id,
                func.lower(Patient.full_name) == full_name.lower(),
                Patient.date_of_birth == date_of_birth,
            )
        ).all()
        for row in rows:
            if exclude_id and row.id == exclude_id:
                continue
            if row.id in results:
                results[row.id][1].append("name+dob")
            else:
                results[row.id] = (row, ["name+dob"])

    return list(results.values())


# --- merge: clinical safety data -------------------------------------------
_ALLERGY_SPLIT = re.compile(r"[,;\n]+")
MERGE_CHAIN_DEPTH = 20


def union_allergies(*texts: str) -> str:
    """Union free-text allergy lists (comma/semicolon/newline separated),
    de-duplicated case-insensitively, first spelling and order kept."""
    seen: dict[str, str] = {}
    for text_value in texts:
        for part in _ALLERGY_SPLIT.split(text_value or ""):
            entry = part.strip()
            if entry and entry.lower() not in seen:
                seen[entry.lower()] = entry
    return ", ".join(seen.values())


def effective_allergies(db: Session, patient: Patient) -> str:
    """The patient's allergies PLUS those of every record merged into it
    (transitively). Merges copy allergies onto the survivor, but records
    merged before M7.0 did not, so the safety gate never relies on the copy
    alone."""
    texts = [patient.allergies]
    frontier = [patient.id]
    seen = {patient.id}
    for _ in range(MERGE_CHAIN_DEPTH):
        if not frontier:
            break
        rows = db.execute(
            select(Patient.id, Patient.allergies).where(
                Patient.organization_id == patient.organization_id,
                Patient.merged_into_id.in_(frontier),
            )
        ).all()
        frontier = [r[0] for r in rows if r[0] not in seen]
        seen.update(frontier)
        texts.extend(r[1] for r in rows)
    return union_allergies(*texts)


# --- idempotency ------------------------------------------------------------
IDEMPOTENCY_KEY_MAX = 100  # idempotency_keys.idempotency_key is varchar(100)
_PENDING_STATUS = 0  # placeholder until idempotent_store records the response


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_key(key: str) -> None:
    if len(key) > IDEMPOTENCY_KEY_MAX:
        # never truncate: two different long keys would collide
        raise HTTPException(
            status_code=422,
            detail=f"Idempotency-Key longer than {IDEMPOTENCY_KEY_MAX} characters",
        )


def idempotent_replay(
    db: Session,
    *,
    organization_id: uuid.UUID,
    key: str | None,
    endpoint: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Claim ``key`` for this request, or return the stored response.

    The key row is CLAIMED up-front with ``INSERT .. ON CONFLICT DO NOTHING``
    inside a SAVEPOINT: a concurrent request with the same key blocks on the
    unique index until the first transaction finishes, then replays its
    stored response (or gets 409 for a different payload). The outer
    transaction is never rolled back, so the record this request creates
    and its audit event stay consistent with the response it returns. If the
    claiming request fails, its transaction rolls back and the claim with it.

    Raises 409 when the same key is reused with a DIFFERENT payload and 422
    when the key is longer than the column.
    """
    if not key:
        return None
    _check_key(key)
    request_hash = _hash(payload)
    with db.begin_nested():
        claimed = db.scalar(
            pg_insert(IdempotencyKey)
            .values(
                id=uuid.uuid4(),
                organization_id=organization_id,
                idempotency_key=key,
                endpoint=endpoint,
                request_hash=request_hash,
                response_status=_PENDING_STATUS,
                response_body={},
            )
            .on_conflict_do_nothing(constraint="uq_idem_org_key")
            .returning(IdempotencyKey.id)
        )
    if claimed is not None:
        return None  # first use: the caller does the work, then stores

    row = db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.organization_id == organization_id,
            IdempotencyKey.idempotency_key == key,
        )
    )
    if row is None:  # pragma: no cover - claim vanished (rolled back) mid-race
        raise HTTPException(status_code=409, detail="Idempotency-Key busy, retry")
    if row.endpoint != endpoint or row.request_hash != request_hash:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key reused with a different payload",
        )
    if row.response_status == _PENDING_STATUS:
        raise HTTPException(
            status_code=409, detail="A request with this Idempotency-Key is in progress"
        )
    return {
        "replayed": True,
        "status": row.response_status,
        "body": row.response_body,
    }


def idempotent_store(
    db: Session,
    *,
    organization_id: uuid.UUID,
    key: str | None,
    endpoint: str,
    payload: dict[str, Any],
    status: int,
    body: dict[str, Any],
) -> None:
    """Record the response on the key claimed by ``idempotent_replay``
    (same transaction: committed together with the record it describes)."""
    if not key:
        return
    _check_key(key)
    updated = db.execute(
        update(IdempotencyKey)
        .where(
            IdempotencyKey.organization_id == organization_id,
            IdempotencyKey.idempotency_key == key,
            IdempotencyKey.request_hash == _hash(payload),
            IdempotencyKey.response_status == _PENDING_STATUS,
        )
        .values(endpoint=endpoint, response_status=status, response_body=body)
        .execution_options(synchronize_session=False)
    )
    if updated.rowcount == 1:
        return
    # not claimed through idempotent_replay: insert, never clobber another
    with db.begin_nested():
        db.execute(
            pg_insert(IdempotencyKey)
            .values(
                id=uuid.uuid4(),
                organization_id=organization_id,
                idempotency_key=key,
                endpoint=endpoint,
                request_hash=_hash(payload),
                response_status=status,
                response_body=body,
            )
            .on_conflict_do_nothing(constraint="uq_idem_org_key")
        )
