"""Development/test-only helpers. Not mounted outside ENVIRONMENT=development|test.

``/dev/outbox`` exposes messages recorded by the mock communications
provider, so demos can follow password-reset and invitation links without
any real e-mail/SMS/WhatsApp delivery.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CommsMessage
from ..schemas import OutboxMessageOut

router = APIRouter(prefix="/dev", tags=["dev"])


@router.get("/outbox", response_model=list[OutboxMessageOut])
def outbox(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db, scope="function"),
) -> list[OutboxMessageOut]:
    rows = db.scalars(
        select(CommsMessage).order_by(CommsMessage.id.desc()).limit(limit)
    ).all()
    return [
        OutboxMessageOut(id=r.id, channel=r.channel, to=r.recipient, subject=r.subject,
                         body=r.body, status=r.status, created_at=r.created_at)
        for r in rows
    ]
