"""M6 reports API: IPD, finance and inventory summaries for one period.

Reports only aggregate THIS tenant's rows (the queries all carry
``organization_id`` and RLS is the backstop), and every endpoint needs
``report.read`` — support and auditor hold no M6 grants (least privilege).
Numbers are read-only derivations of frozen records: nothing is written or
mutated by a report.

Finance (M7.0 / H8): revenue and refunds are read from the append-only
LEDGER, not from the mutable ``payments.status``: revenue = every settled
payment (one ``payment`` credit each, posted at settlement time) whether or
not it was refunded later; refunds = every ``refund`` debit, subtracted
exactly once in ``net``. A fully refunded ₹1000 payment therefore reports
revenue 1000, refunds 1000, net 0.

Period boundaries are CLINIC calendar days (``app.timeutil``, IST by
default), not UTC days.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, require_permission
from ..models import (
    Admission,
    Bed,
    Expense,
    InventoryItem,
    LedgerEntry,
)
from ..schemas import (
    FinanceCategoryRow,
    FinanceReport,
    IpdReport,
    InventoryReport,
    ReportSummaryOut,
)
from ..timeutil import clinic_day_bounds, clinic_today

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=ReportSummaryOut)
def report_summary(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    principal: Principal = Depends(require_permission("report.read")),
    db: Session = Depends(get_db, scope="function"),
) -> ReportSummaryOut:
    today = clinic_today()
    date_to = date_to or today
    date_from = date_from or (date_to - timedelta(days=30))
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    org = principal.organization_id
    # [period_start, period_end) in UTC for the clinic-local days
    period_start = clinic_day_bounds(date_from)[0]
    period_end = clinic_day_bounds(date_to)[1]

    beds_total = db.scalar(
        select(func.count()).select_from(Bed).where(Bed.organization_id == org)
    ) or 0
    beds_maintenance = db.scalar(
        select(func.count()).select_from(Bed).where(
            Bed.organization_id == org, Bed.status == "maintenance"
        )
    ) or 0
    beds_occupied = db.scalar(
        select(func.count()).select_from(Admission).where(
            Admission.organization_id == org, Admission.status == "admitted"
        )
    ) or 0
    currently_admitted = beds_occupied
    admissions_in_period = db.scalar(
        select(func.count()).select_from(Admission).where(
            Admission.organization_id == org,
            Admission.admitted_at >= period_start,
            Admission.admitted_at < period_end,
        )
    ) or 0
    discharges_in_period = db.scalar(
        select(func.count()).select_from(Admission).where(
            Admission.organization_id == org,
            Admission.status == "discharged",
            Admission.discharged_at >= period_start,
            Admission.discharged_at < period_end,
        )
    ) or 0
    deaths_in_period = db.scalar(
        select(func.count()).select_from(Admission).where(
            Admission.organization_id == org,
            Admission.status == "discharged",
            Admission.discharge_outcome == "death",
            Admission.discharged_at >= period_start,
            Admission.discharged_at < period_end,
        )
    ) or 0

    def _ledger_sum(entry_type: str):
        return db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.organization_id == org,
                LedgerEntry.entry_type == entry_type,
                LedgerEntry.created_at >= period_start,
                LedgerEntry.created_at < period_end,
            )
        ) or 0

    # settled payments (refunded later or not) / refunds — each counted once
    revenue = _ledger_sum("payment")
    refunds = _ledger_sum("refund")

    expense_rows = db.execute(
        select(
            Expense.category,
            func.sum(Expense.amount),
        )
        .where(
            Expense.organization_id == org,
            Expense.status == "recorded",
            Expense.expense_date >= date_from,
            Expense.expense_date <= date_to,
        )
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
    ).all()
    expense_total = sum(float(r[1] or 0) for r in expense_rows)
    by_category = [
        FinanceCategoryRow(category=r[0], total=float(r[1] or 0))
        for r in expense_rows
    ]

    items_active = db.scalar(
        select(func.count()).select_from(InventoryItem).where(
            InventoryItem.organization_id == org,
            InventoryItem.status == "active",
        )
    ) or 0
    low_rows = db.scalars(
        select(InventoryItem).where(
            InventoryItem.organization_id == org,
            InventoryItem.status == "active",
            InventoryItem.reorder_level > 0,
            InventoryItem.quantity_on_hand <= InventoryItem.reorder_level,
        )
        .order_by(InventoryItem.quantity_on_hand)
        .limit(20)
    ).all()

    return ReportSummaryOut(
        from_date=date_from,
        to_date=date_to,
        ipd=IpdReport(
            currently_admitted=currently_admitted,
            admissions_in_period=admissions_in_period,
            discharges_in_period=discharges_in_period,
            deaths_in_period=deaths_in_period,
            beds_total=beds_total,
            beds_occupied=beds_occupied,
            beds_maintenance=beds_maintenance,
        ),
        finance=FinanceReport(
            revenue=float(revenue),
            refunds=float(refunds),
            expenses=expense_total,
            net=float(revenue) - float(refunds) - expense_total,
            by_category=by_category,
        ),
        inventory=InventoryReport(
            items_active=items_active,
            low_stock=[
                {
                    "id": str(i.id),
                    "name": i.name,
                    "unit": i.unit,
                    "quantity_on_hand": i.quantity_on_hand,
                    "reorder_level": i.reorder_level,
                }
                for i in low_rows
            ],
        ),
    )