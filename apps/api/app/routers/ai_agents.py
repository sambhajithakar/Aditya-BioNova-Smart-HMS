"""AI operations agents: proposals with human approval (AI_ARCHITECTURE.md §5).

Mounted behind ``require_feature("ai_agents")``; tenant opt-in required.
Running an agent only creates PROPOSALS. Approval needs ``ai.agents.approve``
plus the action's own permission (checked at approval time, as the
approving user), re-validates against current data and executes only the
safe action of that kind. Rejected / expired proposals do nothing.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai import agents as A
from ..ai.common import args_hash, audit, require_opt_in, require_perm
from ..ai.models_ai1 import AiProposal, AiProposalEvent, AiReorderDraft, AiStaffTask
from ..db import get_db
from ..deps import Principal, require_permission
from ..schemas_ai1 import AgentRunIn, AgentRunOut, ProposalDecisionIn, ProposalEventOut, \
    ProposalOut, ReorderDraftOut, StaffTaskOut
from ..services.tenancy import load_branch

router = APIRouter(prefix="/ai/agents", tags=["ai-agents"])
FEATURE = "ai_agents"


def _out(p: AiProposal) -> ProposalOut:
    o = ProposalOut.model_validate(p)
    o.approve_requires = ["ai.agents.approve", *A.action_permissions(p.kind, p.payload)]
    o.executable = A.executable(p.kind)
    return o


def _event(db: Session, p: AiProposal, frm: str | None, to: str, actor, note: str = ""):
    db.add(AiProposalEvent(organization_id=p.organization_id, proposal_id=p.id,
                           from_status=frm, to_status=to, actor_user_id=actor,
                           note=note[:500]))


def _expire_stale(db: Session, principal: Principal) -> None:
    now = datetime.now(timezone.utc)
    for p in db.scalars(select(AiProposal).where(
            AiProposal.organization_id == principal.organization_id,
            AiProposal.status == "proposed", AiProposal.expires_at <= now)).all():
        p.status = "expired"
        _event(db, p, "proposed", "expired", None, "expired without a decision")
    db.flush()


def _get(db: Session, principal: Principal, pid: uuid.UUID) -> AiProposal:
    p = db.scalar(select(AiProposal).where(AiProposal.id == pid, AiProposal.organization_id ==
                                           principal.organization_id))
    if p is None:
        raise HTTPException(404, detail="Proposal not found")
    return p


@router.get("/catalog")
def catalog(principal: Principal = Depends(require_permission("ai.agents.use"))) -> list[dict]:
    return [{"agent": a, "kind": k, "executable_on_approval": A.executable(k),
             "on_approval": {"followup_tasks": "Creates reminder-call tasks for reception "
                                               "(no messages are sent)",
                             "inventory_reorder": "Creates a reorder draft (no supplier "
                                                  "order, no stock change)",
                             "billing_reconciliation": "Files the report draft (no money "
                                                       "movement)",
                             "ops_daily_report": "Files the report draft"}[k],
             "planner": A.PLANNER_VERSION}
            for a, k in A.AGENT_KIND.items()]


@router.post("/run", response_model=AgentRunOut)
def run_agent(payload: AgentRunIn, request: Request,
              principal: Principal = Depends(require_permission("ai.agents.use")),
              db: Session = Depends(get_db, scope="function")) -> AgentRunOut:
    require_opt_in(db, principal, FEATURE)
    if payload.branch_id:
        load_branch(db, principal, payload.branch_id)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    recent = db.scalar(select(func.count()).select_from(AiProposal).where(
        AiProposal.organization_id == principal.organization_id,
        AiProposal.agent == payload.agent, AiProposal.created_at >= since)) or 0
    if recent >= A.MAX_PROPOSALS_PER_AGENT_PER_DAY:
        raise HTTPException(429, detail="Agent proposal limit reached for today")
    _expire_stale(db, principal)
    drafts = A.PLANNERS[payload.agent](db, principal, payload.branch_id,
                                       older_than_days=payload.older_than_days)
    created, dupes = [], 0
    now = datetime.now(timezone.utc)
    for d in drafts:
        A.PAYLOADS[d.kind].model_validate(d.payload)  # structured-output validation
        p = AiProposal(organization_id=principal.organization_id, agent=payload.agent,
                       kind=d.kind, status="proposed", branch_id=d.branch_id,
                       title=d.title[:300], payload=d.payload, rationale=d.rationale,
                       evidence=d.evidence, args_sha256=args_hash(d.payload),
                       dedupe_key=d.dedupe_key[:200], created_by=principal.user_id,
                       created_at=now, expires_at=now + A.PROPOSAL_TTL)
        try:
            with db.begin_nested():
                db.add(p)
                db.flush()
        except IntegrityError:
            dupes += 1   # an identical proposal is already waiting for a decision
            continue
        _event(db, p, None, "proposed", principal.user_id, f"agent {payload.agent}")
        created.append(p)
    db.flush()
    audit(db, request, principal, "ai.agent.run", "ai_agent", payload.agent,
          {"created": [str(p.id) for p in created], "duplicates": dupes})
    return AgentRunOut(agent=payload.agent, created=[_out(p) for p in created],
                       skipped_duplicates=dupes,
                       note="Deterministic planner (no AI model). Proposals do nothing until "
                            "approved.")


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(status: str | None = None, limit: int = Query(default=50, ge=1, le=200),
                   principal: Principal = Depends(require_permission("ai.agents.use")),
                   db: Session = Depends(get_db, scope="function")) -> list[ProposalOut]:
    _expire_stale(db, principal)
    q = select(AiProposal).where(AiProposal.organization_id == principal.organization_id)
    if status:
        q = q.where(AiProposal.status == status)
    return [_out(p) for p in db.scalars(q.order_by(AiProposal.created_at.desc())
                                        .limit(limit)).all()]


@router.get("/proposals/{pid}")
def get_proposal(pid: uuid.UUID,
                 principal: Principal = Depends(require_permission("ai.agents.use")),
                 db: Session = Depends(get_db, scope="function")) -> dict:
    p = _get(db, principal, pid)
    events = db.scalars(select(AiProposalEvent).where(
        AiProposalEvent.organization_id == principal.organization_id,
        AiProposalEvent.proposal_id == p.id).order_by(AiProposalEvent.id)).all()
    return {"proposal": _out(p).model_dump(mode="json"),
            "events": [ProposalEventOut.model_validate(e).model_dump(mode="json")
                       for e in events]}


@router.post("/proposals/{pid}/approve", response_model=ProposalOut)
def approve(pid: uuid.UUID, payload: ProposalDecisionIn, request: Request,
            principal: Principal = Depends(require_permission("ai.agents.approve")),
            db: Session = Depends(get_db, scope="function")) -> ProposalOut:
    require_opt_in(db, principal, FEATURE)
    p = _get(db, principal, pid)
    if p.status != "proposed":
        raise HTTPException(409, detail=f"Proposal is {p.status}")
    now = datetime.now(timezone.utc)
    if p.expires_at <= now:
        p.status = "expired"
        _event(db, p, "proposed", "expired", principal.user_id, "approval after expiry")
        db.flush()
        return _out(p)
    # the approving human must hold the action's own permission NOW
    require_perm(principal, *A.action_permissions(p.kind, p.payload))
    p.status, p.decided_by, p.decided_at = "approved", principal.user_id, now
    p.decision_note = payload.note
    db.flush()
    _event(db, p, "proposed", "approved", principal.user_id, payload.note)
    try:
        with db.begin_nested():
            result = A.execute(db, principal, p)
        p.status, p.result = "executed", result
    except A.StaleProposal as exc:
        p.status, p.result = "failed", {"error": str(exc), "executed": False}
    p.executed_at = datetime.now(timezone.utc)
    db.flush()
    _event(db, p, "approved", p.status, principal.user_id, (p.result or {}).get("error", ""))
    audit(db, request, principal, f"ai.proposal.{p.status}", "ai_proposal", str(p.id),
          {"kind": p.kind, "result": p.result})
    db.flush()
    return _out(p)


@router.post("/proposals/{pid}/reject", response_model=ProposalOut)
def reject(pid: uuid.UUID, payload: ProposalDecisionIn, request: Request,
           principal: Principal = Depends(require_permission("ai.agents.approve")),
           db: Session = Depends(get_db, scope="function")) -> ProposalOut:
    p = _get(db, principal, pid)
    if p.status != "proposed":
        raise HTTPException(409, detail=f"Proposal is {p.status}")
    p.status, p.decided_by = "rejected", principal.user_id
    p.decided_at, p.decision_note = datetime.now(timezone.utc), payload.note
    db.flush()
    _event(db, p, "proposed", "rejected", principal.user_id, payload.note)
    audit(db, request, principal, "ai.proposal.rejected", "ai_proposal", str(p.id),
          {"kind": p.kind})
    db.flush()
    return _out(p)


@router.get("/tasks", response_model=list[StaffTaskOut])
def list_tasks(status: str = "open",
               principal: Principal = Depends(require_permission("appointment.read")),
               db: Session = Depends(get_db, scope="function")) -> list[StaffTaskOut]:
    rows = db.scalars(select(AiStaffTask).where(
        AiStaffTask.organization_id == principal.organization_id, AiStaffTask.status == status)
        .order_by(AiStaffTask.priority, AiStaffTask.created_at).limit(500)).all()
    return [StaffTaskOut.model_validate(r) for r in rows]


@router.post("/tasks/{task_id}/done", response_model=StaffTaskOut)
def complete_task(task_id: uuid.UUID, request: Request,
                  principal: Principal = Depends(require_permission("appointment.write")),
                  db: Session = Depends(get_db, scope="function")) -> StaffTaskOut:
    t = db.scalar(select(AiStaffTask).where(AiStaffTask.id == task_id,
                                            AiStaffTask.organization_id ==
                                            principal.organization_id))
    if t is None:
        raise HTTPException(404, detail="Task not found")
    if t.status != "open":
        raise HTTPException(409, detail=f"Task is {t.status}")
    t.status, t.completed_by = "done", principal.user_id
    t.completed_at = datetime.now(timezone.utc)
    db.flush()
    audit(db, request, principal, "ai.task.done", "ai_staff_task", str(t.id), {})
    return StaffTaskOut.model_validate(t)


@router.get("/reorder-drafts", response_model=list[ReorderDraftOut])
def list_reorder_drafts(principal: Principal = Depends(require_permission("ai.agents.use")),
                        db: Session = Depends(get_db, scope="function")
                        ) -> list[ReorderDraftOut]:
    rows = db.scalars(select(AiReorderDraft).where(
        AiReorderDraft.organization_id == principal.organization_id)
        .order_by(AiReorderDraft.created_at.desc()).limit(100)).all()
    return [ReorderDraftOut.model_validate(r) for r in rows]
