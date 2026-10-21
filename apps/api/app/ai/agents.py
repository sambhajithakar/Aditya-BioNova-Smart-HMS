"""Operations agents — propose → human approve → execute (AI_ARCHITECTURE.md §5).

Each agent is a DETERMINISTIC planner (no LLM in this phase) that reads with
RLS-scoped queries and returns typed proposals. Nothing is written to the
clinic's operational records until a human with ``ai.agents.approve`` AND the
action's own permission approves; the executor then re-validates against
CURRENT data and performs only safe actions:

| kind                    | on approval                                        | action permission |
|-------------------------|----------------------------------------------------|-------------------|
| followup_tasks          | creates reminder-call tasks (``ai_staff_tasks``);  | appointment.write |
|                         | no message is sent to anyone                       |                   |
| inventory_reorder       | creates a reorder DRAFT (``ai_reorder_drafts``);   | pharmacy.manage / |
|                         | no supplier order, no stock movement               | inventory.manage  |
| billing_reconciliation  | report draft accepted — NO money movement          | billing.read      |
| ops_daily_report        | report draft accepted                              | report.read       |

The model-facing tool registry is empty: a future LLM planner may only pick
among these planners; the write functions are reachable only from the
approval endpoint.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..deps import Principal
from ..models import Appointment, Branch, InventoryItem, Invoice, LedgerEntry, \
    OpdQueueEntry, StockBatch
from ..timeutil import clinic_day_bounds, clinic_today, clinic_tz
from . import forecast_service
from .common import args_hash
from .gateway import tenant_enabled_features
from .models_ai1 import AiReorderDraft, AiStaffTask

PROPOSAL_TTL = timedelta(hours=24)
MAX_PROPOSALS_PER_AGENT_PER_DAY = 50
PLANNER_VERSION = "agents-rules-1.0"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- typed payloads (validated on create AND again on approval) -----------------------------
class FollowupTask(_Strict):
    appointment_id: uuid.UUID
    starts_at: datetime
    priority: Literal["high", "normal"]
    no_show_risk: float | None = None
    reason: str = Field(max_length=300)


class FollowupPayload(_Strict):
    date: date
    branch_id: uuid.UUID
    tasks: list[FollowupTask] = Field(min_length=1, max_length=300)


class ReorderLine(_Strict):
    item_type: Literal["drug", "inventory"]
    item_id: uuid.UUID
    name: str
    on_hand: int = Field(ge=0)
    usable_on_hand: int = Field(ge=0)
    avg_daily_use: float | None = None
    days_of_cover: float | None = None
    suggested_qty: int = Field(gt=0, le=100000)
    reason: Literal["forecast_cover", "low_stock_rule", "below_reorder_level"]
    basis: str = Field(max_length=300)


class NearExpiry(_Strict):
    drug_id: uuid.UUID
    name: str
    projected_expiring_unused: int = Field(ge=0)


class ReorderPayload(_Strict):
    branch_id: uuid.UUID
    lines: list[ReorderLine] = Field(max_length=300)
    near_expiry: list[NearExpiry] = Field(default_factory=list, max_length=300)
    lead_time_days: int
    review_days: int


class UnpaidInvoice(_Strict):
    invoice_id: uuid.UUID
    invoice_number: str
    issued_at: datetime | None
    total: float
    amount_paid: float
    balance: float
    age_days: int


class LedgerMismatch(_Strict):
    invoice_id: uuid.UUID
    invoice_number: str
    amount_paid: float
    ledger_net_payments: float
    difference: float


class ReconciliationPayload(_Strict):
    as_of: date
    older_than_days: int
    unpaid: list[UnpaidInvoice] = Field(max_length=500)
    mismatches: list[LedgerMismatch] = Field(max_length=500)
    totals: dict[str, float]


class OpsReportPayload(_Strict):
    date: date
    figures: dict[str, float | int | None]


PAYLOADS: dict[str, type[BaseModel]] = {
    "followup_tasks": FollowupPayload, "inventory_reorder": ReorderPayload,
    "billing_reconciliation": ReconciliationPayload, "ops_daily_report": OpsReportPayload,
}
AGENT_KIND = {"appointment_followups": "followup_tasks",
              "inventory_monitor": "inventory_reorder",
              "billing_reconciliation": "billing_reconciliation",
              "ops_daily_report": "ops_daily_report"}


def action_permissions(kind: str, payload: dict) -> list[str]:
    if kind == "followup_tasks":
        return ["appointment.write"]
    if kind == "inventory_reorder":
        types = {line["item_type"] for line in payload.get("lines", [])}
        return sorted(({"pharmacy.manage"} if "drug" in types else set())
                      | ({"inventory.manage"} if "inventory" in types else set())) \
            or ["inventory.read"]
    if kind == "billing_reconciliation":
        return ["billing.read"]
    return ["report.read"]


def executable(kind: str) -> bool:
    return kind in ("followup_tasks", "inventory_reorder")


@dataclass
class Draft:
    kind: str
    title: str
    payload: dict
    rationale: str
    evidence: list
    dedupe_key: str
    branch_id: uuid.UUID | None


def _branches(db: Session, principal: Principal, branch_id: uuid.UUID | None):
    conds = [Branch.organization_id == principal.organization_id, Branch.status == "active"]
    if branch_id:
        conds.append(Branch.id == branch_id)
    return db.execute(select(Branch.id, Branch.name).where(*conds).order_by(Branch.name)).all()


def _dump(model: BaseModel) -> dict:
    return model.model_dump(mode="json")


# --- planners ------------------------------------------------------------------------------
def plan_followups(db: Session, principal: Principal, branch_id, **_) -> list[Draft]:
    tomorrow = clinic_today() + timedelta(days=1)
    t0, t1 = clinic_day_bounds(tomorrow)
    risk: dict[str, dict] = {}
    if "ai_forecast" in tenant_enabled_features(db, principal.organization_id) and \
            "appointment.read" in principal.permissions:
        ns = forecast_service.no_show(db, principal, branch_id, days_ahead=2)
        if ns["status"] == "ok":
            risk = {p["appointment_id"]: p for p in ns["predictions"]}
    drafts = []
    for bid, bname in _branches(db, principal, branch_id):
        appts = db.execute(select(Appointment.id, Appointment.starts_at).where(
            Appointment.organization_id == principal.organization_id,
            Appointment.branch_id == bid, Appointment.status == "scheduled",
            Appointment.starts_at >= t0, Appointment.starts_at < t1)
            .order_by(Appointment.starts_at)).all()
        if not appts:
            continue
        tasks = []
        for aid, starts in appts:
            r = risk.get(str(aid))
            high = bool(r and r["band"] == "high")
            reason = ("Reminder call — higher no-show risk: "
                      + "; ".join(f["description"] for f in r["factors"][:2])
                      if high else "Routine reminder call for tomorrow's appointment")
            tasks.append(FollowupTask(appointment_id=aid, starts_at=starts,
                                      priority="high" if high else "normal",
                                      no_show_risk=r["risk"] if r else None,
                                      reason=reason[:300]))
        tasks.sort(key=lambda t: (t.priority != "high", t.starts_at))
        payload = FollowupPayload(date=tomorrow, branch_id=bid, tasks=tasks)
        n_high = sum(t.priority == "high" for t in tasks)
        drafts.append(Draft(
            "followup_tasks", f"Reminder calls for {len(tasks)} appointment(s) on "
                              f"{tomorrow.isoformat()} — {bname}", _dump(payload),
            f"{len(tasks)} scheduled appointment(s) tomorrow; {n_high} flagged high no-show "
            "risk (statistical model, reminder prioritisation only)" if risk else
            f"{len(tasks)} scheduled appointment(s) tomorrow (no-show model not available: "
            "routine priority for all).",
            [{"type": "appointment", "id": str(t.appointment_id)} for t in tasks],
            f"followups:{bid}:{tomorrow.isoformat()}", bid))
    return drafts


def plan_inventory(db: Session, principal: Principal, branch_id, lead_time_days=7,
                   review_days=14, **_) -> list[Draft]:
    drafts = []
    drugs = forecast_service.pharmacy_demand(db, principal, branch_id, lead_time_days,
                                             review_days) \
        if "pharmacy.read" in principal.permissions else []
    items = forecast_service.inventory_demand(db, principal, branch_id, lead_time_days,
                                              review_days) \
        if "inventory.read" in principal.permissions else []
    reorder_level = {}
    if items:
        reorder_level = dict(db.execute(select(InventoryItem.id, InventoryItem.reorder_level)
                                        .where(InventoryItem.organization_id ==
                                               principal.organization_id)).all())
    for bid, bname in _branches(db, principal, branch_id):
        lines, near = [], []
        for d in (x for x in drugs if x["branch_id"] == str(bid)):
            if d["status"] == "ok":
                if d["projected_expiring_unused"] > 0:
                    near.append(NearExpiry(drug_id=d["item_id"], name=d["name"],
                                           projected_expiring_unused=d[
                                               "projected_expiring_unused"]))
                if d["suggested_order_qty"] > 0:
                    lines.append(ReorderLine(
                        item_type="drug", item_id=d["item_id"], name=d["name"],
                        on_hand=d["on_hand"], usable_on_hand=d["usable_on_hand"],
                        avg_daily_use=d["avg_daily_use"], days_of_cover=d["days_of_cover"],
                        suggested_qty=d["suggested_order_qty"], reason="forecast_cover",
                        basis=f"{d['method']} forecast {d['avg_daily_use']}/day; cover "
                              f"{lead_time_days}+{review_days} days + safety stock"))
            elif d["on_hand"] < 10:
                lines.append(ReorderLine(
                    item_type="drug", item_id=d["item_id"], name=d["name"],
                    on_hand=d["on_hand"], usable_on_hand=d["on_hand"],
                    suggested_qty=20 - d["on_hand"], reason="low_stock_rule",
                    basis="Rule: pharmacy low-stock threshold (10 units), topped up to 20; "
                          "no forecast (insufficient history)"))
        for it in (x for x in items if x["branch_id"] == str(bid)):
            level = reorder_level.get(uuid.UUID(it["item_id"]), 0)
            if it["status"] == "ok" and it["suggested_order_qty"] > 0:
                lines.append(ReorderLine(
                    item_type="inventory", item_id=it["item_id"], name=it["name"],
                    on_hand=it["on_hand"], usable_on_hand=it["usable_on_hand"],
                    avg_daily_use=it["avg_daily_use"], days_of_cover=it["days_of_cover"],
                    suggested_qty=it["suggested_order_qty"], reason="forecast_cover",
                    basis=f"{it['method']} forecast {it['avg_daily_use']}/day"))
            elif it["status"] != "ok" and it["on_hand"] <= level and level > 0:
                lines.append(ReorderLine(
                    item_type="inventory", item_id=it["item_id"], name=it["name"],
                    on_hand=it["on_hand"], usable_on_hand=it["on_hand"],
                    suggested_qty=max(1, 2 * level - it["on_hand"]),
                    reason="below_reorder_level",
                    basis=f"Rule: at/below reorder level {level}; topped up to 2× level "
                          "(no forecast: insufficient history)"))
        if not lines and not near:
            continue
        payload = ReorderPayload(branch_id=bid, lines=lines, near_expiry=near,
                                 lead_time_days=lead_time_days, review_days=review_days)
        drafts.append(Draft(
            "inventory_reorder", f"Reorder draft: {len(lines)} line(s) — {bname}",
            _dump(payload),
            f"{len(lines)} item(s) below their forecast cover or reorder rule; "
            f"{len(near)} drug(s) projected to expire before use.",
            [{"type": line.item_type, "id": str(line.item_id)} for line in lines],
            f"reorder:{bid}:{clinic_today().isoformat()}", bid))
    return drafts


def _money(v) -> float:
    return float(Decimal(str(v or 0)).quantize(Decimal("0.01")))


def reconciliation_payload(db: Session, principal: Principal,
                           older_than_days: int) -> ReconciliationPayload:
    org = principal.organization_id
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=older_than_days)
    unpaid = []
    for inv in db.scalars(select(Invoice).where(
            Invoice.organization_id == org, Invoice.status == "issued",
            Invoice.issued_at.is_not(None), Invoice.issued_at < cutoff)
            .order_by(Invoice.issued_at)).all():
        bal = _money(inv.total) - _money(inv.amount_paid)
        if bal > 0:
            unpaid.append(UnpaidInvoice(invoice_id=inv.id, invoice_number=inv.invoice_number,
                                        issued_at=inv.issued_at, total=_money(inv.total),
                                        amount_paid=_money(inv.amount_paid),
                                        balance=round(bal, 2),
                                        age_days=(now - inv.issued_at).days))
    led = dict(db.execute(
        select(LedgerEntry.invoice_id, func.coalesce(func.sum(
            case((LedgerEntry.entry_type == "payment", LedgerEntry.amount),
                      (LedgerEntry.entry_type == "refund", -LedgerEntry.amount), else_=0)), 0))
        .where(LedgerEntry.organization_id == org).group_by(LedgerEntry.invoice_id)).all())
    mismatches = []
    for inv in db.scalars(select(Invoice).where(Invoice.organization_id == org,
                                                Invoice.status != "draft")).all():
        ledger_net = _money(led.get(inv.id, 0))
        if abs(ledger_net - _money(inv.amount_paid)) >= 0.01:
            mismatches.append(LedgerMismatch(
                invoice_id=inv.id, invoice_number=inv.invoice_number,
                amount_paid=_money(inv.amount_paid), ledger_net_payments=ledger_net,
                difference=round(_money(inv.amount_paid) - ledger_net, 2)))
    return ReconciliationPayload(
        as_of=clinic_today(), older_than_days=older_than_days, unpaid=unpaid[:500],
        mismatches=mismatches[:500],
        totals={"unpaid_count": len(unpaid),
                "unpaid_balance": round(sum(u.balance for u in unpaid), 2),
                "mismatch_count": len(mismatches)})


def plan_reconciliation(db: Session, principal: Principal, branch_id, older_than_days=7,
                        **_) -> list[Draft]:
    p = reconciliation_payload(db, principal, older_than_days)
    return [Draft(
        "billing_reconciliation",
        f"Billing reconciliation draft ({p.as_of.isoformat()}): {len(p.unpaid)} unpaid > "
        f"{older_than_days} days, {len(p.mismatches)} ledger mismatch(es)", _dump(p),
        "Report draft only — approving files the report; no payment, refund or adjustment "
        "is made. Corrections go through the normal billing screens.",
        [{"type": "invoice", "id": str(u.invoice_id)} for u in p.unpaid[:50]]
        + [{"type": "invoice", "id": str(m.invoice_id)} for m in p.mismatches[:50]],
        f"recon:{p.as_of.isoformat()}:{older_than_days}", None)]


def ops_figures(db: Session, principal: Principal, day: date) -> dict:
    from ..routers.reports import report_summary

    s = report_summary(date_from=day, date_to=day, principal=principal, db=db)
    org = principal.organization_id
    t0, t1 = clinic_day_bounds(day)
    opd = db.scalar(select(func.count()).select_from(OpdQueueEntry).where(
        OpdQueueEntry.organization_id == org, OpdQueueEntry.service_date == day,
        OpdQueueEntry.status != "cancelled")) or 0
    appts = dict(db.execute(select(Appointment.status, func.count()).where(
        Appointment.organization_id == org, Appointment.starts_at >= t0,
        Appointment.starts_at < t1).group_by(Appointment.status)).all())
    expiring = db.scalar(select(func.count()).select_from(StockBatch).where(
        StockBatch.organization_id == org, StockBatch.quantity_on_hand > 0,
        StockBatch.expiry_date <= day + timedelta(days=30))) or 0
    return {"opd_visits": opd, "appointments_total": sum(appts.values()),
            "appointments_no_show": appts.get("no_show", 0),
            "payments": s.finance.revenue, "refunds": s.finance.refunds,
            "expenses": s.finance.expenses, "net": s.finance.net,
            "beds_total": s.ipd.beds_total, "beds_occupied": s.ipd.beds_occupied,
            "low_stock_items": len(s.inventory.low_stock),
            "batches_expiring_30d": expiring}


def plan_ops_report(db: Session, principal: Principal, branch_id, **_) -> list[Draft]:
    day = clinic_today() - timedelta(days=1)
    figures = ops_figures(db, principal, day)
    p = OpsReportPayload(date=day, figures=figures)
    return [Draft("ops_daily_report", f"Daily operations report — {day.isoformat()}",
                  _dump(p), "Figures computed with the Reports page functions "
                  "(reports.report_summary) plus OPD/appointment counts for the day.",
                  [{"type": "report", "id": f"summary:{day.isoformat()}"}],
                  f"ops:{day.isoformat()}", None)]


PLANNERS: dict[str, Callable[..., list[Draft]]] = {
    "appointment_followups": plan_followups, "inventory_monitor": plan_inventory,
    "billing_reconciliation": plan_reconciliation, "ops_daily_report": plan_ops_report,
}
# Tools a future model-based planner could be allowed to SELECT (read-only).
# Write/executor functions are deliberately absent.
MODEL_TOOL_ALLOWLIST = tuple(PLANNERS)


# --- re-validation + execution (only from the approval endpoint) --------------------------
class StaleProposal(Exception):
    pass


def execute(db: Session, principal: Principal, proposal) -> dict:
    """Re-validate the stored payload against CURRENT data and run the safe
    action. Raises StaleProposal when nothing valid remains."""
    model = PAYLOADS[proposal.kind].model_validate(proposal.payload)
    if args_hash(proposal.payload) != proposal.args_sha256:
        raise StaleProposal("payload hash mismatch (tampered)")
    org = principal.organization_id
    if proposal.kind == "followup_tasks":
        now = datetime.now(timezone.utc)
        ids = [t.appointment_id for t in model.tasks]
        current = dict(db.execute(select(Appointment.id, Appointment.status).where(
            Appointment.organization_id == org, Appointment.id.in_(ids),
            Appointment.starts_at > now)).all())
        created, skipped = [], []
        tz = clinic_tz()
        for t in model.tasks:
            if current.get(t.appointment_id) != "scheduled":
                skipped.append(str(t.appointment_id))
                continue
            task = AiStaffTask(organization_id=org, branch_id=model.branch_id,
                               proposal_id=proposal.id, kind="reminder_call",
                               title=f"Reminder call: appointment at "
                                     f"{t.starts_at.astimezone(tz).strftime('%d %b %H:%M')}",
                               subject_type="appointment", subject_id=t.appointment_id,
                               due_date=clinic_today(), priority=t.priority,
                               created_by=principal.user_id)
            db.add(task)
            db.flush()
            created.append(str(task.id))
        if not created:
            raise StaleProposal("no appointment is still scheduled")
        return {"action": "staff_tasks_created", "task_ids": created,
                "skipped_appointments": skipped, "messages_sent": 0}
    if proposal.kind == "inventory_reorder":
        lines = []
        for line in model.lines:
            if line.item_type == "drug":
                on_hand = db.scalar(select(func.coalesce(func.sum(
                    StockBatch.quantity_on_hand), 0)).where(
                    StockBatch.organization_id == org, StockBatch.branch_id == model.branch_id,
                    StockBatch.drug_id == line.item_id, StockBatch.status == "active",
                    StockBatch.expiry_date >= clinic_today())) or 0
            else:
                on_hand = db.scalar(select(InventoryItem.quantity_on_hand).where(
                    InventoryItem.organization_id == org,
                    InventoryItem.id == line.item_id)) or 0
            # stock received since the proposal covers (part of) the need
            still_needed = line.suggested_qty - max(0, int(on_hand) - line.on_hand)
            if still_needed > 0:
                lines.append({**line.model_dump(mode="json"), "on_hand_at_approval":
                              int(on_hand), "draft_qty": still_needed})
        if not lines:
            raise StaleProposal("stock is no longer below the reorder targets")
        draft = AiReorderDraft(organization_id=org, branch_id=model.branch_id,
                               proposal_id=proposal.id, lines=lines, status="draft",
                               created_by=principal.user_id)
        db.add(draft)
        db.flush()
        return {"action": "reorder_draft_created", "reorder_draft_id": str(draft.id),
                "lines": len(lines), "supplier_orders_placed": 0, "stock_movements": 0}
    if proposal.kind == "billing_reconciliation":
        fresh = reconciliation_payload(db, principal, model.older_than_days)
        if fresh.as_of != model.as_of or _dump(fresh)["totals"] != proposal.payload["totals"]:
            raise StaleProposal("billing figures changed since the draft; run the agent "
                                "again")
        return {"action": "report_filed", "money_movements": 0}
    fresh_figures = ops_figures(db, principal, model.date)
    if OpsReportPayload(date=model.date, figures=fresh_figures).model_dump(mode="json") \
            != proposal.payload:
        raise StaleProposal("figures changed since the draft; run the agent again")
    return {"action": "report_filed"}
