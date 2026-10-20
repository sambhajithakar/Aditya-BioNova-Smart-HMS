"""Authentication: register (org onboarding), login (+ TOTP MFA), refresh
rotation, logout, me, password change/reset, session management and
invitation acceptance.

Abuse protection (M7.0): every unauthenticated entry point is rate limited
per client IP, and failed logins lock the *submitted e-mail* for a window —
whether or not the account exists — so lockout never reveals registration.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import comms, ratelimit
from ..auditing import record_event, record_security_event
from ..config import get_settings
from ..db import get_db, set_request_context
from ..deps import (
    Principal,
    get_client_ip,
    get_correlation_id,
    get_current_principal,
    session_is_live,
)
from ..models import (
    MemberInvitation,
    Membership,
    MfaRecoveryCode,
    Organization,
    PasswordResetToken,
    RefreshSession,
    Role,
    RolePermission,
    User,
)
from ..schemas import (
    AuthSessionOut,
    InvitationAcceptIn,
    LoginIn,
    MeOut,
    MfaChallengeOut,
    MfaDisableIn,
    MfaStatusOut,
    MfaVerifyIn,
    OrganizationOut,
    PasswordChangeIn,
    PasswordForgotIn,
    PasswordResetIn,
    RecoveryCodesOut,
    RefreshIn,
    RegisterIn,
    SessionOut,
    TokenPair,
    TotpCodeIn,
    TotpSetupOut,
    UserOut,
)
from ..security import (
    DUMMY_PASSWORD_HASH,
    MFA_CHALLENGE_TTL_SECONDS,
    create_access_token,
    create_mfa_challenge_token,
    decode_mfa_challenge_token,
    decrypt_field,
    encrypt_field,
    hash_password,
    hash_refresh_token,
    hash_token,
    new_recovery_codes,
    new_refresh_token,
    new_totp_secret,
    password_needs_rehash,
    totp_uri,
    verify_password,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["auth"])

settings = get_settings()

PASSWORD_RESET_TTL = timedelta(minutes=30)
_MINUTE, _QUARTER, _HOUR = 60, 15 * 60, 60 * 60


def _invalid_credentials() -> HTTPException:
    # Generic message: never reveal whether the email exists.
    return HTTPException(status_code=401, detail="Invalid credentials")


def _new_session(
    db: Session,
    *,
    user: User,
    org_id: uuid.UUID,
    request: Request,
    family_id: uuid.UUID | None = None,
    absolute_expires_at: datetime | None = None,
) -> tuple[RefreshSession, str, str]:
    """Create a session row; return (row, access_token, refresh_token).

    A new family gets a fresh absolute deadline; a rotation inherits it, so
    refreshing can never extend a login beyond the absolute lifetime.
    """
    now = datetime.now(timezone.utc)
    absolute = absolute_expires_at or now + timedelta(
        seconds=settings.session_absolute_ttl_seconds
    )
    refresh_token, token_hash = new_refresh_token()
    session_row = RefreshSession(
        family_id=family_id or uuid.uuid4(),
        user_id=user.id,
        organization_id=org_id,
        token_hash=token_hash,
        expires_at=min(now + timedelta(seconds=settings.refresh_token_ttl_seconds), absolute),
        absolute_expires_at=absolute,
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        ip_address=get_client_ip(request),
    )
    db.add(session_row)
    db.flush()
    access = create_access_token(
        user_id=str(user.id), session_id=str(session_row.id), org_id=str(org_id)
    )
    return session_row, access, refresh_token


def _token_pair(access: str, refresh: str) -> TokenPair:
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_seconds,
    )


def _revoke_session_family(family_id, when) -> None:
    """Revoke every live session of a rotation family (own transaction)."""
    from ..db import SessionLocal

    local = SessionLocal()
    try:
        local.execute(
            RefreshSession.__table__.update()
            .where(RefreshSession.family_id == family_id)
            .where(RefreshSession.revoked_at.is_(None))
            .values(revoked_at=when)
        )
        local.commit()
    finally:
        local.close()


def _revoke_user_sessions(
    db: Session, user_id: uuid.UUID, *, except_session: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
) -> int:
    stmt = (
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id)
        .where(RefreshSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    if except_session is not None:
        stmt = stmt.where(RefreshSession.id != except_session)
    if organization_id is not None:
        stmt = stmt.where(RefreshSession.organization_id == organization_id)
    return db.execute(stmt).rowcount or 0


def _permissions_for_role(db: Session, role_id: uuid.UUID) -> list[str]:
    rows = db.scalars(
        select(RolePermission.permission_key).where(RolePermission.role_id == role_id)
    ).all()
    return sorted(set(rows))


def _issue_login(
    db: Session,
    *,
    user: User,
    org_row: Organization,
    membership: Membership,
    request: Request,
    method: str,
) -> AuthSessionOut:
    """Create the session and the response shared by every login path."""
    set_request_context(db, user_id=str(user.id), org_id=str(org_row.id))
    session_row, access, refresh_token = _new_session(
        db, user=user, org_id=org_row.id, request=request
    )
    record_event(
        db,
        action="auth.login",
        organization_id=str(org_row.id),
        actor_user_id=str(user.id),
        resource_type="session",
        resource_id=str(session_row.id),
        metadata={"method": method},
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    role = db.get(Role, membership.role_id)
    return AuthSessionOut(
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org_row),
        role=role.key if role else "unknown",
        permissions=_permissions_for_role(db, membership.role_id),
        tokens=_token_pair(access, refresh_token),
    )


def _mfa_enabled(user: User) -> bool:
    return user.mfa_totp_enabled_at is not None and user.mfa_totp_secret_enc is not None


def _check_second_factor(db: Session, user: User, code: str) -> str | None:
    """Verify a TOTP or recovery code; consume it. Returns the method or None."""
    code = code.strip().lower()
    if code.isdigit() and user.mfa_totp_secret_enc:
        secret = decrypt_field(user.mfa_totp_secret_enc, context=f"totp:{user.id}")
        step = verify_totp(secret, code, last_step=user.mfa_totp_last_step)
        if step is not None:
            user.mfa_totp_last_step = step  # replay guard
            return "totp"
        return None
    row = db.scalar(
        select(MfaRecoveryCode)
        .where(MfaRecoveryCode.user_id == user.id)
        .where(MfaRecoveryCode.code_hash == hash_token(code))
        .where(MfaRecoveryCode.used_at.is_(None))
        .with_for_update()
    )
    if row is None:
        return None
    row.used_at = datetime.now(timezone.utc)
    return "recovery_code"


def _send_email(to: str, subject: str, body: str, *, sensitive: bool = False) -> None:
    comms.send(comms.Message(channel="email", to=to, subject=subject, body=body,
                             sensitive=sensitive))


@router.post(
    "/register",
    response_model=AuthSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterIn,
    request: Request,
    db: Session = Depends(get_db, scope="function"),
) -> AuthSessionOut:
    """Onboard a new clinic/organization with its owner account.

    Creates organization + owner user + owner membership in one transaction.
    The transaction-local ``app.is_bootstrap`` flag is the only path through
    the organizations INSERT row-level policy.
    """
    email = payload.email.lower()
    ip = get_client_ip(request)
    cid = get_correlation_id(request)
    ratelimit.hit("register-ip", ip, limit=settings.rl_register_per_ip,
                  window_seconds=_HOUR)

    try:
        if db.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        user = User(
            email=email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        db.flush()

        # Claim the new org's id as tenant context BEFORE the row exists:
        # PostgreSQL applies SELECT row-policies to INSERT ... RETURNING, and
        # our org SELECT policy accepts `id = app.current_org_id`.
        org = Organization(
            id=uuid.uuid4(),
            name=payload.organization_name,
            slug=payload.organization_slug,
        )
        set_request_context(db, user_id=str(user.id), org_id=str(org.id), bootstrap=True)
        db.add(org)
        db.flush()

        set_request_context(db, user_id=str(user.id), org_id=str(org.id), bootstrap=False)
        owner_role = db.scalar(select(Role).where(Role.key == "owner"))
        if owner_role is None:  # pragma: no cover - migrations seed this
            raise RuntimeError("roles missing: run alembic migrations")
        membership = Membership(
            user_id=user.id, organization_id=org.id, role_id=owner_role.id
        )
        db.add(membership)
        db.flush()

        session_row, access, refresh_token = _new_session(
            db, user=user, org_id=org.id, request=request
        )

        record_event(
            db,
            action="auth.register",
            organization_id=str(org.id),
            actor_user_id=str(user.id),
            resource_type="organization",
            resource_id=str(org.id),
            metadata={"slug": org.slug},
            correlation_id=cid,
            ip_address=ip,
        )
        record_event(
            db,
            action="auth.login",
            organization_id=str(org.id),
            actor_user_id=str(user.id),
            resource_type="session",
            resource_id=str(session_row.id),
            metadata={"method": "password", "via": "register"},
            correlation_id=cid,
            ip_address=ip,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug or email already in use",
        )

    owner_role_id = membership.role_id
    return AuthSessionOut(
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org),
        role="owner",
        permissions=_permissions_for_role(db, owner_role_id),
        tokens=_token_pair(access, refresh_token),
    )


@router.post("/login", response_model=AuthSessionOut | MfaChallengeOut)
def login(
    payload: LoginIn, request: Request, db: Session = Depends(get_db, scope="function")
) -> AuthSessionOut | MfaChallengeOut:
    email = payload.email.lower()
    ip = get_client_ip(request)
    cid = get_correlation_id(request)

    ratelimit.hit("login-ip", ip, limit=settings.rl_login_per_ip, window_seconds=_MINUTE)
    # Lockout is checked before the password so a locked account cannot be
    # probed; it is keyed by the submitted e-mail (exists or not).
    try:
        ratelimit.check("login-fail", email, limit=settings.rl_login_failures_per_account,
                        window_seconds=_QUARTER)
    except HTTPException:
        record_security_event(
            action="auth.login_locked", metadata={"reason": "too_many_failures"},
            correlation_id=cid, ip_address=ip,
        )
        raise

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(payload.password, DUMMY_PASSWORD_HASH)  # timing equalisation
        ratelimit.record("login-fail", email, window_seconds=_QUARTER)
        record_security_event(
            action="auth.login_failed",
            metadata={"reason": "unknown_email"},
            correlation_id=cid,
            ip_address=ip,
        )
        raise _invalid_credentials()

    if not verify_password(payload.password, user.password_hash):
        ratelimit.record("login-fail", email, window_seconds=_QUARTER)
        record_security_event(
            action="auth.login_failed",
            actor_user_id=str(user.id),
            metadata={"reason": "bad_password"},
            correlation_id=cid,
            ip_address=ip,
        )
        raise _invalid_credentials()

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is disabled")

    ratelimit.clear("login-fail", email)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    # Tenant context first: RLS then reveals only this user's memberships.
    set_request_context(db, user_id=str(user.id))
    memberships = list(db.scalars(select(Membership).where(Membership.user_id == user.id)))
    if not memberships:
        raise HTTPException(status_code=403, detail="No organization membership")

    if payload.organization_slug:
        wanted = payload.organization_slug.lower()
        chosen = None
        for m in memberships:
            org_row = db.get(Organization, m.organization_id)
            if org_row is not None and org_row.slug == wanted:
                chosen = m
                break
        if chosen is None:
            raise _invalid_credentials()
    elif len(memberships) == 1:
        chosen = memberships[0]
    else:
        slugs = []
        for m in memberships:
            org_row = db.get(Organization, m.organization_id)
            if org_row is not None:
                slugs.append(org_row.slug)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Multiple organizations; specify organization_slug",
                "organization_slugs": slugs,
            },
        )

    if chosen.status != "active":
        raise HTTPException(status_code=403, detail="Membership is suspended")

    org_row = db.get(Organization, chosen.organization_id)
    if org_row is None or org_row.status != "active":
        raise HTTPException(status_code=403, detail="Organization is not active")

    if _mfa_enabled(user):
        token, _jti = create_mfa_challenge_token(user_id=str(user.id), org_id=str(org_row.id))
        set_request_context(db, user_id=str(user.id), org_id=str(org_row.id))
        record_event(
            db,
            action="auth.mfa_challenge",
            organization_id=str(org_row.id),
            actor_user_id=str(user.id),
            resource_type="user",
            resource_id=str(user.id),
            correlation_id=cid,
            ip_address=ip,
        )
        return MfaChallengeOut(
            mfa_token=token, methods=["totp"], expires_in=MFA_CHALLENGE_TTL_SECONDS
        )

    return _issue_login(db, user=user, org_row=org_row, membership=chosen,
                        request=request, method="password")


@router.post("/mfa/verify", response_model=AuthSessionOut)
def mfa_verify(
    payload: MfaVerifyIn, request: Request, db: Session = Depends(get_db, scope="function")
) -> AuthSessionOut:
    """Second login step: exchange an MFA challenge + code for a session."""
    ip = get_client_ip(request)
    cid = get_correlation_id(request)
    ratelimit.hit("login-ip", ip, limit=settings.rl_login_per_ip, window_seconds=_MINUTE)
    try:
        claims = decode_mfa_challenge_token(payload.mfa_token)
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="MFA challenge is invalid or expired")

    ratelimit.hit("mfa-challenge", claims["jti"], limit=settings.rl_mfa_attempts,
                  window_seconds=_QUARTER)
    ratelimit.check("mfa-user", claims["sub"], limit=settings.rl_mfa_attempts * 2,
                    window_seconds=_QUARTER)

    # FOR NO KEY UPDATE: serialises concurrent verifications (TOTP replay
    # guard) without blocking the FK checks of audit rows written on the
    # separate security-event connection (FOR UPDATE would self-deadlock).
    user = db.scalar(
        select(User).where(User.id == uuid.UUID(claims["sub"]))
        .with_for_update(key_share=True)
    )
    if user is None or user.status != "active" or not _mfa_enabled(user):
        raise HTTPException(status_code=401, detail="MFA challenge is invalid or expired")

    method = _check_second_factor(db, user, payload.code)
    if method is None:
        ratelimit.record("mfa-user", claims["sub"], window_seconds=_QUARTER)
        record_security_event(
            action="auth.mfa_failed",
            organization_id=claims["org"],
            actor_user_id=str(user.id),
            correlation_id=cid,
            ip_address=ip,
        )
        raise HTTPException(status_code=401, detail="Invalid verification code")

    org_id = uuid.UUID(claims["org"])
    set_request_context(db, user_id=str(user.id), org_id=str(org_id))
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.organization_id == org_id
        )
    )
    org_row = db.get(Organization, org_id)
    if (
        membership is None or membership.status != "active"
        or org_row is None or org_row.status != "active"
    ):
        raise HTTPException(status_code=403, detail="Membership is not active")
    return _issue_login(db, user=user, org_row=org_row, membership=membership,
                        request=request, method=f"password+{method}")


@router.post("/refresh", response_model=TokenPair)
def refresh(
    payload: RefreshIn, request: Request, db: Session = Depends(get_db, scope="function")
) -> TokenPair:
    """Rotate the refresh token. Replaying an already-rotated token revokes
    the whole session family (reuse detection) and is audited."""
    ip = get_client_ip(request)
    cid = get_correlation_id(request)
    ratelimit.hit("refresh-ip", ip, limit=settings.rl_refresh_per_ip, window_seconds=_MINUTE)
    token_hash = hash_refresh_token(payload.refresh_token)

    # Row lock: two concurrent refreshes of the same token must not both
    # rotate it (the loser sees it revoked and triggers reuse detection).
    row = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == token_hash)
        .with_for_update()
    )
    if row is None:
        raise _invalid_credentials()

    set_request_context(db, user_id=str(row.user_id), org_id=str(row.organization_id))
    now = datetime.now(timezone.utc)

    if row.revoked_at is not None:
        _revoke_session_family(row.family_id, now)
        record_security_event(
            action="auth.refresh_reuse_detected",
            organization_id=str(row.organization_id),
            actor_user_id=str(row.user_id),
            resource_type="session",
            resource_id=str(row.id),
            metadata={"family_id": str(row.family_id)},
            correlation_id=cid,
            ip_address=ip,
        )
        raise _invalid_credentials()

    if not session_is_live(row, now):
        raise _invalid_credentials()

    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        raise _invalid_credentials()

    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == row.organization_id,
        )
    )
    if membership is None or membership.status != "active":
        raise HTTPException(status_code=403, detail="Membership is not active")
    org_row = db.get(Organization, row.organization_id)
    if org_row is None or org_row.status != "active":
        raise HTTPException(status_code=403, detail="Organization is not active")

    row.revoked_at = now
    new_session, access, refresh_token = _new_session(
        db, user=user, org_id=row.organization_id, request=request,
        family_id=row.family_id,
        # pre-M7 sessions have no cap yet: start one now
        absolute_expires_at=row.absolute_expires_at,
    )
    row.replaced_by = new_session.id

    record_event(
        db,
        action="auth.refresh",
        organization_id=str(row.organization_id),
        actor_user_id=str(user.id),
        resource_type="session",
        resource_id=str(new_session.id),
        correlation_id=cid,
        ip_address=ip,
    )
    return _token_pair(access, refresh_token)


@router.post("/logout")
def logout(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    row = db.get(RefreshSession, principal.session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
    record_event(
        db,
        action="auth.logout",
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="session",
        resource_id=str(principal.session_id),
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )
    return {"status": "logged_out"}


@router.get("/me", response_model=MeOut)
def me(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> MeOut:
    org_row = db.get(Organization, principal.organization_id)
    if org_row is None:
        raise HTTPException(status_code=403, detail="Organization not found")
    return MeOut(
        user=UserOut.model_validate(principal.user),
        organization=OrganizationOut.model_validate(org_row),
        membership_id=principal.membership.id,
        branch_id=principal.membership.branch_id,
        role=principal.role_key,
        permissions=sorted(principal.permissions),
    )


# --- MFA enrolment -------------------------------------------------------------
def _audit_self(db: Session, principal: Principal, request: Request, action: str,
                metadata: dict | None = None) -> None:
    record_event(
        db,
        action=action,
        organization_id=str(principal.organization_id),
        actor_user_id=str(principal.user_id),
        resource_type="user",
        resource_id=str(principal.user_id),
        metadata=metadata,
        correlation_id=get_correlation_id(request),
        ip_address=get_client_ip(request),
    )


def _remaining_recovery_codes(db: Session, user_id: uuid.UUID) -> int:
    return len(db.scalars(
        select(MfaRecoveryCode.id)
        .where(MfaRecoveryCode.user_id == user_id)
        .where(MfaRecoveryCode.used_at.is_(None))
    ).all())


@router.get("/mfa/status", response_model=MfaStatusOut)
def mfa_status(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> MfaStatusOut:
    return MfaStatusOut(
        totp_enabled=_mfa_enabled(principal.user),
        recovery_codes_remaining=_remaining_recovery_codes(db, principal.user_id),
    )


@router.post("/mfa/totp/setup", response_model=TotpSetupOut)
def totp_setup(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> TotpSetupOut:
    """Start enrolment: a pending seed that becomes active only once a code
    from the authenticator app is confirmed via ``/mfa/totp/enable``."""
    user = principal.user
    if _mfa_enabled(user):
        raise HTTPException(status_code=409, detail="TOTP is already enabled")
    secret = new_totp_secret()
    user.mfa_totp_pending_enc = encrypt_field(secret, context=f"totp:{user.id}")
    _audit_self(db, principal, request, "auth.mfa_setup_started")
    return TotpSetupOut(secret=secret, otpauth_uri=totp_uri(secret, account=user.email))


@router.post("/mfa/totp/enable", response_model=RecoveryCodesOut)
def totp_enable(
    payload: TotpCodeIn,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> RecoveryCodesOut:
    user = principal.user
    if _mfa_enabled(user):
        raise HTTPException(status_code=409, detail="TOTP is already enabled")
    if not user.mfa_totp_pending_enc:
        raise HTTPException(status_code=409, detail="Start TOTP setup first")
    ratelimit.hit("mfa-enroll", str(user.id), limit=settings.rl_mfa_attempts,
                  window_seconds=_QUARTER)
    secret = decrypt_field(user.mfa_totp_pending_enc, context=f"totp:{user.id}")
    step = verify_totp(secret, payload.code, last_step=None)
    if step is None:
        raise HTTPException(status_code=422, detail="Invalid verification code")

    user.mfa_totp_secret_enc = user.mfa_totp_pending_enc
    user.mfa_totp_pending_enc = None
    user.mfa_totp_enabled_at = datetime.now(timezone.utc)
    user.mfa_totp_last_step = step
    db.execute(MfaRecoveryCode.__table__.delete().where(MfaRecoveryCode.user_id == user.id))
    codes = new_recovery_codes()
    for code in codes:
        db.add(MfaRecoveryCode(user_id=user.id, code_hash=hash_token(code)))
    _audit_self(db, principal, request, "auth.mfa_enabled", {"method": "totp"})
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/mfa/disable")
def mfa_disable(
    payload: MfaDisableIn,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    user = principal.user
    if not _mfa_enabled(user):
        raise HTTPException(status_code=409, detail="MFA is not enabled")
    ratelimit.hit("mfa-disable", str(user.id), limit=settings.rl_mfa_attempts,
                  window_seconds=_QUARTER)
    if not verify_password(payload.password, user.password_hash):
        raise _invalid_credentials()
    if _check_second_factor(db, user, payload.code) is None:
        raise HTTPException(status_code=401, detail="Invalid verification code")
    db.flush()  # persist the consumed code before the bulk delete below
    user.mfa_totp_secret_enc = None
    user.mfa_totp_pending_enc = None
    user.mfa_totp_enabled_at = None
    user.mfa_totp_last_step = None
    db.execute(MfaRecoveryCode.__table__.delete().where(MfaRecoveryCode.user_id == user.id))
    _audit_self(db, principal, request, "auth.mfa_disabled")
    return {"status": "disabled"}


# --- Passwords -------------------------------------------------------------------
@router.post("/password/change")
def password_change(
    payload: PasswordChangeIn,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    user = principal.user
    ratelimit.hit("password-change", str(user.id), limit=settings.rl_mfa_attempts,
                  window_seconds=_QUARTER)
    if not verify_password(payload.current_password, user.password_hash):
        raise _invalid_credentials()
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    revoked = _revoke_user_sessions(db, user.id, except_session=principal.session_id)
    _audit_self(db, principal, request, "auth.password_changed",
                {"other_sessions_revoked": revoked})
    return {"status": "changed"}


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
def password_forgot(
    payload: PasswordForgotIn,
    request: Request,
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    """Always 202, whether or not the e-mail is registered."""
    email = payload.email.lower()
    ip = get_client_ip(request)
    ratelimit.hit("pwreset-ip", ip, limit=settings.rl_password_reset_per_ip,
                  window_seconds=_HOUR)
    ratelimit.hit("pwreset-email", email, limit=settings.rl_password_reset_per_account,
                  window_seconds=_HOUR)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.status == "active":
        token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + PASSWORD_RESET_TTL,
            ip_address=ip,
        ))
        db.flush()
        link = f"{settings.web_base_url.rstrip('/')}/reset-password?token={token}"
        _send_email(
            user.email,
            "Reset your Aditya BioNova HMS password",
            f"A password reset was requested for your account.\n\n{link}\n\n"
            f"The link expires in {int(PASSWORD_RESET_TTL.total_seconds() // 60)} minutes "
            "and works once. If you did not ask for this, ignore this e-mail.",
            sensitive=True,
        )
        record_security_event(
            action="auth.password_reset_requested", actor_user_id=str(user.id),
            correlation_id=get_correlation_id(request), ip_address=ip,
        )
    return {"status": "accepted"}


@router.post("/password/reset")
def password_reset(
    payload: PasswordResetIn,
    request: Request,
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    ip = get_client_ip(request)
    ratelimit.hit("pwreset-ip", ip, limit=settings.rl_password_reset_per_ip,
                  window_seconds=_HOUR)
    row = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_token(payload.token))
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
    row.used_at = now
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = now
    # invalidate any other outstanding reset links too
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id)
        .where(PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    revoked = _revoke_user_sessions(db, user.id)
    ratelimit.clear("login-fail", user.email)
    record_security_event(
        action="auth.password_reset", actor_user_id=str(user.id),
        metadata={"sessions_revoked": revoked},
        correlation_id=get_correlation_id(request), ip_address=ip,
    )
    return {"status": "reset"}


# --- Sessions -----------------------------------------------------------------------
@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> list[SessionOut]:
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(RefreshSession)
        .where(RefreshSession.user_id == principal.user_id)
        .where(RefreshSession.organization_id == principal.organization_id)
        .where(RefreshSession.revoked_at.is_(None))
        .order_by(RefreshSession.issued_at.desc())
    ).all()
    return [
        SessionOut(
            id=r.id, created_at=r.issued_at, expires_at=r.expires_at,
            user_agent=r.user_agent, ip_address=r.ip_address,
            current=r.id == principal.session_id,
        )
        for r in rows
        if session_is_live(r, now)
    ]


@router.post("/sessions/revoke-others")
def revoke_other_sessions(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    revoked = _revoke_user_sessions(
        db, principal.user_id, except_session=principal.session_id,
        organization_id=principal.organization_id,
    )
    _audit_self(db, principal, request, "auth.sessions_revoked", {"count": revoked})
    return {"revoked": revoked}


@router.post("/sessions/{session_id}/revoke")
def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    row = db.get(RefreshSession, session_id)
    if (
        row is None or row.user_id != principal.user_id
        or row.organization_id != principal.organization_id
    ):
        raise HTTPException(status_code=404, detail="Session not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
    _audit_self(db, principal, request, "auth.session_revoked", {"session_id": str(row.id)})
    return {"status": "revoked"}


# --- Invitations ---------------------------------------------------------------------
@router.post("/invitations/accept", response_model=AuthSessionOut | MfaChallengeOut)
def accept_invitation(
    payload: InvitationAcceptIn,
    request: Request,
    db: Session = Depends(get_db, scope="function"),
) -> AuthSessionOut | MfaChallengeOut:
    """Join an organization from an e-mailed invitation.

    A new e-mail creates its account here (``full_name`` + password); an
    existing account must prove ownership with its current password — an
    administrator can never attach someone else's account to their tenant.
    """
    ip = get_client_ip(request)
    ratelimit.hit("invite-accept-ip", ip, limit=settings.rl_invite_accept_per_ip,
                  window_seconds=_HOUR)
    token_hash = hash_token(payload.token)
    org_id = db.scalar(text("SELECT invitation_org_for_token(:h)"), {"h": token_hash})
    if org_id is None:
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired")
    set_request_context(db, org_id=str(org_id))
    inv = db.scalar(
        select(MemberInvitation)
        .where(MemberInvitation.token_hash == token_hash)
        .with_for_update()
    )
    if inv is None or inv.status != "pending":  # pragma: no cover - raced
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired")

    user = db.scalar(select(User).where(User.email == inv.email))
    if user is None:
        if not payload.full_name:
            raise HTTPException(status_code=422, detail="full_name is required")
        if len(payload.password) < 10:
            raise HTTPException(status_code=422,
                                detail="password must be at least 10 characters")
        user = User(email=inv.email, full_name=payload.full_name,
                    password_hash=hash_password(payload.password))
        db.add(user)
        db.flush()
        created = True
    else:
        if user.status != "active" or not verify_password(payload.password, user.password_hash):
            raise _invalid_credentials()
        created = False

    set_request_context(db, user_id=str(user.id), org_id=str(org_id))
    if db.scalar(select(Membership.id).where(
        Membership.user_id == user.id, Membership.organization_id == org_id
    )):
        raise HTTPException(status_code=409, detail="Already a member of this organization")

    membership = Membership(user_id=user.id, organization_id=org_id,
                            branch_id=inv.branch_id, role_id=inv.role_id)
    db.add(membership)
    inv.status = "accepted"
    inv.accepted_user_id = user.id
    inv.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_event(
        db,
        action="member.invitation_accepted",
        organization_id=str(org_id),
        actor_user_id=str(user.id),
        resource_type="membership",
        resource_id=str(membership.id),
        metadata={"invitation_id": str(inv.id), "user_created": created},
        correlation_id=get_correlation_id(request),
        ip_address=ip,
    )
    org_row = db.get(Organization, org_id)
    if org_row is None or org_row.status != "active":
        raise HTTPException(status_code=403, detail="Organization is not active")
    if _mfa_enabled(user):
        # never bypass a second factor: the membership is kept and the
        # caller completes sign-in through /auth/mfa/verify
        token, _jti = create_mfa_challenge_token(user_id=str(user.id), org_id=str(org_id))
        return MfaChallengeOut(
            mfa_token=token, methods=["totp"], expires_in=MFA_CHALLENGE_TTL_SECONDS
        )
    return _issue_login(db, user=user, org_row=org_row, membership=membership,
                        request=request, method="invitation")
