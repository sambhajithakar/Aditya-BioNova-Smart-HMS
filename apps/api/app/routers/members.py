"""Organization members (staff accounts and their roles) and invitations.

An administrator may create a brand-new staff account directly, but can
never attach an *existing* account (which may belong to another tenant) —
that requires the account holder to accept an e-mailed invitation with their
own password (see ``POST /auth/invitations/accept``).
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import comms
from ..auditing import record_event
from ..config import get_settings
from ..entitlements import check_limit
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..models import Branch, MemberInvitation, Membership, RefreshSession, Role, User
from ..schemas import (
    InvitationCreateIn,
    InvitationOut,
    MemberCreateIn,
    MemberOut,
    MemberUpdateIn,
)
from ..security import hash_password, hash_token

router = APIRouter(prefix="/members", tags=["members"])

INVITATION_TTL = timedelta(days=7)

_ASSIGNABLE_NON_OWNER_ROLES = (
    "admin",
    "doctor",
    "nurse",
    "receptionist",
    "pharmacist",
    "lab_technician",
    "billing",
    "auditor",
    "support",
)


def _member_out(db: Session, m: Membership) -> MemberOut:
    user = db.get(User, m.user_id)
    role = db.get(Role, m.role_id)
    assert user is not None and role is not None
    return MemberOut(
        membership_id=m.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        registration_number=user.registration_number,
        role_key=role.key,
        branch_id=m.branch_id,
        status=m.status,
        created_at=m.created_at,
    )


def _assignable_role(db: Session, role_key: str) -> Role:
    if role_key == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The owner role is granted only during organization registration",
        )
    role = db.scalar(select(Role).where(Role.key == role_key))
    if role is None or role.key not in _ASSIGNABLE_NON_OWNER_ROLES:
        raise HTTPException(status_code=422, detail="Unknown or non-assignable role_key")
    return role


def _check_branch(db: Session, branch_id: uuid.UUID | None) -> None:
    # RLS-scoped lookup: another tenant's branch id is simply not visible
    if branch_id is not None and db.get(Branch, branch_id) is None:
        raise HTTPException(status_code=422, detail="branch_id not found in this organization")


def _audit(db: Session, principal: Principal, request: Request, action: str,
           resource_type: str, resource_id: uuid.UUID, metadata: dict) -> None:
    record_event(
        db,
        action=action,
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type=resource_type,
        resource_id=str(resource_id),
        metadata=metadata,
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )


def _revoke_member_sessions(db: Session, m: Membership) -> int:
    return db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == m.user_id)
        .where(RefreshSession.organization_id == m.organization_id)
        .where(RefreshSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    ).rowcount or 0


def _load_member(db: Session, principal: Principal, membership_id: uuid.UUID) -> Membership:
    m = db.get(Membership, membership_id)
    if m is None or m.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Member not found")
    return m


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: MemberCreateIn,
    request: Request,
    principal: Principal = Depends(require_permission("member.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> MemberOut:
    role = _assignable_role(db, payload.role_key)
    _check_branch(db, payload.branch_id)

    email = payload.email.lower()
    check_limit(db, principal.organization_id, "max_users")
    if db.scalar(select(User.id).where(User.email == email)):
        # Never attach an existing account (or reveal whose it is).
        raise HTTPException(
            status_code=409,
            detail="This e-mail already has an account. Send an invitation instead.",
        )
    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    membership = Membership(
        user_id=user.id,
        organization_id=principal.organization_id,
        branch_id=payload.branch_id,
        role_id=role.id,
    )
    db.add(membership)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Membership conflict")

    _audit(db, principal, request, "member.created", "membership", membership.id,
           {"email": email, "role_key": role.key, "user_created": True})
    return _member_out(db, membership)


@router.get("", response_model=list[MemberOut])
def list_members(
    principal: Principal = Depends(require_permission("member.read")),
    db: Session = Depends(get_db, scope="function"),
) -> list[MemberOut]:
    rows = db.scalars(
        select(Membership)
        .where(Membership.organization_id == principal.organization_id)
        .order_by(Membership.created_at)
    ).all()
    return [_member_out(db, m) for m in rows]


# --- Invitations (declared before /{membership_id} routes) -------------------
def _invitation_out(db: Session, inv: MemberInvitation) -> InvitationOut:
    role = db.get(Role, inv.role_id)
    return InvitationOut(
        id=inv.id, email=inv.email, role_key=role.key if role else "unknown",
        branch_id=inv.branch_id, status=inv.status, expires_at=inv.expires_at,
        created_at=inv.created_at,
    )


@router.post("/invitations", response_model=InvitationOut,
             status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreateIn,
    request: Request,
    principal: Principal = Depends(require_permission("member.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> InvitationOut:
    role = _assignable_role(db, payload.role_key)
    _check_branch(db, payload.branch_id)
    email = payload.email.lower()
    # One live invitation per e-mail: re-inviting replaces the old link.
    db.execute(
        update(MemberInvitation)
        .where(MemberInvitation.organization_id == principal.organization_id)
        .where(MemberInvitation.email == email)
        .where(MemberInvitation.status == "pending")
        .values(status="revoked", updated_at=datetime.now(timezone.utc))
    )
    db.flush()
    check_limit(db, principal.organization_id, "max_users")
    token = secrets.token_urlsafe(32)
    inv = MemberInvitation(
        organization_id=principal.organization_id,
        email=email,
        role_id=role.id,
        branch_id=payload.branch_id,
        token_hash=hash_token(token),
        invited_by_user_id=principal.user_id,
        expires_at=datetime.now(timezone.utc) + INVITATION_TTL,
    )
    db.add(inv)
    db.flush()
    db.refresh(inv)
    settings = get_settings()
    link = f"{settings.web_base_url.rstrip('/')}/accept-invite?token={token}"
    comms.send(comms.Message(
        channel="email",
        to=email,
        subject="You have been invited to Aditya BioNova HMS",
        body=(f"{principal.user.full_name} invited you to join their clinic as "
              f"{role.name}.\n\n{link}\n\nThe invitation expires in "
              f"{INVITATION_TTL.days} days."),
        sensitive=True,
    ))
    _audit(db, principal, request, "member.invited", "invitation", inv.id,
           {"email": email, "role_key": role.key})
    return _invitation_out(db, inv)


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(
    principal: Principal = Depends(require_permission("member.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> list[InvitationOut]:
    rows = db.scalars(
        select(MemberInvitation)
        .where(MemberInvitation.organization_id == principal.organization_id)
        .order_by(MemberInvitation.created_at.desc())
    ).all()
    return [_invitation_out(db, r) for r in rows]


@router.post("/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def revoke_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission("member.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> InvitationOut:
    inv = db.get(MemberInvitation, invitation_id)
    if inv is None or inv.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.status != "pending":
        raise HTTPException(status_code=409, detail=f"Invitation is already {inv.status}")
    inv.status = "revoked"
    inv.updated_at = datetime.now(timezone.utc)
    _audit(db, principal, request, "member.invitation_revoked", "invitation", inv.id, {})
    return _invitation_out(db, inv)


# --- Member administration ---------------------------------------------------
@router.patch("/{membership_id}", response_model=MemberOut)
def update_member(
    membership_id: uuid.UUID,
    payload: MemberUpdateIn,
    request: Request,
    principal: Principal = Depends(require_permission("member.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> MemberOut:
    m = _load_member(db, principal, membership_id)
    current_role = db.get(Role, m.role_id)
    if current_role is not None and current_role.key == "owner":
        raise HTTPException(status_code=403, detail="The owner membership cannot be modified")
    if m.user_id == principal.user_id and payload.status == "suspended":
        raise HTTPException(status_code=409, detail="You cannot suspend yourself")

    changes: dict = {}
    if payload.role_key is not None:
        role = _assignable_role(db, payload.role_key)
        if role.id != m.role_id:
            changes["role_key"] = role.key
            m.role_id = role.id
    if "branch_id" in payload.model_fields_set:
        _check_branch(db, payload.branch_id)
        if payload.branch_id != m.branch_id:
            changes["branch_id"] = str(payload.branch_id) if payload.branch_id else None
            m.branch_id = payload.branch_id
    if "registration_number" in payload.model_fields_set:
        user = db.get(User, m.user_id)
        if user is not None and user.registration_number != payload.registration_number:
            changes["registration_number"] = payload.registration_number
            user.registration_number = payload.registration_number
    revoked = 0
    if payload.status is not None and payload.status != m.status:
        if payload.status == "active":
            check_limit(db, principal.organization_id, "max_users")
        changes["status"] = payload.status
        m.status = payload.status
        if payload.status == "suspended":
            revoked = _revoke_member_sessions(db, m)
    db.flush()
    if changes:
        _audit(db, principal, request, "member.updated", "membership", m.id,
               {**changes, "sessions_revoked": revoked})
    return _member_out(db, m)


@router.post("/{membership_id}/sessions/revoke")
def revoke_member_sessions(
    membership_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission("member.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    m = _load_member(db, principal, membership_id)
    revoked = _revoke_member_sessions(db, m)
    _audit(db, principal, request, "member.sessions_revoked", "membership", m.id,
           {"count": revoked})
    return {"revoked": revoked}
