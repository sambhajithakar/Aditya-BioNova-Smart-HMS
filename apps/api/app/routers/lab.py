"""M5 laboratory API: orders -> specimens -> results (import/verify/release).

Blueprint rules enforced here (§R4):
* orders reference the validated ``lab_test_catalog`` — no free-text tests;
* the result lifecycle is imported -> verified -> released with
  column-level DB freezing; verification is FOUR-EYES (the verifier must
  differ from the importer) and every transition is audited;
* a released result can only be superseded by a NEW version — the old row
  is flipped to ``superseded`` by DB trigger, never edited;
* released/cancelled orders are frozen.

Ordered tests (M7.0 / C2, H7):
* the tests of an order are persisted as ``lab_order_items`` (ordered ->
  resulted | cancelled); results are accepted ONLY for tests on the order
  (422 otherwise) and never with an empty value;
* an order is released only when EVERY non-cancelled ordered test has a
  live released result (and no live result is still pending) — a DB
  trigger refuses any other release, even via raw SQL;
* an order may take several specimens (e.g. blood + urine), and a rejected
  specimen can be re-collected while the order is open;
* specimen barcodes are allocated under a per-tenant advisory lock.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..db import get_db
from ..deps import (
    Principal,
    get_client_ip,
    get_correlation_id,
    require_permission,
)
from ..models import (
    LabOrder,
    LabOrderItem,
    LabResult,
    LabSpecimen,
    LabTestCatalog,
    Patient,
)
from ..schemas import (
    AmendResultIn,
    CancelLabOrderIn,
    CollectSpecimenIn,
    ImportResultsIn,
    LabOrderDetailOut,
    LabOrderIn,
    LabOrderItemOut,
    LabOrderOut,
    LabResultOut,
    LabSpecimenOut,
    LabTestOut,
    PageOut,
    RejectSpecimenIn,
)
from ..services.tenancy import load_branch, load_encounter

router = APIRouter(prefix="/lab", tags=["lab"])

MAX_LIMIT = 100

BARCODE_ATTEMPTS = 3
_OPEN_FOR_SPECIMENS = ("ordered", "specimen_collected", "in_progress")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_order(
    db: Session, principal: Principal, order_id: uuid.UUID, *, lock: bool = False
) -> LabOrder:
    stmt = select(LabOrder).where(
        LabOrder.id == order_id,
        LabOrder.organization_id == principal.organization_id,
    )
    if lock:
        # serializes imports/releases/collections on one order
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(stmt)
    if row is None:
        raise HTTPException(status_code=404, detail="Lab order not found")
    return row


def _order_items(
    db: Session, principal: Principal, order_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LabOrderItemOut]]:
    """Ordered tests per order, with code/name from the global catalog."""
    out: dict[uuid.UUID, list[LabOrderItemOut]] = {oid: [] for oid in order_ids}
    if not order_ids:
        return out
    rows = db.execute(
        select(LabOrderItem, LabTestCatalog.code, LabTestCatalog.name)
        .join(LabTestCatalog, LabTestCatalog.id == LabOrderItem.test_id)
        .where(
            LabOrderItem.organization_id == principal.organization_id,
            LabOrderItem.order_id.in_(order_ids),
        )
        .order_by(LabOrderItem.created_at, LabTestCatalog.code)
    ).all()
    for item, code, name in rows:
        out[item.order_id].append(
            LabOrderItemOut(id=item.id, test_id=item.test_id, test_code=code,
                            test_name=name, status=item.status)
        )
    return out


def _order_detail(db: Session, principal: Principal, order: LabOrder) -> LabOrderDetailOut:
    specimens = db.scalars(
        select(LabSpecimen).where(
            LabSpecimen.organization_id == principal.organization_id,
            LabSpecimen.order_id == order.id,
        ).order_by(LabSpecimen.collected_at)
    ).all()
    results = db.scalars(
        select(LabResult).where(
            LabResult.organization_id == principal.organization_id,
            LabResult.order_id == order.id,
        ).order_by(LabResult.created_at)
    ).all()
    detail = LabOrderDetailOut.model_validate(order)
    detail.items = _order_items(db, principal, [order.id])[order.id]
    detail.specimens = [LabSpecimenOut.model_validate(s) for s in specimens]
    detail.results = [LabResultOut.model_validate(r) for r in results]
    return detail


def _next_barcode(db: Session, principal: Principal) -> str:
    # per-tenant lock: concurrent collections cannot compute the same max+1
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"specimen-barcode:{principal.organization_id}"},
    )
    last = db.scalar(
        select(func.max(LabSpecimen.barcode)).where(
            LabSpecimen.organization_id == principal.organization_id
        )
    )
    seq = int(last.split("-")[-1]) + 1 if last else 1
    for _ in range(BARCODE_ATTEMPTS):
        candidate = f"SPC-{seq:06d}"
        clash = db.scalar(
            select(LabSpecimen.id).where(
                LabSpecimen.organization_id == principal.organization_id,
                LabSpecimen.barcode == candidate,
            )
        )
        if clash is None:
            return candidate
        seq += 1
    raise HTTPException(status_code=503, detail="Specimen barcode busy, retry")


def _load_tests(db: Session, test_ids: list[uuid.UUID]) -> list[LabTestCatalog]:
    rows = db.scalars(
        select(LabTestCatalog).where(
            LabTestCatalog.id.in_(test_ids), LabTestCatalog.is_active.is_(True)
        )
    ).all()
    found = {r.id for r in rows}
    missing = [str(t) for t in test_ids if t not in found]
    if missing:
        raise HTTPException(
            status_code=422, detail="Unknown lab test id(s): " + ", ".join(missing)
        )
    return list(rows)


# --- catalog ----------------------------------------------------------------
@router.get("/tests", response_model=list[LabTestOut])
def list_lab_tests(
    q: str | None = None,
    limit: int = 100,
    principal: Principal = Depends(require_permission("lab.read")),
    db: Session = Depends(get_db, scope="function"),
) -> list[LabTestOut]:
    limit = min(max(limit, 1), MAX_LIMIT)
    query = select(LabTestCatalog).where(LabTestCatalog.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            LabTestCatalog.name.ilike(like) | LabTestCatalog.code.ilike(like)
        )
    rows = db.scalars(
        query.order_by(LabTestCatalog.code).limit(limit)
    ).all()
    return [LabTestOut.model_validate(r) for r in rows]


# --- orders -----------------------------------------------------------------
@router.post("/orders", response_model=LabOrderDetailOut,
             status_code=status.HTTP_201_CREATED)
def post_lab_order(
    payload: LabOrderIn,
    request: Request,
    principal: Principal = Depends(require_permission("lab.order")),
    db: Session = Depends(get_db, scope="function"),
) -> LabOrderDetailOut:
    patient = db.scalar(
        select(Patient).where(
            Patient.id == payload.patient_id,
            Patient.organization_id == principal.organization_id,
        )
    )
    if patient is None or patient.status == "merged":
        raise HTTPException(status_code=404, detail="Patient not found")
    # FK checks bypass RLS: branch/encounter must be visible to this tenant
    load_branch(db, principal, payload.branch_id)
    if payload.encounter_id is not None:
        load_encounter(db, principal, payload.encounter_id,
                       patient_id=payload.patient_id)

    _load_tests(db, payload.test_ids)  # validates against the catalog

    order = LabOrder(
        organization_id=principal.organization_id,
        patient_id=payload.patient_id,
        encounter_id=payload.encounter_id,
        branch_id=payload.branch_id,
        priority=payload.priority,
        clinical_notes=payload.clinical_notes,
        ordered_by=principal.user_id,
    )
    db.add(order)
    db.flush()
    for test_id in payload.test_ids:
        db.add(LabOrderItem(organization_id=principal.organization_id,
                            order_id=order.id, test_id=test_id))
    db.flush()
    record_event(
        db,
        action="lab.order_created",
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="lab_order",
        resource_id=str(order.id),
        metadata={
            "patient_id": str(payload.patient_id),
            "test_ids": [str(t) for t in payload.test_ids],
            "priority": payload.priority,
        },
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    return _order_detail(db, principal, order)


@router.get("/orders", response_model=PageOut)
def list_lab_orders(
    order_status: str | None = Query(default=None, alias="status"),
    patient_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(require_permission("lab.read")),
    db: Session = Depends(get_db, scope="function"),
) -> PageOut:
    limit = min(max(limit, 1), MAX_LIMIT)
    q = select(LabOrder).where(LabOrder.organization_id == principal.organization_id)
    if order_status:
        q = q.where(LabOrder.status == order_status)
    if patient_id:
        q = q.where(LabOrder.patient_id == patient_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(
        q.order_by(LabOrder.created_at.desc()).limit(limit).offset(offset)
    ).all()
    items = _order_items(db, principal, [r.id for r in rows])
    out = []
    for r in rows:
        row_out = LabOrderOut.model_validate(r)
        row_out.items = items[r.id]
        out.append(row_out)
    return PageOut(items=out, total=total or 0, limit=limit, offset=offset)


@router.get("/orders/{order_id}", response_model=LabOrderDetailOut)
def get_lab_order(
    order_id: uuid.UUID,
    principal: Principal = Depends(require_permission("lab.read")),
    db: Session = Depends(get_db, scope="function"),
) -> LabOrderDetailOut:
    return _order_detail(db, principal, _get_order(db, principal, order_id))


@router.post("/orders/{order_id}/cancel", response_model=LabOrderDetailOut)
def post_cancel_order(
    order_id: uuid.UUID,
    payload: CancelLabOrderIn,
    request: Request,
    principal: Principal = Depends(require_permission("lab.order")),
    db: Session = Depends(get_db, scope="function"),
) -> LabOrderDetailOut:
    order = _get_order(db, principal, order_id, lock=True)
    if order.status not in ("ordered", "specimen_collected"):
        raise HTTPException(
            status_code=409,
            detail=f"Only open orders can be cancelled (status: {order.status})",
        )
    has_results = db.scalar(
        select(LabResult.id).where(LabResult.order_id == order.id).limit(1)
    )
    if has_results is not None:
        raise HTTPException(
            status_code=409,
            detail="Order already has imported results; cannot cancel",
        )
    order.status = "cancelled"
    order.cancel_reason = payload.reason
    order.updated_at = _now()
    for item in db.scalars(
        select(LabOrderItem).where(
            LabOrderItem.organization_id == principal.organization_id,
            LabOrderItem.order_id == order.id,
            LabOrderItem.status == "ordered",
        )
    ).all():
        item.status = "cancelled"
        item.updated_at = order.updated_at
    record_event(
        db,
        action="lab.order_cancelled",
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="lab_order",
        resource_id=str(order.id),
        metadata={"reason": payload.reason},
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    return _order_detail(db, principal, order)


# --- specimens --------------------------------------------------------------
@router.post("/orders/{order_id}/specimens",
             response_model=LabSpecimenOut,
             status_code=status.HTTP_201_CREATED)
def post_collect_specimen(
    order_id: uuid.UUID,
    payload: CollectSpecimenIn,
    request: Request,
    principal: Principal = Depends(require_permission("lab.order")),
    db: Session = Depends(get_db, scope="function"),
) -> LabSpecimenOut:
    order = _get_order(db, principal, order_id, lock=True)
    # several specimens per order (blood + urine ...) and re-collection after
    # a rejection are legal while the order is open
    if order.status not in _OPEN_FOR_SPECIMENS:
        raise HTTPException(
            status_code=409,
            detail=f"Specimens can only be collected on open orders "
                   f"(status: {order.status})",
        )
    specimen = LabSpecimen(
        organization_id=principal.organization_id,
        order_id=order.id,
        barcode=_next_barcode(db, principal),
        specimen_type=payload.specimen_type,
        collected_by=principal.user_id,
    )
    db.add(specimen)
    if order.status == "ordered":
        order.status = "specimen_collected"
    order.updated_at = _now()
    db.flush()
    record_event(
        db,
        action="lab.specimen_collected",
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="lab_specimen",
        resource_id=str(specimen.id),
        metadata={"order_id": str(order.id), "barcode": specimen.barcode},
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    return LabSpecimenOut.model_validate(specimen)


@router.post("/specimens/{specimen_id}/reject", response_model=LabSpecimenOut)
def post_reject_specimen(
    specimen_id: uuid.UUID,
    payload: RejectSpecimenIn,
    request: Request,
    principal: Principal = Depends(require_permission("lab.order")),
    db: Session = Depends(get_db, scope="function"),
) -> LabSpecimenOut:
    specimen = db.scalar(
        select(LabSpecimen).where(
            LabSpecimen.id == specimen_id,
            LabSpecimen.organization_id == principal.organization_id,
        )
    )
    if specimen is None:
        raise HTTPException(status_code=404, detail="Specimen not found")
    if specimen.status != "collected":
        raise HTTPException(
            status_code=409,
            detail=f"Only collected specimens can be rejected ({specimen.status})",
        )
    specimen.status = "rejected"
    specimen.rejection_reason = payload.reason
    record_event(
        db,
        action="lab.specimen_rejected",
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="lab_specimen",
        resource_id=str(specimen.id),
        metadata={"reason": payload.reason},
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    return LabSpecimenOut.model_validate(specimen)


# --- results ----------------------------------------------------------------
@router.post("/orders/{order_id}/results",
             response_model=LabOrderDetailOut,
             status_code=status.HTTP_201_CREATED)
def post_import_results(
    order_id: uuid.UUID,
    payload: ImportResultsIn,
    request: Request,
    principal: Principal = Depends(require_permission("lab.import")),
    db: Session = Depends(get_db, scope="function"),
) -> LabOrderDetailOut:
    order = _get_order(db, principal, order_id, lock=True)
    if order.status not in ("specimen_collected", "in_progress"):
        raise HTTPException(
            status_code=409,
            detail=f"Results need a collected specimen (status: {order.status})",
        )

    tests = _load_tests(db, [r.test_id for r in payload.results])
    test_ids = {t.id for t in tests}
    if len(test_ids) != len(payload.results):
        raise HTTPException(
            status_code=422, detail="Duplicate test_id in results payload"
        )
    # only tests that were ORDERED (and not cancelled) can carry a result
    items = {
        i.test_id: i
        for i in db.scalars(
            select(LabOrderItem).where(
                LabOrderItem.organization_id == principal.organization_id,
                LabOrderItem.order_id == order.id,
                LabOrderItem.status != "cancelled",
            )
        ).all()
    }
    not_ordered = sorted(str(t) for t in test_ids if t not in items)
    if not_ordered:
        raise HTTPException(
            status_code=422,
            detail="Test(s) not on this order: " + ", ".join(not_ordered),
        )

    # exactly one LIVE result per test per order (uq_labresult_live_per_test):
    # re-importing a test must go through the amendment path instead of
    # tripping the partial unique index.
    live = db.scalars(
        select(LabResult.test_id).where(
            LabResult.organization_id == principal.organization_id,
            LabResult.order_id == order.id,
            LabResult.status != "superseded",
            LabResult.test_id.in_(test_ids),
        )
    ).all()
    if live:
        raise HTTPException(
            status_code=409,
            detail=("Result already imported for test(s): "
                    + ", ".join(sorted(str(t) for t in live))
                    + " — amend the released result instead"),
        )

    specimen = None
    if payload.specimen_id is not None:
        specimen = db.scalar(
            select(LabSpecimen).where(
                LabSpecimen.id == payload.specimen_id,
                LabSpecimen.organization_id == principal.organization_id,
                LabSpecimen.order_id == order.id,
            )
        )
        if specimen is None:
            raise HTTPException(status_code=404, detail="Specimen not found")
        if specimen.status != "collected":
            raise HTTPException(
                status_code=409,
                detail=f"Specimen is {specimen.status}; results cannot be imported",
            )
    else:
        usable = db.scalar(
            select(LabSpecimen.id).where(
                LabSpecimen.organization_id == principal.organization_id,
                LabSpecimen.order_id == order.id,
                LabSpecimen.status == "collected",
            ).limit(1)
        )
        if usable is None:
            raise HTTPException(
                status_code=409,
                detail="No usable specimen on this order (all rejected); "
                       "collect a new specimen first",
            )

    tests_by_id = {t.id: t for t in tests}
    for r in payload.results:
        test = tests_by_id[r.test_id]
        db.add(
            LabResult(
                organization_id=principal.organization_id,
                order_id=order.id,
                test_id=r.test_id,
                specimen_id=specimen.id if specimen else None,
                value_text=r.value_text,
                value_numeric=r.value_numeric,
                unit=test.unit,
                reference_range=test.reference_range,
                flag=r.flag,
                status="imported",
                imported_by=principal.user_id,
            )
        )
        item = items[r.test_id]
        if item.status == "ordered":
            item.status = "resulted"
            item.updated_at = _now()
    order.status = "in_progress"
    order.updated_at = _now()
    db.flush()
    record_event(
        db,
        action="lab.results_imported",
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="lab_order",
        resource_id=str(order.id),
        metadata={
            "test_ids": [str(t) for t in test_ids],
            "specimen_id": str(specimen.id) if specimen else None,
        },
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    return _order_detail(db, principal, order)


def _transition_result(
    db: Session,
    principal: Principal,
    result: LabResult,
    *,
    new_status: str,
    action: str,
    request: Request,
) -> LabResultOut:
    now = _now()
    if new_status == "verified":
        # four-eyes: the verifier must differ from the importer
        if result.imported_by == principal.user_id:
            raise HTTPException(
                status_code=403,
                detail="Four-eyes policy: a second person must verify this "
                       "result (verifier cannot be the importer)",
            )
        result.verified_by = principal.user_id
        result.verified_at = now
    elif new_status == "released":
        result.released_by = principal.user_id
        result.released_at = now
    result.status = new_status
    result.updated_at = now
    # autoflush is OFF app-wide: flush here so callers that immediately query
    # (e.g. the release endpoint counting pending results) see this change.
    db.flush()
    record_event(
        db,
        action=action,
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="lab_result",
        resource_id=str(result.id),
        metadata={"order_id": str(result.order_id), "status": new_status},
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    return LabResultOut.model_validate(result)


@router.post("/results/{result_id}/verify", response_model=LabResultOut)
def post_verify_result(
    result_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission("lab.verify")),
    db: Session = Depends(get_db, scope="function"),
) -> LabResultOut:
    result = db.scalar(
        select(LabResult).where(
            LabResult.id == result_id,
            LabResult.organization_id == principal.organization_id,
        )
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Lab result not found")
    if result.status != "imported":
        raise HTTPException(
            status_code=409,
            detail=f"Only imported results can be verified ({result.status})",
        )
    return _transition_result(
        db, principal, result, new_status="verified",
        action="lab.result_verified", request=request,
    )


@router.post("/results/{result_id}/release", response_model=LabResultOut)
def post_release_result(
    result_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission("lab.release")),
    db: Session = Depends(get_db, scope="function"),
) -> LabResultOut:
    result, order = _lock_result_and_order(db, principal, result_id)
    if result.status != "verified":
        raise HTTPException(
            status_code=409,
            detail=f"Only verified results can be released ({result.status})",
        )
    out = _transition_result(
        db, principal, result, new_status="released",
        action="lab.result_released", request=request,
    )
    if order.status != "cancelled" and _order_complete(db, principal, order):
        order.status = "released"
        order.updated_at = _now()
    return out


def _lock_result_and_order(
    db: Session, principal: Principal, result_id: uuid.UUID
) -> tuple[LabResult, LabOrder]:
    """Lock the parent order, then re-read the result: concurrent releases
    or amendments of one order serialize and never act on a stale status."""
    found = db.scalar(
        select(LabResult.order_id).where(
            LabResult.id == result_id,
            LabResult.organization_id == principal.organization_id,
        )
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Lab result not found")
    order = _get_order(db, principal, found, lock=True)
    result = db.scalar(
        select(LabResult)
        .where(LabResult.id == result_id,
               LabResult.organization_id == principal.organization_id)
        .execution_options(populate_existing=True)
    )
    return result, order


def _order_complete(db: Session, principal: Principal, order: LabOrder) -> bool:
    """Release rule: no live result still pending AND every non-cancelled
    ordered test has a live released result (mirrors the DB trigger)."""
    pending = db.scalar(
        select(func.count()).select_from(LabResult).where(
            LabResult.organization_id == principal.organization_id,
            LabResult.order_id == order.id,
            LabResult.status != "released",
            LabResult.status != "superseded",
        )
    )
    if pending:
        return False
    released = select(LabResult.id).where(
        LabResult.order_id == LabOrderItem.order_id,
        LabResult.test_id == LabOrderItem.test_id,
        LabResult.status == "released",
    ).exists()
    missing = db.scalar(
        select(func.count()).select_from(LabOrderItem).where(
            LabOrderItem.organization_id == principal.organization_id,
            LabOrderItem.order_id == order.id,
            LabOrderItem.status != "cancelled",
            ~released,
        )
    )
    return not missing


@router.post("/results/{result_id}/amend", response_model=LabResultOut,
             status_code=status.HTTP_201_CREATED)
def post_amend_result(
    result_id: uuid.UUID,
    payload: AmendResultIn,
    request: Request,
    principal: Principal = Depends(require_permission("lab.import")),
    db: Session = Depends(get_db, scope="function"),
) -> LabResultOut:
    """Supersede a released result with a NEW audited version (four-eyes:
    amendments are imported by one person and must be re-verified/released
    by another)."""
    old, order = _lock_result_and_order(db, principal, result_id)
    if old.status != "released":
        raise HTTPException(
            status_code=409,
            detail=f"Only released results can be amended ({old.status})",
        )
    new_id = uuid.uuid4()
    # Flip the OLD row first: the partial unique index (one live result per
    # order+test) forces the superseded row out of the index before the
    # replacement can enter it. superseded_by_id -> new_id is a DEFERRABLE
    # FK, checked at commit when the new row exists.
    old.status = "superseded"          # single legal post-release transition
    old.superseded_by_id = new_id
    old.amendment_reason = payload.reason
    old.updated_at = _now()
    db.flush()
    new = LabResult(
        id=new_id,
        organization_id=principal.organization_id,
        order_id=old.order_id,
        test_id=old.test_id,
        specimen_id=old.specimen_id,
        value_text=payload.value_text,
        value_numeric=payload.value_numeric,
        unit=old.unit,
        reference_range=old.reference_range,
        flag=payload.flag,
        status="imported",
        imported_by=principal.user_id,
    )
    db.add(new)
    db.flush()
    if order.status == "released":
        order.status = "in_progress"
        order.updated_at = _now()
    record_event(
        db,
        action="lab.result_amended",
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="lab_result",
        resource_id=str(new.id),
        metadata={
            "supersedes": str(old.id),
            "reason": payload.reason,
        },
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    return LabResultOut.model_validate(new)
