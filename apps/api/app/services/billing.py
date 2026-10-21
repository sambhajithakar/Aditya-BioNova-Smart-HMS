"""M3 services: invoice numbering, ledger posting, safety warnings.

Invoice numbering
-----------------
Per-tenant sequence ``INV-000001`` allocated under a per-organization
advisory transaction lock (same pattern as UHID), with the unique
``uq_invoice_org_number`` constraint as backstop.

GST on the discounted value (M7.0)
----------------------------------
Tax is charged on the TAXABLE value, i.e. after discount. An invoice-level
discount is allocated to the lines in proportion to their pre-tax value
(qty x unit price); each allocation is rounded DOWN to the paisa and the
left-over paise go one at a time to the lines with the largest rounding
remainder (largest-remainder method), so the allocations
always sum to the discount exactly and no line is discounted below zero.
Per line: ``tax = round((base - allocated_discount) x rate%)`` and
``line_total = base + tax``; the document keeps the identity
``total = subtotal - discount + tax_total`` (= sum(line_total) - discount).

Financial ledger
----------------
``ledger_entries`` is append-only at the database level. Posting rules:
* issuing an invoice writes ONE ``charge`` (debit) for the total;
* each succeeded payment writes ONE ``payment`` (credit) — unique partial
  index on payment_id makes double-posting impossible;
* each refund writes ONE ``refund`` (debit);
* voiding a fully unpaid invoice writes one ``adjustment`` (credit).
Balance due = charges - credits; it must always equal
``invoice.total - invoice.amount_paid``.

Safety warnings (blueprint R3.5)
--------------------------------
``rx_warnings`` runs BEFORE signing: it matches the patient's free-text
allergies against each drug's catalogued allergy terms / class (case-insensitive
substring on token boundaries) and detects the same drug twice in one Rx.
Allergy hits are blocking (sign requires ``acknowledge_allergies=true``);
duplicates are advisory.
"""
from __future__ import annotations

import re
import uuid
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    DrugCatalog,
    Invoice,
    LedgerEntry,
    Patient,
    Refund,
)
from .clinical import effective_allergies

UHID_ATTEMPTS = 3
_TOKEN_RE = re.compile(r"[a-z]+")


def next_invoice_number(db: Session, organization_id: uuid.UUID) -> str:
    """Allocate INV-000001 style numbers inside the tenant (advisory lock)."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"invoice:{organization_id}"},
    )
    last = db.scalar(
        select(func.max(Invoice.invoice_number)).where(
            Invoice.organization_id == organization_id
        )
    )
    seq = int(last.split("-")[-1]) + 1 if last else 1
    for attempt in range(UHID_ATTEMPTS):
        candidate = f"INV-{seq:06d}"
        exists = db.scalar(
            select(Invoice.id).where(
                Invoice.organization_id == organization_id,
                Invoice.invoice_number == candidate,
            )
        )
        if exists is None:
            return candidate
        seq += 1
    raise HTTPException(status_code=503, detail="Invoice numbering busy, retry")


def money(value: float | Decimal) -> Decimal:
    """Two-decimal banker-safe rounding for line and document totals."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_line_total(quantity: int, unit_price: float, tax_rate: float) -> Decimal:
    base = money(quantity) * money(unit_price)
    tax = (base * money(tax_rate) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return money(base + tax)


def compute_invoice_totals(
    lines: list[tuple[int, float, float]], discount: float | Decimal
) -> tuple[Decimal, Decimal, Decimal, Decimal, list[Decimal]]:
    """(subtotal, discount, tax_total, total, line_totals) for
    ``lines = [(quantity, unit_price, tax_rate)]`` — GST after discount.

    Raises 422 if the discount exceeds the subtotal.
    """
    bases = [money(Decimal(str(q)) * money(p)) for q, p, _ in lines]
    subtotal = money(sum(bases, Decimal("0")))
    disc = money(discount)
    if disc > subtotal:
        raise HTTPException(status_code=422, detail="Discount exceeds subtotal")

    shares = [Decimal("0.00")] * len(bases)
    if disc > 0:
        exact = [disc * base / subtotal for base in bases]
        for i, value in enumerate(exact):
            shares[i] = value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        leftover = disc - sum(shares, Decimal("0"))
        cent = Decimal("0.01")
        # largest remainder first (ties: larger line, then line order)
        order = sorted(range(len(bases)),
                       key=lambda i: (-(exact[i] - shares[i]), -bases[i], i))
        while leftover > 0:
            for i in order:
                if leftover <= 0:
                    break
                if shares[i] + cent <= bases[i]:
                    shares[i] += cent
                    leftover -= cent

    tax_total = Decimal("0")
    line_totals: list[Decimal] = []
    for (_, _, rate), base, share in zip(lines, bases, shares):
        tax = ((base - share) * money(rate) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        tax_total += tax
        line_totals.append(money(base + tax))
    tax_total = money(tax_total)
    return subtotal, disc, tax_total, money(subtotal - disc + tax_total), line_totals


# --- ledger -----------------------------------------------------------------
def post_ledger(
    db: Session,
    *,
    organization_id: uuid.UUID,
    invoice_id: uuid.UUID,
    entry_type: str,
    direction: str,
    amount: Decimal,
    description: str,
    actor_user_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
    refund_id: uuid.UUID | None = None,
) -> LedgerEntry:
    entry = LedgerEntry(
        organization_id=organization_id,
        invoice_id=invoice_id,
        payment_id=payment_id,
        refund_id=refund_id,
        entry_type=entry_type,
        direction=direction,
        amount=money(amount),
        description=description[:300],
        created_by=actor_user_id,
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Ledger entry already posted (double-post blocked)"
        )
    return entry


def balance_due(db: Session, invoice: Invoice) -> Decimal:
    """charges - credits from the ledger (source of truth)."""
    row = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (LedgerEntry.direction == "debit", LedgerEntry.amount),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (LedgerEntry.direction == "credit", LedgerEntry.amount),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(LedgerEntry.invoice_id == invoice.id)
    ).one()
    return money(Decimal(str(row[0])) - Decimal(str(row[1])))


def assert_ledger_consistent(db: Session, invoice: Invoice) -> None:
    """Invariant: ledger balance == invoice.total - amount_paid.

    A voided invoice is fully reversed by its adjustment entry, so its
    ledger position is zero regardless of the stored totals.
    """
    if invoice.status == "void":
        expected = Decimal("0.00")
    else:
        expected = money(
            Decimal(str(invoice.total)) - Decimal(str(invoice.amount_paid))
        )
    actual = balance_due(db, invoice)
    if actual != expected:
        raise HTTPException(
            status_code=500,
            detail=f"Ledger inconsistent: balance {actual} != expected {expected}",
        )


# --- prescription safety warnings ------------------------------------------
def _allergy_tokens(allergies: str) -> list[str]:
    return _TOKEN_RE.findall(allergies.lower())


def _drug_terms(drug: DrugCatalog) -> list[str]:
    terms = [t.strip().lower() for t in drug.allergy_terms.split(",") if t.strip()]
    terms.append(drug.drug_class.lower())
    terms.append(drug.generic_name.lower())
    return terms


def rx_warnings(
    db: Session,
    *,
    organization_id: uuid.UUID,
    patient: Patient,
    item_drug_ids: list[uuid.UUID],
) -> list[dict]:
    """Return [{kind, message, drug_ids}] — allergy hits + duplicate drugs."""
    warnings: list[dict] = []
    if not item_drug_ids:
        return warnings

    drugs = {
        d.id: d
        for d in db.scalars(
            select(DrugCatalog).where(DrugCatalog.id.in_(set(item_drug_ids)))
        ).all()
    }

    # 1) allergy check against the patient's free-text allergy list —
    #    including allergies recorded on records merged INTO this patient
    allergy_text = effective_allergies(db, patient)
    tokens = _allergy_tokens(allergy_text)
    if tokens:
        for drug_id in set(item_drug_ids):
            drug = drugs.get(drug_id)
            if drug is None:
                continue
            terms = _drug_terms(drug)
            hit = next(
                (
                    t
                    for tok in tokens
                    if len(tok) >= 3
                    for t in terms
                    if tok in t or t in tok
                ),
                None,
            )
            if hit:
                warnings.append(
                    {
                        "kind": "allergy",
                        "message": (
                            f"Allergy warning: patient records '{allergy_text}' "
                            f"and {drug.generic_name} matches '{hit}'."
                        ),
                        "drug_ids": [str(drug_id)],
                    }
                )

    # 2) same drug twice in this prescription
    counts: dict[uuid.UUID, int] = {}
    for drug_id in item_drug_ids:
        counts[drug_id] = counts.get(drug_id, 0) + 1
    for drug_id, n in counts.items():
        if n > 1 and (drug := drugs.get(drug_id)):
            warnings.append(
                {
                    "kind": "duplicate_drug",
                    "message": f"{drug.generic_name} appears {n} times in this Rx.",
                    "drug_ids": [str(drug_id)],
                }
            )
    return warnings


def assert_valid_drugs(
    db: Session, drug_ids: list[uuid.UUID]
) -> dict[uuid.UUID, DrugCatalog]:
    """Every item must reference an active entry of the validated catalog."""
    rows = {
        d.id: d
        for d in db.scalars(
            select(DrugCatalog).where(
                DrugCatalog.id.in_(drug_ids), DrugCatalog.is_active.is_(True)
            )
        ).all()
    }
    missing = [str(d) for d in drug_ids if d not in rows]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"message": "Unknown or inactive drug(s)", "drug_ids": missing},
        )
    return rows


# --- invoice status transitions --------------------------------------------
def settle_paid_status(db: Session, invoice: Invoice) -> None:
    """Flip issued -> paid when fully settled (never backwards manually)."""
    if invoice.status != "issued":
        return
    paid = money(Decimal(str(invoice.amount_paid)))
    total = money(Decimal(str(invoice.total)))
    if paid >= total > 0:
        invoice.status = "paid"


def refund_total_for_payment(db: Session, payment_id: uuid.UUID) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.payment_id == payment_id, Refund.status == "succeeded"
        )
    )
    return money(Decimal(str(total or 0)))


# re-export for routers that need idempotency helpers
__all__ = [
    "UHID_ATTEMPTS",
    "assert_ledger_consistent",
    "assert_valid_drugs",
    "balance_due",
    "compute_invoice_totals",
    "compute_line_total",
    "money",
    "next_invoice_number",
    "post_ledger",
    "refund_total_for_payment",
    "rx_warnings",
    "settle_paid_status",
]
