"""Smart Printer Setup: per-clinic printer profiles (paper kind, margins,
font scale) and which profile is the default for prescriptions, receipts
and lab reports. The web print routes read the defaults and emit matching
``@page`` CSS — printing itself is done by the browser's print dialog."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..models_setup import PrinterProfile
from ..schemas_setup import (
    PRINT_DOCUMENTS,
    PrinterDefaultsOut,
    PrinterProfileIn,
    PrinterProfileOut,
    PrinterProfileUpdateIn,
)

router = APIRouter(prefix="/setup/printers", tags=["printers"])

MAX_PROFILES = 20


def _audit(db: Session, principal: Principal, request: Request, action: str,
           row: PrinterProfile, metadata: dict | None = None) -> None:
    record_event(
        db, action=action, organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id), resource_type="printer_profile",
        resource_id=str(row.id), metadata={"name": row.name, "kind": row.kind,
                                           **(metadata or {})},
        correlation_id=get_correlation_id(request), ip_address=get_client_ip(request),
    )


def _lock(db: Session, principal: Principal) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
               {"k": f"printers:{principal.organization_id}"})


def _claim_defaults(db: Session, principal: Principal, row: PrinterProfile) -> None:
    """A document type has at most one default profile: taking it here
    removes it from every other profile of the clinic."""
    if not row.default_for:
        return
    others = db.scalars(select(PrinterProfile).where(
        PrinterProfile.organization_id == principal.organization_id,
        PrinterProfile.id != row.id)).all()
    for other in others:
        kept = [d for d in other.default_for if d not in row.default_for]
        if kept != list(other.default_for):
            other.default_for = kept
            other.updated_at = datetime.now(timezone.utc)


def _load(db: Session, principal: Principal, profile_id: uuid.UUID) -> PrinterProfile:
    row = db.scalar(select(PrinterProfile).where(
        PrinterProfile.id == profile_id,
        PrinterProfile.organization_id == principal.organization_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Printer profile not found")
    return row


def _flush(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A printer profile with this name exists")


@router.get("", response_model=list[PrinterProfileOut])
def list_profiles(
    principal: Principal = Depends(require_permission("setup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> list[PrinterProfileOut]:
    rows = db.scalars(select(PrinterProfile).where(
        PrinterProfile.organization_id == principal.organization_id)
        .order_by(PrinterProfile.created_at)).all()
    return [PrinterProfileOut.model_validate(r) for r in rows]


@router.get("/defaults", response_model=PrinterDefaultsOut)
def defaults(
    principal: Principal = Depends(require_permission("setup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> PrinterDefaultsOut:
    rows = db.scalars(select(PrinterProfile).where(
        PrinterProfile.organization_id == principal.organization_id)
        .order_by(PrinterProfile.created_at)).all()
    pick = {doc: next((PrinterProfileOut.model_validate(r) for r in rows
                       if doc in r.default_for), None) for doc in PRINT_DOCUMENTS}
    return PrinterDefaultsOut(**pick)


@router.get("/{profile_id}", response_model=PrinterProfileOut)
def get_profile(
    profile_id: uuid.UUID,
    principal: Principal = Depends(require_permission("setup.read")),
    db: Session = Depends(get_db, scope="function"),
) -> PrinterProfileOut:
    return PrinterProfileOut.model_validate(_load(db, principal, profile_id))


@router.post("", response_model=PrinterProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: PrinterProfileIn,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> PrinterProfileOut:
    _lock(db, principal)
    count = db.scalar(select(func.count()).select_from(PrinterProfile).where(
        PrinterProfile.organization_id == principal.organization_id)) or 0
    if count >= MAX_PROFILES:
        raise HTTPException(status_code=409,
                            detail=f"At most {MAX_PROFILES} printer profiles per clinic")
    row = PrinterProfile(organization_id=principal.organization_id,
                         created_by=principal.user_id, **payload.model_dump())
    db.add(row)
    _flush(db)
    _claim_defaults(db, principal, row)
    _flush(db)
    db.refresh(row)
    _audit(db, principal, request, "printer.created", row, {"default_for": row.default_for})
    return PrinterProfileOut.model_validate(row)


@router.patch("/{profile_id}", response_model=PrinterProfileOut)
def update_profile(
    profile_id: uuid.UUID,
    payload: PrinterProfileUpdateIn,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> PrinterProfileOut:
    _lock(db, principal)
    row = _load(db, principal, profile_id)
    changes = {k: getattr(payload, k) for k in payload.model_fields_set
               if getattr(payload, k) is not None}
    for k, v in changes.items():
        setattr(row, k, v)
    if changes:
        row.updated_at = datetime.now(timezone.utc)
        _flush(db)
        if "default_for" in changes:
            _claim_defaults(db, principal, row)
            _flush(db)
        db.refresh(row)
        _audit(db, principal, request, "printer.updated", row, {"fields": sorted(changes)})
    return PrinterProfileOut.model_validate(row)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission("setup.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> None:
    row = _load(db, principal, profile_id)
    _audit(db, principal, request, "printer.deleted", row)
    db.delete(row)
    db.flush()
