"""AI-1: forecasting model runs, knowledge base (RAG), agent proposals with
human approval, Clinical Scribe draft workflow.

Revision ID: 0016
Revises: 0012   (the integrator re-chains this onto the current head)

See docs/AI_ARCHITECTURE.md §3, §5–§7. Every table is tenant-scoped with the
strict ``organization_id = GUC`` RLS policy used since 0001.

Append-only (no UPDATE/DELETE for hms_app + trigger, as for ai_requests):
``ai_model_runs``, ``ai_proposal_events``, ``scribe_consents``.

State-machine guarded (trigger): ``ai_proposals`` — kind/payload/args hash
are immutable, status moves only proposed→approved|rejected|expired and
approved→executed|failed; ``scribe_sessions`` — frozen once accepted or
discarded; ``kb_documents`` — content immutable (a change is a new version).
No DELETE grant on any of these tables.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0016"
down_revision = "0012"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"

AI1_PERMS = [
    ("ai.forecast.read", "View statistical forecasts (OPD demand, no-show risk, pharmacy "
                         "demand, bed occupancy)"),
    ("ai.knowledge.use", "Ask the knowledge assistant about approved clinic documents"),
    ("ai.knowledge.manage", "Upload, approve and archive knowledge-base documents"),
    ("ai.agents.use", "Run AI operations agents and view their proposals"),
    ("ai.agents.approve", "Approve or reject AI agent proposals"),
    ("ai.scribe.use", "Use the Clinical Scribe to draft consultation notes"),
]
ROLE_GRANTS = {
    "owner": [p for p, _ in AI1_PERMS],
    "admin": ["ai.forecast.read", "ai.knowledge.use", "ai.knowledge.manage", "ai.agents.use",
              "ai.agents.approve"],
    "doctor": ["ai.forecast.read", "ai.knowledge.use", "ai.scribe.use"],
    "nurse": ["ai.forecast.read", "ai.knowledge.use"],
    "receptionist": ["ai.forecast.read", "ai.knowledge.use"],
    "pharmacist": ["ai.forecast.read", "ai.knowledge.use"],
    "lab_technician": ["ai.knowledge.use"],
    "billing": ["ai.knowledge.use"],
}

TABLES = ("ai_model_runs", "kb_documents", "kb_chunks", "ai_proposals", "ai_proposal_events",
          "ai_staff_tasks", "ai_reorder_drafts", "scribe_consents", "scribe_sessions")


def _org() -> sa.Column:
    return sa.Column("organization_id", UUID(as_uuid=True),
                     sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)


def _uuid_pk() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _user(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=nullable)


def _ts(name: str = "created_at", nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable,
                     server_default=sa.func.now() if not nullable else None)


def upgrade() -> None:
    # --- model registry -----------------------------------------------------------------
    op.create_table(
        "ai_model_runs", _uuid_pk(), _org(),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("scope", sa.String(80), nullable=False, server_default="all"),
        sa.Column("engine_version", sa.String(40), nullable=False),
        sa.Column("method", sa.String(40), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("params", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("baseline_metrics", JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_start", sa.Date(), nullable=True),
        sa.Column("data_end", sa.Date(), nullable=True),
        sa.Column("n_obs", sa.Integer(), nullable=False, server_default="0"),
        _user("trained_by"), _ts("trained_at"),
        sa.CheckConstraint("kind IN ('opd_demand','no_show','pharmacy_demand',"
                           "'bed_occupancy')", name="ck_modelrun_kind"),
        sa.CheckConstraint("status IN ('ok','insufficient_data')", name="ck_modelrun_status"),
    )
    op.create_index("ix_modelrun_org_kind", "ai_model_runs",
                    ["organization_id", "kind", "trained_at"])

    # --- knowledge base -----------------------------------------------------------------
    op.create_table(
        "kb_documents", _uuid_pk(), _org(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("visibility_roles", ARRAY(sa.String(40)), nullable=False,
                  server_default="{}"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("injection_flags", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        _user("uploaded_by"), _ts(), _user("approved_by"), _ts("approved_at", nullable=True),
        _ts("updated_at"),
        sa.UniqueConstraint("organization_id", "title", "version", name="uq_kbdoc_title_ver"),
        sa.CheckConstraint("doc_type IN ('sop','manual','policy','training','other')",
                           name="ck_kbdoc_type"),
        sa.CheckConstraint("language IN ('en','mr','hi','mixed')", name="ck_kbdoc_lang"),
        sa.CheckConstraint("status IN ('draft','approved','superseded','archived')",
                           name="ck_kbdoc_status"),
        sa.CheckConstraint("length(body) <= 200000", name="ck_kbdoc_size"),
    )
    op.create_index("ix_kbdoc_org_status", "kb_documents", ["organization_id", "status"])
    op.create_table(
        "kb_chunks", _uuid_pk(), _org(),
        sa.Column("document_id", UUID(as_uuid=True),
                  sa.ForeignKey("kb_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(300), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tokens", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        _ts(),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_kbchunk_doc_ord"),
    )
    op.create_index("ix_kbchunk_org_doc", "kb_chunks", ["organization_id", "document_id"])

    # --- agents -------------------------------------------------------------------------
    op.create_table(
        "ai_proposals", _uuid_pk(), _org(),
        sa.Column("agent", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("args_sha256", sa.String(64), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        _user("created_by"), _ts(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _user("decided_by"), _ts("decided_at", nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=False, server_default=""),
        _ts("executed_at", nullable=True),
        sa.Column("result", JSONB(), nullable=True),
        sa.CheckConstraint("status IN ('proposed','approved','rejected','expired','executed',"
                           "'failed')", name="ck_proposal_status"),
        sa.CheckConstraint("kind IN ('followup_tasks','inventory_reorder',"
                           "'billing_reconciliation','ops_daily_report')",
                           name="ck_proposal_kind"),
    )
    op.create_index("ix_proposal_org_status", "ai_proposals",
                    ["organization_id", "status", "created_at"])
    op.create_index("uq_proposal_open_dedupe", "ai_proposals",
                    ["organization_id", "dedupe_key"], unique=True,
                    postgresql_where=sa.text("status = 'proposed'"))
    op.create_table(
        "ai_proposal_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), _org(),
        sa.Column("proposal_id", UUID(as_uuid=True),
                  sa.ForeignKey("ai_proposals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        _user("actor_user_id"),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        _ts(),
    )
    op.create_index("ix_propevent_org_prop", "ai_proposal_events",
                    ["organization_id", "proposal_id"])
    op.create_table(
        "ai_staff_tasks", _uuid_pk(), _org(),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("proposal_id", UUID(as_uuid=True),
                  sa.ForeignKey("ai_proposals.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("subject_type", sa.String(30), nullable=True),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        _user("created_by"), _ts(), _user("completed_by"), _ts("completed_at", nullable=True),
        sa.CheckConstraint("kind IN ('reminder_call')", name="ck_stafftask_kind"),
        sa.CheckConstraint("priority IN ('high','normal')", name="ck_stafftask_priority"),
        sa.CheckConstraint("status IN ('open','done','cancelled')", name="ck_stafftask_status"),
    )
    op.create_index("ix_stafftask_org_status", "ai_staff_tasks",
                    ["organization_id", "status", "due_date"])
    op.create_table(
        "ai_reorder_drafts", _uuid_pk(), _org(),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("proposal_id", UUID(as_uuid=True),
                  sa.ForeignKey("ai_proposals.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("lines", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        _user("created_by"), _ts(),
        sa.CheckConstraint("status IN ('draft','ordered','cancelled')",
                           name="ck_reorder_status"),
    )

    # --- scribe -------------------------------------------------------------------------
    op.create_table(
        "scribe_consents", _uuid_pk(), _org(),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("encounter_id", UUID(as_uuid=True),
                  sa.ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False),
        _user("obtained_by", nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("notice_language", sa.String(5), nullable=False),
        sa.Column("notice_version", sa.String(20), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("method IN ('verbal')", name="ck_scribeconsent_method"),
        sa.CheckConstraint("notice_language IN ('en','mr','hi')",
                           name="ck_scribeconsent_lang"),
    )
    op.create_table(
        "scribe_sessions", _uuid_pk(), _org(),
        sa.Column("encounter_id", UUID(as_uuid=True),
                  sa.ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        _user("clinician_id", nullable=False),
        sa.Column("consent_id", UUID(as_uuid=True),
                  sa.ForeignKey("scribe_consents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="consented"),
        sa.Column("transcriber", sa.String(40), nullable=False, server_default=""),
        sa.Column("transcript_sealed", sa.Text(), nullable=True),   # AES-GCM (C3)
        sa.Column("segment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("draft_sealed", sa.Text(), nullable=True),        # AES-GCM (C3)
        sa.Column("draft_valid", sa.Boolean(), nullable=True),
        sa.Column("ai_request_id", UUID(as_uuid=True),
                  sa.ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("audio_stored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _user("accepted_by"), _ts("accepted_at", nullable=True),
        sa.Column("accepted_fields", ARRAY(sa.String(30)), nullable=False, server_default="{}"),
        sa.Column("edit_ratio", sa.Numeric(5, 4), nullable=True),
        _ts(), _ts("updated_at"),
        sa.CheckConstraint("status IN ('consented','drafted','accepted','discarded')",
                           name="ck_scribesession_status"),
        # this phase stores no audio at all (docs/AI_ARCHITECTURE.md §3, D4)
        sa.CheckConstraint("audio_stored = false", name="ck_scribesession_no_audio"),
    )
    op.create_index("ix_scribesession_org_enc", "scribe_sessions",
                    ["organization_id", "encounter_id"])

    # --- RLS, grants, guards --------------------------------------------------------------
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""CREATE POLICY {table}_tenant ON {table}
            USING (organization_id = {GUC_ORG}) WITH CHECK (organization_id = {GUC_ORG});""")
        op.execute(f"REVOKE DELETE ON {table} FROM hms_app;")
    for table in ("ai_model_runs", "ai_proposal_events", "scribe_consents", "kb_chunks"):
        op.execute(f"REVOKE UPDATE ON {table} FROM hms_app;")
        op.execute(f"""CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE
            ON {table} FOR EACH ROW EXECUTE FUNCTION forbid_ai_log_mutation();""")

    op.execute("""
        CREATE OR REPLACE FUNCTION guard_ai_proposal() RETURNS trigger AS $$
        BEGIN
            IF NEW.organization_id <> OLD.organization_id OR NEW.kind <> OLD.kind
               OR NEW.agent <> OLD.agent OR NEW.payload <> OLD.payload
               OR NEW.args_sha256 <> OLD.args_sha256 OR NEW.created_at <> OLD.created_at
               OR NEW.expires_at <> OLD.expires_at THEN
                RAISE EXCEPTION 'AI proposal content is immutable';
            END IF;
            IF NEW.status <> OLD.status AND NOT (
                (OLD.status = 'proposed' AND NEW.status IN ('approved','rejected','expired'))
                OR (OLD.status = 'approved' AND NEW.status IN ('executed','failed'))) THEN
                RAISE EXCEPTION 'AI proposal cannot move from % to %', OLD.status, NEW.status;
            END IF;
            IF NEW.status = OLD.status AND OLD.status <> 'proposed' THEN
                RAISE EXCEPTION 'AI proposal is closed (%)', OLD.status;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""CREATE TRIGGER trg_ai_proposals_guard BEFORE UPDATE ON ai_proposals
        FOR EACH ROW EXECUTE FUNCTION guard_ai_proposal();""")

    op.execute("""
        CREATE OR REPLACE FUNCTION guard_scribe_session() RETURNS trigger AS $$
        BEGIN
            IF OLD.status IN ('accepted','discarded') THEN
                RAISE EXCEPTION 'Scribe session is closed (%)', OLD.status;
            END IF;
            IF NEW.encounter_id <> OLD.encounter_id OR NEW.patient_id <> OLD.patient_id
               OR NEW.consent_id <> OLD.consent_id OR NEW.organization_id <> OLD.organization_id
               THEN
                RAISE EXCEPTION 'Scribe session subject is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""CREATE TRIGGER trg_scribe_sessions_guard BEFORE UPDATE ON scribe_sessions
        FOR EACH ROW EXECUTE FUNCTION guard_scribe_session();""")

    op.execute("""
        CREATE OR REPLACE FUNCTION guard_kb_document() RETURNS trigger AS $$
        BEGIN
            IF NEW.body <> OLD.body OR NEW.title <> OLD.title OR NEW.version <> OLD.version
               OR NEW.sha256 <> OLD.sha256 OR NEW.organization_id <> OLD.organization_id THEN
                RAISE EXCEPTION 'Document content is immutable; upload a new version';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""CREATE TRIGGER trg_kb_documents_guard BEFORE UPDATE ON kb_documents
        FOR EACH ROW EXECUTE FUNCTION guard_kb_document();""")

    # --- permissions ----------------------------------------------------------------------
    op.bulk_insert(sa.table("permissions", sa.column("key", sa.String),
                            sa.column("description", sa.Text)),
                   [{"key": k, "description": d} for k, d in AI1_PERMS])
    conn = op.get_bind()
    role_ids = {key: str(rid) for rid, key in
                conn.execute(sa.text("SELECT id, key FROM roles")).fetchall()}
    op.bulk_insert(
        sa.table("role_permissions", sa.column("role_id", sa.String),
                 sa.column("permission_key", sa.String)),
        [{"role_id": role_ids[r], "permission_key": p}
         for r, perms in ROLE_GRANTS.items() if r in role_ids for p in perms],
    )


def downgrade() -> None:
    conn = op.get_bind()
    keys = [p for p, _ in AI1_PERMS]
    for stmt in ("DELETE FROM role_permissions WHERE permission_key IN :keys",
                 "DELETE FROM permissions WHERE key IN :keys"):
        conn.execute(sa.text(stmt).bindparams(sa.bindparam("keys", expanding=True)),
                     {"keys": keys})
    op.execute("DROP TRIGGER IF EXISTS trg_kb_documents_guard ON kb_documents;")
    op.execute("DROP TRIGGER IF EXISTS trg_scribe_sessions_guard ON scribe_sessions;")
    op.execute("DROP TRIGGER IF EXISTS trg_ai_proposals_guard ON ai_proposals;")
    for table in ("ai_model_runs", "ai_proposal_events", "scribe_consents", "kb_chunks"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table};")
    for fn in ("guard_kb_document", "guard_scribe_session", "guard_ai_proposal"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}();")
    for table in reversed(TABLES):
        op.drop_table(table)
