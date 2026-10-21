"""M7.2: SaaS subscription billing — orders, payments, webhooks, invoices,
refunds and AI credit packs (Razorpay sandbox / local payment simulator).

This is the VENDOR's billing of clinics for the software. It is completely
separate from clinical patient billing (invoices/payments/ledger_entries of
migration 0006), which stays tenant-only.

RLS model (same mechanism as 0011):
* a tenant may READ its own orders, payments, invoices, refunds;
* a tenant may INSERT only a fresh order (status 'created') or a refund
  request (status 'requested') for itself;
* every state change (payment recorded, order paid, invoice issued, refund
  decided) needs the transaction-local ``app.platform_admin`` flag, which the
  API sets only inside the platform console or inside the fulfilment code
  after a payment signature has been verified.
* payments, invoices and webhook events are append-only (no UPDATE/DELETE);
  a refund produces a credit note, never an edit of the invoice.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"
PLATFORM = "coalesce(current_setting('app.platform_admin', true), '') = 'true'"

NEW_PERMISSIONS = [
    ("billing.saas.read", "View the clinic's software subscription invoices and payments"),
    ("billing.saas.pay", "Pay for the software subscription and AI credit packs"),
    ("billing.saas.refund_request", "Request a refund of a software subscription payment"),
]
ROLE_GRANTS = {
    "owner": ["billing.saas.read", "billing.saas.pay", "billing.saas.refund_request"],
    "admin": ["billing.saas.read", "billing.saas.pay"],
    "billing": ["billing.saas.read"],
    "auditor": ["billing.saas.read"],
}


def _ts(name: str, **kw) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def _uuid_pk() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _org_fk(nullable: bool = False) -> sa.Column:
    return sa.Column("organization_id", UUID(as_uuid=True),
                     sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=nullable)


def upgrade() -> None:
    # --- AI credit packs: vendor catalogue, prices unset until the owner sets them
    op.create_table(
        "ai_credit_packs",
        _uuid_pk(),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("price_paise", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("credits > 0", name="ck_aipack_credits"),
        sa.CheckConstraint("price_paise IS NULL OR price_paise > 0", name="ck_aipack_price"),
    )
    op.execute("""
        INSERT INTO ai_credit_packs (code, name, credits) VALUES
          ('ai_credits_100', 'AI credits — 100', 100),
          ('ai_credits_500', 'AI credits — 500', 500),
          ('ai_credits_2000', 'AI credits — 2,000', 2000)
    """)

    op.create_table(
        "saas_orders",
        _uuid_pk(),
        _org_fk(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("billing_cycle", sa.String(10), nullable=True),
        sa.Column("pack_id", UUID(as_uuid=True), sa.ForeignKey("ai_credit_packs.id"),
                  nullable=True),
        sa.Column("credits", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("tax_paise", sa.BigInteger(), nullable=False),
        sa.Column("total_paise", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("gst_rate_bp", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_order_id", sa.String(64), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="created"),
        sa.Column("failure_reason", sa.String(300), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("paid_at", nullable=True),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_saasorder_idem"),
        sa.CheckConstraint("kind IN ('subscription','ai_credits')", name="ck_saasorder_kind"),
        sa.CheckConstraint("status IN ('created','paid','failed','expired','cancelled')",
                           name="ck_saasorder_status"),
        sa.CheckConstraint("provider IN ('razorpay','simulator')", name="ck_saasorder_provider"),
        sa.CheckConstraint("amount_paise > 0 AND tax_paise >= 0 "
                           "AND total_paise = amount_paise + tax_paise",
                           name="ck_saasorder_amounts"),
        sa.CheckConstraint(
            "(kind = 'subscription' AND plan_id IS NOT NULL "
            " AND billing_cycle IN ('monthly','annual')) OR "
            "(kind = 'ai_credits' AND pack_id IS NOT NULL AND credits > 0)",
            name="ck_saasorder_shape"),
    )
    op.create_index("ix_saasorder_org_created", "saas_orders", ["organization_id", "created_at"])

    op.create_table(
        "saas_payments",
        _uuid_pk(),
        _org_fk(),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("saas_orders.id"),
                  nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_payment_id", sa.String(64), nullable=False, unique=True),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("method", sa.String(30), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(300), nullable=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('captured','failed')", name="ck_saaspay_status"),
        sa.CheckConstraint("source IN ('checkout','webhook','reconciliation')",
                           name="ck_saaspay_source"),
        sa.CheckConstraint("amount_paise > 0", name="ck_saaspay_amount"),
    )
    op.create_index("ix_saaspay_order", "saas_payments", ["order_id"])

    op.create_table(
        "saas_invoices",
        _uuid_pk(),
        _org_fk(),
        sa.Column("number", sa.String(30), nullable=False, unique=True),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("saas_orders.id"),
                  nullable=False),
        sa.Column("refund_id", UUID(as_uuid=True), nullable=True),
        sa.Column("related_invoice_id", UUID(as_uuid=True),
                  sa.ForeignKey("saas_invoices.id"), nullable=True),
        _ts("issued_at", nullable=False, server_default=sa.func.now()),
        _ts("period_start", nullable=True),
        _ts("period_end", nullable=True),
        sa.Column("seller", JSONB(), nullable=False),
        sa.Column("buyer", JSONB(), nullable=False),
        sa.Column("lines", JSONB(), nullable=False),
        sa.Column("subtotal_paise", sa.BigInteger(), nullable=False),
        sa.Column("tax_breakdown", JSONB(), nullable=False),
        sa.Column("tax_paise", sa.BigInteger(), nullable=False),
        sa.Column("total_paise", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.CheckConstraint("kind IN ('invoice','credit_note')", name="ck_saasinv_kind"),
        sa.CheckConstraint("total_paise = subtotal_paise + tax_paise", name="ck_saasinv_total"),
    )
    op.create_index("uq_saasinv_order_invoice", "saas_invoices", ["order_id"], unique=True,
                    postgresql_where=sa.text("kind = 'invoice'"))
    op.execute("CREATE SEQUENCE saas_invoice_number_seq")
    op.execute("CREATE SEQUENCE saas_credit_note_number_seq")

    op.create_table(
        "saas_refunds",
        _uuid_pk(),
        _org_fk(),
        sa.Column("payment_id", UUID(as_uuid=True), sa.ForeignKey("saas_payments.id"),
                  nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="requested"),
        sa.Column("requested_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _ts("decided_at", nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("provider_refund_id", sa.String(64), nullable=True, unique=True),
        sa.Column("error", sa.String(300), nullable=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount_paise > 0", name="ck_saasrefund_amount"),
        sa.CheckConstraint(
            "status IN ('requested','rejected','processed','failed')",
            name="ck_saasrefund_status"),
        # four-eyes: the person who decides is never the person who asked
        sa.CheckConstraint("decided_by IS NULL OR decided_by IS DISTINCT FROM requested_by",
                           name="ck_saasrefund_four_eyes"),
    )

    op.create_table(
        "saas_webhook_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("detail", sa.String(300), nullable=False, server_default=""),
        _ts("received_at", nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "event_id", name="uq_saaswebhook_event"),
        sa.CheckConstraint(
            "outcome IN ('processed','duplicate','ignored','rejected','mismatch','failed')",
            name="ck_saaswebhook_outcome"),
    )

    # --- RLS --------------------------------------------------------------------
    op.execute("ALTER TABLE ai_credit_packs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_credit_packs FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY aipack_read ON ai_credit_packs FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY aipack_platform ON ai_credit_packs FOR ALL "
               f"USING ({PLATFORM}) WITH CHECK ({PLATFORM})")

    for table in ("saas_orders", "saas_payments", "saas_invoices", "saas_refunds"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_read ON {table} FOR SELECT "
                   f"USING (organization_id = {GUC_ORG})")
        op.execute(f"CREATE POLICY {table}_platform ON {table} FOR ALL "
                   f"USING ({PLATFORM}) WITH CHECK ({PLATFORM})")
    op.execute(f"CREATE POLICY saas_orders_tenant_create ON saas_orders FOR INSERT "
               f"WITH CHECK (organization_id = {GUC_ORG} AND status = 'created')")
    op.execute(f"CREATE POLICY saas_refunds_tenant_request ON saas_refunds FOR INSERT "
               f"WITH CHECK (organization_id = {GUC_ORG} AND status = 'requested' "
               f"AND decided_by IS NULL)")

    op.execute("ALTER TABLE saas_webhook_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE saas_webhook_events FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY saaswebhook_platform ON saas_webhook_events FOR ALL "
               f"USING ({PLATFORM}) WITH CHECK ({PLATFORM})")

    # --- append-only financial records -------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_billing_record_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION '% is append-only (financial record)', TG_TABLE_NAME
            USING ERRCODE = 'integrity_constraint_violation';
        END $$;
    """)
    for table in ("saas_payments", "saas_invoices", "saas_webhook_events"):
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON "
                   f"{table} FOR EACH ROW EXECUTE FUNCTION forbid_billing_record_mutation()")
    # orders and refunds move forward only, never back to an earlier state
    op.execute("""
        CREATE OR REPLACE FUNCTION guard_saas_order_transition() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'saas_orders rows cannot be deleted'
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          IF OLD.status <> 'created' AND NEW.status IS DISTINCT FROM OLD.status
             AND NOT (OLD.status = 'failed' AND NEW.status = 'paid') THEN
            RAISE EXCEPTION 'saas order % cannot move from % to %', OLD.id, OLD.status,
              NEW.status USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          IF NEW.total_paise <> OLD.total_paise OR NEW.organization_id <> OLD.organization_id
             OR NEW.provider_order_id <> OLD.provider_order_id THEN
            RAISE EXCEPTION 'saas order amounts and identity are immutable'
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_saas_orders_transition BEFORE UPDATE OR DELETE ON saas_orders
          FOR EACH ROW EXECUTE FUNCTION guard_saas_order_transition();

        CREATE OR REPLACE FUNCTION guard_saas_refund_transition() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'saas_refunds rows cannot be deleted'
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          IF OLD.status <> 'requested' THEN
            RAISE EXCEPTION 'refund % is already %', OLD.id, OLD.status
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          IF NEW.amount_paise <> OLD.amount_paise OR NEW.payment_id <> OLD.payment_id THEN
            RAISE EXCEPTION 'refund amount and payment are immutable'
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_saas_refunds_transition BEFORE UPDATE OR DELETE ON saas_refunds
          FOR EACH ROW EXECUTE FUNCTION guard_saas_refund_transition();
    """)

    # --- grants -------------------------------------------------------------------
    op.execute("GRANT SELECT ON ai_credit_packs TO hms_app")
    op.execute("GRANT INSERT, UPDATE ON ai_credit_packs TO hms_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON saas_orders, saas_refunds TO hms_app")
    op.execute("GRANT SELECT, INSERT ON saas_payments, saas_invoices, saas_webhook_events "
               "TO hms_app")
    op.execute("GRANT USAGE ON SEQUENCE saas_invoice_number_seq, saas_credit_note_number_seq, "
               "saas_webhook_events_id_seq TO hms_app")

    # --- permissions ---------------------------------------------------------------
    for key, desc in NEW_PERMISSIONS:
        op.execute(sa.text("INSERT INTO permissions (key, description) VALUES (:k, :d) "
                           "ON CONFLICT (key) DO NOTHING").bindparams(k=key, d=desc))
    for role, keys in ROLE_GRANTS.items():
        for key in keys:
            op.execute(sa.text(
                "INSERT INTO role_permissions (role_id, permission_key) "
                "SELECT r.id, :p FROM roles r WHERE r.key = :r "
                "ON CONFLICT DO NOTHING").bindparams(r=role, p=key))


def downgrade() -> None:
    for role, keys in ROLE_GRANTS.items():
        for key in keys:
            op.execute(sa.text(
                "DELETE FROM role_permissions WHERE permission_key = :p AND role_id IN "
                "(SELECT id FROM roles WHERE key = :r)").bindparams(r=role, p=key))
    for key, _ in NEW_PERMISSIONS:
        op.execute(sa.text("DELETE FROM permissions WHERE key = :k").bindparams(k=key))
    for table in ("saas_webhook_events", "saas_refunds", "saas_invoices", "saas_payments",
                  "saas_orders"):
        op.drop_table(table)
    op.execute("DROP SEQUENCE IF EXISTS saas_invoice_number_seq")
    op.execute("DROP SEQUENCE IF EXISTS saas_credit_note_number_seq")
    op.execute("DROP FUNCTION IF EXISTS forbid_billing_record_mutation()")
    op.execute("DROP FUNCTION IF EXISTS guard_saas_order_transition()")
    op.execute("DROP FUNCTION IF EXISTS guard_saas_refund_transition()")
    op.drop_table("ai_credit_packs")
