"""Customer support tickets (tenant side). Vendor replies come from the
platform console; vendor-internal notes are hidden from tenants by RLS."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..models import Organization, SupportTicket, SupportTicketMessage, User
from ..schemas import SupportMessageIn, SupportMessageOut, SupportTicketDetailOut, \
    SupportTicketIn, SupportTicketOut

router = APIRouter(prefix="/support", tags=["support"])


def _name(db: Session, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user.full_name if user else None


def ticket_out(db: Session, t: SupportTicket, *, with_org: bool = False) -> SupportTicketOut:
    org_name = None
    if with_org:
        org = db.get(Organization, t.organization_id)
        org_name = org.name if org else None
    return SupportTicketOut(
        id=t.id, number=t.number, subject=t.subject, category=t.category,
        priority=t.priority, status=t.status, created_at=t.created_at,
        updated_at=t.updated_at, created_by_name=_name(db, t.created_by),
        organization_name=org_name,
    )


def ticket_detail(db: Session, t: SupportTicket, *, with_org: bool = False
                  ) -> SupportTicketDetailOut:
    msgs = db.scalars(select(SupportTicketMessage).where(
        SupportTicketMessage.ticket_id == t.id).order_by(SupportTicketMessage.id)).all()
    return SupportTicketDetailOut(
        **ticket_out(db, t, with_org=with_org).model_dump(),
        messages=[SupportMessageOut(id=m.id, author_name=_name(db, m.author_user_id),
                                    author_side=m.author_side, body=m.body,
                                    internal=m.internal, created_at=m.created_at)
                  for m in msgs],
    )


def _audit(db, principal, request, action, ticket) -> None:
    record_event(db, action=action, organization_id=str(ticket.organization_id),
                 actor_user_id=str(principal.user_id), resource_type="support_ticket",
                 resource_id=str(ticket.id), metadata={"number": ticket.number},
                 correlation_id=get_correlation_id(request),
                 ip_address=get_client_ip(request))


def open_ticket(db: Session, principal: Principal, request: Request,
                payload: SupportTicketIn) -> SupportTicketOut:
    seq = db.scalar(text("SELECT nextval('support_ticket_number_seq')"))
    ticket = SupportTicket(
        organization_id=principal.organization_id, number=f"SUP-{seq:06d}",
        subject=payload.subject, category=payload.category, priority=payload.priority,
        created_by=principal.user_id,
    )
    db.add(ticket)
    db.flush()
    db.add(SupportTicketMessage(
        ticket_id=ticket.id, organization_id=principal.organization_id,
        author_user_id=principal.user_id, author_side="customer", body=payload.body,
    ))
    db.flush()
    db.refresh(ticket)
    _audit(db, principal, request, "support.ticket_opened", ticket)
    return ticket_out(db, ticket)


def _load(db: Session, principal: Principal, ticket_id: uuid.UUID) -> SupportTicket:
    t = db.get(SupportTicket, ticket_id)
    if t is None or t.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return t


@router.get("/tickets", response_model=list[SupportTicketOut])
def list_tickets(
    principal: Principal = Depends(require_permission("support.read")),
    db: Session = Depends(get_db, scope="function"),
) -> list[SupportTicketOut]:
    rows = db.scalars(select(SupportTicket).where(
        SupportTicket.organization_id == principal.organization_id)
        .order_by(SupportTicket.updated_at.desc())).all()
    return [ticket_out(db, t) for t in rows]


@router.post("/tickets", response_model=SupportTicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: SupportTicketIn,
    request: Request,
    principal: Principal = Depends(require_permission("support.write")),
    db: Session = Depends(get_db, scope="function"),
) -> SupportTicketOut:
    return open_ticket(db, principal, request, payload)


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetailOut)
def get_ticket(
    ticket_id: uuid.UUID,
    principal: Principal = Depends(require_permission("support.read")),
    db: Session = Depends(get_db, scope="function"),
) -> SupportTicketDetailOut:
    return ticket_detail(db, _load(db, principal, ticket_id))


@router.post("/tickets/{ticket_id}/messages", response_model=SupportTicketDetailOut)
def reply(
    ticket_id: uuid.UUID,
    payload: SupportMessageIn,
    request: Request,
    principal: Principal = Depends(require_permission("support.write")),
    db: Session = Depends(get_db, scope="function"),
) -> SupportTicketDetailOut:
    t = _load(db, principal, ticket_id)
    if t.status == "closed":
        raise HTTPException(status_code=409, detail="Ticket is closed")
    db.add(SupportTicketMessage(ticket_id=t.id, organization_id=t.organization_id,
                                author_user_id=principal.user_id, author_side="customer",
                                body=payload.body))
    if t.status in ("waiting_on_customer", "resolved"):
        t.status = "open"
    t.updated_at = datetime.now(timezone.utc)
    db.flush()
    _audit(db, principal, request, "support.ticket_replied", t)
    return ticket_detail(db, t)


@router.post("/tickets/{ticket_id}/close", response_model=SupportTicketOut)
def close(
    ticket_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_permission("support.write")),
    db: Session = Depends(get_db, scope="function"),
) -> SupportTicketOut:
    t = _load(db, principal, ticket_id)
    if t.status != "closed":
        t.status = "closed"
        t.updated_at = datetime.now(timezone.utc)
        db.flush()
        _audit(db, principal, request, "support.ticket_closed", t)
    return ticket_out(db, t)
