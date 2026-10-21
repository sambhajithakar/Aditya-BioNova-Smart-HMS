"""M8.1: purchased AI credits no longer expire at month end.

Until now a credit pack was recorded as a ``grant`` in the month it was
bought, and the gateway only added grants of the CURRENT month to the
allowance, so unused purchased credits silently disappeared on the 1st.

New ledger entry type ``pack_use``: when a request costs more than what is
left of the month's plan allowance, the excess is drawn from purchased
credits and written as ``pack_use`` instead of ``consume``. The purchased
balance is then simply ``sum(grant) - sum(pack_use)`` over ALL periods —
there is no expiry. The monthly allowance (``consume``) still resets each
month as before.

No live payment has ever been taken, so no real purchased credits exist.
Sandbox consumption recorded before this migration is not re-classified.
"""
from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ai_credit_ledger DROP CONSTRAINT ck_aicredit_type")
    op.execute("ALTER TABLE ai_credit_ledger ADD CONSTRAINT ck_aicredit_type CHECK "
               "(entry_type IN ('consume','grant','adjust','pack_use'))")
    op.create_index("ix_aicredit_org_type", "ai_credit_ledger",
                    ["organization_id", "entry_type"])


def downgrade() -> None:
    op.drop_index("ix_aicredit_org_type", table_name="ai_credit_ledger")
    # the ledger is append-only: a pack_use row cannot be rewritten, so a
    # downgrade is refused while any exists rather than losing the history
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM ai_credit_ledger WHERE entry_type = 'pack_use') THEN
            RAISE EXCEPTION 'ai_credit_ledger holds pack_use entries; downgrade refused';
          END IF;
        END $$;
    """)
    op.execute("ALTER TABLE ai_credit_ledger DROP CONSTRAINT ck_aicredit_type")
    op.execute("ALTER TABLE ai_credit_ledger ADD CONSTRAINT ck_aicredit_type CHECK "
               "(entry_type IN ('consume','grant','adjust'))")
