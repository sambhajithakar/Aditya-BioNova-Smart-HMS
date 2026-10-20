"""Authentication, tenant context and RBAC dependencies.

Security invariants enforced here:
* Tenant/org identity comes from the verified JWT **and** the server-side
  session — never from headers or query parameters supplied by the client.
* Access tokens are rejected once their backing session is revoked/expired,
  so logout and refresh-rotation take effect immediately.
* Every authenticated request installs the transaction-local RLS context.
* A suspended organization or membership loses access on its next request,
  not only at the next login.
"""
from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, set_request_context
from .models import Membership, Organization, RefreshSession, Role, RolePermission, User
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

# account self-service stays reachable while MFA enrolment is pending
_SELF_SERVICE_PREFIX = "/api/v1/auth/"


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass
class Principal:
    user: User
    organization_id: uuid.UUID
    session_id: uuid.UUID
    membership: Membership
    role_key: str
    permissions: set[str] = field(default_factory=set)
    mfa_enrollment_required: bool = False

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def is_platform_admin(self) -> bool:
        """Vendor operator: super-admin flag + TOTP (unless a local demo
        explicitly disables the MFA requirement)."""
        if not self.user.is_superadmin:
            return False
        return (self.user.mfa_totp_enabled_at is not None
                or not get_settings().platform_mfa_required)


def _is_trusted_proxy(host: str | None) -> bool:
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(
        addr in ipaddress.ip_network(net, strict=False)
        for net in get_settings().trusted_proxies
    )


def get_client_ip(request: Request) -> str | None:
    """Client address; ``X-Forwarded-For`` is honoured only when the direct
    peer is a configured trusted proxy (otherwise any client could spoof
    the IP recorded in audit events and used for rate limiting)."""
    peer = request.client.host if request.client else None
    fwd = request.headers.get("x-forwarded-for")
    if fwd and _is_trusted_proxy(peer):
        # right-most address not belonging to our own proxy chain
        for hop in reversed([h.strip() for h in fwd.split(",") if h.strip()]):
            if not _is_trusted_proxy(hop):
                return hop[:60]
    return peer[:60] if peer else None


def session_is_live(row: RefreshSession | None, now: datetime) -> bool:
    return (
        row is not None
        and row.revoked_at is None
        and row.expires_at > now
        and (row.absolute_expires_at is None or row.absolute_expires_at > now)
    )


def get_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "")


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db, scope="function"),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        claims = decode_access_token(credentials.credentials)
    except pyjwt.PyJWTError:
        raise _unauthorized("Invalid or expired token")

    session_id = uuid.UUID(claims["sid"])
    org_id = uuid.UUID(claims["org"])
    user_id = uuid.UUID(claims["sub"])

    session_row = db.get(RefreshSession, session_id)
    if (
        not session_is_live(session_row, datetime.now(timezone.utc))
        or session_row.user_id != user_id
        or session_row.organization_id != org_id
    ):
        raise _unauthorized("Session is no longer valid")

    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise _unauthorized("Account is not active")

    # Install tenant context for PostgreSQL row-level security BEFORE any
    # tenant-scoped query runs.
    set_request_context(
        db, user_id=str(user.id), org_id=str(org_id), bootstrap=False
    )

    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == org_id,
            Membership.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active membership for this organization",
        )

    org_row = db.get(Organization, org_id)
    if org_row is None or org_row.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization is not active"
        )

    role = db.get(Role, membership.role_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Membership role missing"
        )

    # Role-aware MFA policy: members of listed roles (and platform operators)
    # must enrol TOTP; until then only account self-service endpoints work.
    must_enrol = user.mfa_totp_enabled_at is None and (
        role.key in (org_row.mfa_required_roles or [])
        or (user.is_superadmin and get_settings().platform_mfa_required)
    )
    if must_enrol and not request.url.path.startswith(_SELF_SERVICE_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="mfa_enrollment_required"
        )

    if user.is_superadmin:
        from .models import Permission

        permissions = set(db.scalars(select(Permission.key)).all())
    else:
        permissions = set(
            db.scalars(
                select(RolePermission.permission_key).where(
                    RolePermission.role_id == role.id
                )
            ).all()
        )

    principal = Principal(
        user=user,
        organization_id=org_id,
        session_id=session_id,
        membership=membership,
        role_key=role.key,
        permissions=permissions,
        mfa_enrollment_required=must_enrol,
    )
    # read by the PHI-access audit middleware (main.py)
    request.state.principal = principal
    return principal


def require_platform_admin(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db, scope="function"),
) -> Principal:
    """Vendor console guard. Sets the transaction-local ``app.platform_admin``
    GUC, which opens ONLY the commercial tables (plans, subscriptions,
    support, organizations) — patient/clinical tables keep tenant-only RLS."""
    if not principal.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Platform administrator access required")
    db.execute(text("SELECT set_config('app.platform_admin', 'true', true)"))
    return principal


def require_permission(permission_key: str):
    """Route guard: 403 unless the principal's role holds the permission."""

    def checker(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if permission_key not in principal.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_key}",
            )
        return principal

    return checker
