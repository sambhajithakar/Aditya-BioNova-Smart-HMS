"""M8.1: SaaS billing corrections.

* **Late payments (H1).** A payment captured after its order expired or was
  cancelled was refused by the order-transition trigger, so money taken by
  the provider was never fulfilled. ``expired``/``cancelled`` → ``paid`` is
  now allowed (the money arrived; the order is honoured at its own price).
* **Refund ``processing`` state (M2).** The provider refund used to be called
  inside the decision transaction; a crash after the provider call but before
  commit lost the record of a refund that had happened. The decision now
  commits ``processing`` first, then calls the provider with the refund id as
  reference. Transitions: requested → rejected | processing;
  processing → processing (error noted) | processed | failed.
* **Least privilege.** The default privileges from 0001 gave ``hms_app``
  UPDATE/DELETE on every new table. The append-only triggers already refuse
  those, but the grants are now revoked as well.
"""
from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

ORDER_GUARD = """
    CREATE OR REPLACE FUNCTION guard_saas_order_transition() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'saas_orders rows cannot be deleted'
          USING ERRCODE = 'integrity_constraint_violation';
      END IF;
      IF OLD.status <> 'created' AND NEW.status IS DISTINCT FROM OLD.status
         AND NOT (OLD.status IN ({late}) AND NEW.status = 'paid') THEN
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
"""

REFUND_GUARD_NEW = """
    CREATE OR REPLACE FUNCTION guard_saas_refund_transition() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'saas_refunds rows cannot be deleted'
          USING ERRCODE = 'integrity_constraint_violation';
      END IF;
      IF NOT (
           (OLD.status = 'requested' AND NEW.status IN ('requested', 'rejected', 'processing'))
        OR (OLD.status = 'processing' AND NEW.status IN ('processing', 'processed', 'failed'))
      ) THEN
        RAISE EXCEPTION 'refund % cannot move from % to %', OLD.id, OLD.status, NEW.status
          USING ERRCODE = 'integrity_constraint_violation';
      END IF;
      IF NEW.amount_paise <> OLD.amount_paise OR NEW.payment_id <> OLD.payment_id THEN
        RAISE EXCEPTION 'refund amount and payment are immutable'
          USING ERRCODE = 'integrity_constraint_violation';
      END IF;
      IF OLD.decided_by IS NOT NULL AND NEW.decided_by IS DISTINCT FROM OLD.decided_by THEN
        RAISE EXCEPTION 'refund decision maker is immutable'
          USING ERRCODE = 'integrity_constraint_violation';
      END IF;
      RETURN NEW;
    END $$;
"""

REFUND_GUARD_OLD = """
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
"""

APPEND_ONLY = ("saas_payments", "saas_invoices", "saas_webhook_events")


def upgrade() -> None:
    op.execute(ORDER_GUARD.format(late="'failed', 'expired', 'cancelled'"))

    op.execute("ALTER TABLE saas_refunds DROP CONSTRAINT ck_saasrefund_status")
    op.execute("ALTER TABLE saas_refunds ADD CONSTRAINT ck_saasrefund_status CHECK "
               "(status IN ('requested','rejected','processing','processed','failed'))")
    op.execute(REFUND_GUARD_NEW)

    op.execute(f"REVOKE UPDATE, DELETE ON {', '.join(APPEND_ONLY)} FROM hms_app")
    op.execute("REVOKE DELETE ON saas_orders, saas_refunds, ai_credit_packs FROM hms_app")


def downgrade() -> None:
    op.execute("GRANT DELETE ON saas_orders, saas_refunds, ai_credit_packs TO hms_app")
    op.execute(f"GRANT UPDATE, DELETE ON {', '.join(APPEND_ONLY)} TO hms_app")

    # the old schema has no 'processing'; an in-flight refund becomes 'failed'
    # so an operator re-checks it against the provider
    op.execute(REFUND_GUARD_OLD.replace("IF OLD.status <> 'requested' THEN",
                                        "IF OLD.status NOT IN ('requested', 'processing') THEN"))
    op.execute("SELECT set_config('app.platform_admin', 'true', true)")  # FORCE RLS
    op.execute("UPDATE saas_refunds SET status = 'failed', "
               "error = left('in flight at downgrade: ' || coalesce(error, ''), 300) "
               "WHERE status = 'processing'")
    op.execute(REFUND_GUARD_OLD)
    op.execute("ALTER TABLE saas_refunds DROP CONSTRAINT ck_saasrefund_status")
    op.execute("ALTER TABLE saas_refunds ADD CONSTRAINT ck_saasrefund_status CHECK "
               "(status IN ('requested','rejected','processed','failed'))")

    op.execute(ORDER_GUARD.format(late="'failed'"))
