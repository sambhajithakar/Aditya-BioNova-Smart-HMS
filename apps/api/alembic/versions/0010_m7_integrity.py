"""M7.0 integrity hardening: signed-Rx INSERT guard, dispense caps, lab
order items, invoice/payment immutability, OPD queue uniqueness.

Revision ID: 0010
Revises: 0008  (re-pointed to 0009 at merge time)
Create Date: 2026-10-20

What this migration closes (AUDIT_REPORT ids in brackets)
---------------------------------------------------------
* [H1] ``trg_rxitem_immutable`` now fires on INSERT as well: rows can no
  longer be added to a signed/superseded prescription, even with raw SQL.
* [H4] ``prescription_items.dispense_quantity`` (nullable, 1..10000): the
  structured number of units the pharmacy may hand out in total.
* [H5] ``users.registration_number`` (medical council registration printed
  on the prescription).
* [C2/H7] ``lab_order_items``: the ordered tests are persisted (tenant RLS,
  same policy shape as every other tenant table). Status ordered ->
  resulted | cancelled; rows are never deleted. Existing orders are
  backfilled from the ``lab.order_created`` audit metadata (``test_ids``)
  plus any test that already carries a live result, so the new release
  rule holds for historical data as well.
* [C2] a lab order can only become ``released`` when every non-cancelled
  ordered test has a live RELEASED result (DB trigger backstop).
* [H9] ``invoices``: CHECK ``0 <= amount_paid <= total``.
* [M] invoices: no status regression (issued/paid -> draft, void -> *) and
  no DELETE of a non-draft invoice; payments and refunds are append-only
  for their money columns (only the status transitions the billing code
  performs are legal); completed encounters cannot be deleted.
* [M] ``uq_queue_one_active``: one active OPD queue entry per patient per
  service day (backstop for the join race).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0008"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    # ------------------------------------------------------------ columns
    op.add_column("users", sa.Column("registration_number", sa.String(60),
                                     nullable=True))
    op.add_column("prescription_items",
                  sa.Column("dispense_quantity", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_rxitem_dispense_qty", "prescription_items",
        "dispense_quantity IS NULL OR dispense_quantity BETWEEN 1 AND 10000")

    # ------------------------------------------- [H1] signed Rx INSERT guard
    # forbid_rxitem_mutation() (0006) already has the INSERT branch; the
    # trigger simply never fired for INSERT.
    op.execute("DROP TRIGGER IF EXISTS trg_rxitem_immutable ON prescription_items;")
    op.execute("""
        CREATE TRIGGER trg_rxitem_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON prescription_items
        FOR EACH ROW EXECUTE FUNCTION forbid_rxitem_mutation();
    """)

    # ----------------------------------------------------- [C2/H7] lab items
    op.create_table(
        "lab_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lab_orders.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("test_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lab_test_catalog.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="ordered"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("order_id", "test_id", name="uq_laborderitem_test"),
        sa.CheckConstraint("status IN ('ordered','resulted','cancelled')",
                           name="ck_laborderitem_status"),
    )
    op.create_index("ix_laborderitem_org_order", "lab_order_items",
                    ["organization_id", "order_id"])
    op.execute("ALTER TABLE lab_order_items ENABLE ROW LEVEL SECURITY;")
    op.execute(f"""
        CREATE POLICY lab_order_items_tenant ON lab_order_items
        USING (organization_id = {GUC_ORG})
        WITH CHECK (organization_id = {GUC_ORG});
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON lab_order_items TO hms_app;")
    op.execute("REVOKE DELETE ON lab_order_items FROM hms_app;")

    # backfill (runs as the migration owner, so RLS does not filter it):
    # 1) tests named in the order's creation audit event
    op.execute("""
        INSERT INTO lab_order_items (organization_id, order_id, test_id)
        SELECT DISTINCT o.organization_id, o.id, t.test_id::uuid
        FROM lab_orders o
        JOIN audit_events a
          ON a.action = 'lab.order_created'
         AND a.resource_type = 'lab_order'
         AND a.resource_id = o.id::text
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(a.metadata -> 'test_ids') = 'array'
                 THEN a.metadata -> 'test_ids' ELSE '[]'::jsonb END
        ) AS t(test_id)
        JOIN lab_test_catalog c ON c.id::text = t.test_id
        ON CONFLICT (order_id, test_id) DO NOTHING;
    """)
    # 2) any test that already carries a result (the old API accepted
    #    results for tests that were never ordered)
    op.execute("""
        INSERT INTO lab_order_items (organization_id, order_id, test_id)
        SELECT DISTINCT r.organization_id, r.order_id, r.test_id
        FROM lab_results r
        ON CONFLICT (order_id, test_id) DO NOTHING;
    """)
    op.execute("""
        UPDATE lab_order_items i SET status = 'resulted'
        WHERE EXISTS (SELECT 1 FROM lab_results r
                      WHERE r.order_id = i.order_id AND r.test_id = i.test_id
                        AND r.status <> 'superseded');
    """)
    op.execute("""
        UPDATE lab_order_items i SET status = 'cancelled'
        FROM lab_orders o
        WHERE o.id = i.order_id AND o.status = 'cancelled';
    """)

    # items: never deleted; test/order frozen; ordered -> resulted|cancelled
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_laborderitem_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'lab order items are permanent (blocked DELETE)';
            END IF;
            IF NEW.order_id <> OLD.order_id OR NEW.test_id <> OLD.test_id
               OR NEW.organization_id <> OLD.organization_id THEN
                RAISE EXCEPTION 'lab order item % is frozen', OLD.id;
            END IF;
            IF NEW.status <> OLD.status AND NOT (
                OLD.status = 'ordered' AND NEW.status IN ('resulted', 'cancelled')
            ) THEN
                RAISE EXCEPTION 'lab order item %: illegal transition % -> %',
                    OLD.id, OLD.status, NEW.status;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_laborderitem_guard
        BEFORE UPDATE OR DELETE ON lab_order_items
        FOR EACH ROW EXECUTE FUNCTION forbid_laborderitem_mutation();
    """)
    # an order is released only when every live ordered test is released
    op.execute("""
        CREATE OR REPLACE FUNCTION check_laborder_release() RETURNS trigger AS $$
        BEGIN
            IF NEW.status = 'released' AND OLD.status <> 'released' THEN
                IF EXISTS (
                    SELECT 1 FROM lab_order_items i
                    WHERE i.order_id = NEW.id AND i.status <> 'cancelled'
                      AND NOT EXISTS (
                          SELECT 1 FROM lab_results r
                          WHERE r.order_id = i.order_id
                            AND r.test_id = i.test_id
                            AND r.status = 'released')
                ) THEN
                    RAISE EXCEPTION
                        'lab order % cannot be released: ordered tests are '
                        'missing a released result', NEW.id;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_laborder_release_complete
        BEFORE UPDATE ON lab_orders
        FOR EACH ROW EXECUTE FUNCTION check_laborder_release();
    """)

    # ------------------------------------------------------ [H9] invoices
    conn = op.get_bind()
    bad = conn.execute(sa.text(
        "SELECT count(*) FROM invoices WHERE amount_paid > total"
    )).scalar() or 0
    if bad:
        # never silently rewrite money: enforce for new writes, leave the
        # historical rows for a supervised reconciliation (VALIDATE later)
        op.execute("""
            ALTER TABLE invoices ADD CONSTRAINT ck_inv_amount_paid_bound
            CHECK (amount_paid >= 0 AND amount_paid <= total) NOT VALID;
        """)
    else:
        op.create_check_constraint(
            "ck_inv_amount_paid_bound", "invoices",
            "amount_paid >= 0 AND amount_paid <= total")

    # status may only move forward; issued documents are never deleted
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_invoice_regression() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'draft' THEN
                    RAISE EXCEPTION 'invoice % is % and cannot be deleted',
                        OLD.id, OLD.status;
                END IF;
                RETURN OLD;
            END IF;
            IF NEW.status <> OLD.status AND NOT (
                (OLD.status = 'draft' AND NEW.status IN ('issued', 'void'))
                OR (OLD.status = 'issued' AND NEW.status IN ('paid', 'void'))
                OR (OLD.status = 'paid' AND NEW.status = 'issued')
            ) THEN
                RAISE EXCEPTION 'invoice %: illegal status change % -> %',
                    OLD.id, OLD.status, NEW.status;
            END IF;
            IF OLD.status = 'void' AND NEW.amount_paid <> OLD.amount_paid THEN
                RAISE EXCEPTION 'invoice % is void and frozen', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_inv_status_forward
        BEFORE UPDATE OR DELETE ON invoices
        FOR EACH ROW EXECUTE FUNCTION forbid_invoice_regression();
    """)

    # payments: money columns frozen, only the code's status transitions
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_payment_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'payments are append-only (blocked DELETE)';
            END IF;
            IF NEW.invoice_id <> OLD.invoice_id
               OR NEW.organization_id <> OLD.organization_id
               OR NEW.amount <> OLD.amount
               OR NEW.method <> OLD.method
               OR NEW.gateway <> OLD.gateway
               OR NEW.created_at <> OLD.created_at THEN
                RAISE EXCEPTION 'payment % is append-only (money columns frozen)',
                    OLD.id;
            END IF;
            IF OLD.status <> 'pending' AND (
                NEW.gateway_ref <> OLD.gateway_ref
                OR NEW.failure_reason <> OLD.failure_reason) THEN
                RAISE EXCEPTION 'payment % is settled and frozen', OLD.id;
            END IF;
            IF NEW.status <> OLD.status AND NOT (
                (OLD.status = 'pending' AND NEW.status IN ('succeeded', 'failed'))
                OR (OLD.status IN ('succeeded', 'partially_refunded')
                    AND NEW.status IN ('partially_refunded', 'refunded'))
            ) THEN
                RAISE EXCEPTION 'payment %: illegal status change % -> %',
                    OLD.id, OLD.status, NEW.status;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_payment_append_only
        BEFORE UPDATE OR DELETE ON payments
        FOR EACH ROW EXECUTE FUNCTION forbid_payment_mutation();
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_refund_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'refunds are append-only (blocked DELETE)';
            END IF;
            IF (to_jsonb(NEW) - 'status') <> (to_jsonb(OLD) - 'status') THEN
                RAISE EXCEPTION 'refund % is append-only', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_refund_append_only
        BEFORE UPDATE OR DELETE ON refunds
        FOR EACH ROW EXECUTE FUNCTION forbid_refund_mutation();
    """)

    # ----------------------------------------------- encounters: no DELETE
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_completed_encounter_delete()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'completed' THEN
                RAISE EXCEPTION 'encounter % is completed and cannot be deleted',
                    OLD.id;
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_enc_completed_no_delete
        BEFORE DELETE ON encounters
        FOR EACH ROW EXECUTE FUNCTION forbid_completed_encounter_delete();
    """)

    # ------------------------------------------ OPD queue: one active entry
    op.execute("""
        CREATE UNIQUE INDEX uq_queue_one_active
        ON opd_queue (organization_id, patient_id, service_date)
        WHERE status IN ('waiting', 'called', 'in_consultation');
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_queue_one_active;")
    for trig, table in [
        ("trg_enc_completed_no_delete", "encounters"),
        ("trg_refund_append_only", "refunds"),
        ("trg_payment_append_only", "payments"),
        ("trg_inv_status_forward", "invoices"),
        ("trg_laborder_release_complete", "lab_orders"),
        ("trg_laborderitem_guard", "lab_order_items"),
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS {trig} ON {table};")
    for fn in ["forbid_completed_encounter_delete", "forbid_refund_mutation",
               "forbid_payment_mutation", "forbid_invoice_regression",
               "check_laborder_release", "forbid_laborderitem_mutation"]:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}();")
    op.drop_constraint("ck_inv_amount_paid_bound", "invoices", type_="check")

    op.execute("DROP POLICY IF EXISTS lab_order_items_tenant ON lab_order_items;")
    op.drop_index("ix_laborderitem_org_order", table_name="lab_order_items")
    op.drop_table("lab_order_items")

    op.execute("DROP TRIGGER IF EXISTS trg_rxitem_immutable ON prescription_items;")
    op.execute("""
        CREATE TRIGGER trg_rxitem_immutable
        BEFORE UPDATE OR DELETE ON prescription_items
        FOR EACH ROW EXECUTE FUNCTION forbid_rxitem_mutation();
    """)
    op.drop_constraint("ck_rxitem_dispense_qty", "prescription_items",
                       type_="check")
    op.drop_column("prescription_items", "dispense_quantity")
    op.drop_column("users", "registration_number")
