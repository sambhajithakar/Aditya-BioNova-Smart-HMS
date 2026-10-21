"""AI-0: AI gateway governance — tenant opt-in, AI request audit, credit ledger.

Revision ID: 0012
Revises: 0011

See docs/AI_ARCHITECTURE.md §2. All three tables are tenant-scoped with strict
RLS. ``ai_requests`` and ``ai_credit_ledger`` are append-only (no UPDATE /
DELETE grants + trigger, as for audit_events). Credit usage is ALWAYS the sum
of the ledger for the clinic-month, computed under a per-tenant advisory lock
— there is no mutable running total a tenant could reset.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"

AI_PERMS = [
    ("ai.copilot.use", "Ask the AI business copilot about the clinic's own figures"),
    ("ai.settings.manage", "Switch AI features on or off for the clinic"),
    ("ai.audit.read", "Review the clinic's AI request log and credit usage"),
]
ROLE_GRANTS = {
    "owner": [p for p, _ in AI_PERMS],
    "admin": [p for p, _ in AI_PERMS],
    "billing": ["ai.copilot.use"],
    "doctor": ["ai.copilot.use"],
    "auditor": ["ai.audit.read"],
}


def upgrade() -> None:
    op.create_table(
        "ai_tenant_settings",
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled_features", ARRAY(sa.String(40)), nullable=False,
                  server_default="{}"),
        sa.Column("updated_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_table(
        "ai_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("task", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("inference", sa.String(10), nullable=False),
        sa.Column("data_class", sa.String(2), nullable=False),
        sa.Column("deidentified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_redacted", sa.Text(), nullable=True),   # AES-GCM sealed
        sa.Column("output_redacted", sa.Text(), nullable=True),   # AES-GCM sealed
        sa.Column("output_valid", sa.Boolean(), nullable=True),
        sa.Column("tools_called", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_units", sa.Integer(), nullable=True),
        sa.Column("output_units", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(25), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("inference IN ('mock','live')", name="ck_aireq_inference"),
        sa.CheckConstraint("data_class IN ('C0','C1','C2','C3')", name="ck_aireq_class"),
        sa.CheckConstraint(
            "status IN ('ok','suppressed','failed','timeout','rejected_output',"
            "'rejected_by_policy','refused')", name="ck_aireq_status"),
        sa.CheckConstraint("credits >= 0", name="ck_aireq_credits"),
    )
    op.create_index("ix_aireq_org_created", "ai_requests", ["organization_id", "created_at"])
    op.create_table(
        "ai_credit_ledger",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),   # YYYY-MM, clinic calendar
        sa.Column("entry_type", sa.String(10), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("ai_request_id", UUID(as_uuid=True),
                  sa.ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("entry_type IN ('consume','grant','adjust')",
                           name="ck_aicredit_type"),
        sa.CheckConstraint("period ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_aicredit_period"),
    )
    op.create_index("ix_aicredit_org_period", "ai_credit_ledger", ["organization_id", "period"])

    for table in ("ai_tenant_settings", "ai_requests", "ai_credit_ledger"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""CREATE POLICY {table}_tenant ON {table}
            USING (organization_id = {GUC_ORG}) WITH CHECK (organization_id = {GUC_ORG});""")
    op.execute("REVOKE DELETE ON ai_tenant_settings FROM hms_app;")
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_ai_log_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only (blocked %)', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("ai_requests", "ai_credit_ledger"):
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM hms_app;")
        op.execute(f"""CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE
            ON {table} FOR EACH ROW EXECUTE FUNCTION forbid_ai_log_mutation();""")

    op.bulk_insert(sa.table("permissions", sa.column("key", sa.String),
                            sa.column("description", sa.Text)),
                   [{"key": k, "description": d} for k, d in AI_PERMS])
    conn = op.get_bind()
    role_ids = {key: str(rid) for rid, key in
                conn.execute(sa.text("SELECT id, key FROM roles")).fetchall()}
    op.bulk_insert(
        sa.table("role_permissions", sa.column("role_id", sa.String),
                 sa.column("permission_key", sa.String)),
        [{"role_id": role_ids[r], "permission_key": p}
         for r, perms in ROLE_GRANTS.items() for p in perms],
    )


def downgrade() -> None:
    conn = op.get_bind()
    keys = [p for p, _ in AI_PERMS]
    for stmt in ("DELETE FROM role_permissions WHERE permission_key IN :keys",
                 "DELETE FROM permissions WHERE key IN :keys"):
        conn.execute(sa.text(stmt).bindparams(sa.bindparam("keys", expanding=True)),
                     {"keys": keys})
    for table in ("ai_credit_ledger", "ai_requests"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table};")
    op.execute("DROP FUNCTION IF EXISTS forbid_ai_log_mutation();")
    for table in ("ai_credit_ledger", "ai_requests", "ai_tenant_settings"):
        op.drop_table(table)
