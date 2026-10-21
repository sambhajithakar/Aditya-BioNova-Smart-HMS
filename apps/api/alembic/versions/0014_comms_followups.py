"""Communications framework v2 + clinician-directed follow-up CRM.

Revision ID: 0014
Revises: 0013

Tables (all tenant-scoped: ``organization_id`` + strict RLS, as 0005/0012):

* ``comms_tenant_settings`` — per-clinic cost controls and reminder policy:
  monthly spend cap (paise), quiet hours (clinic-local, default 21:00–08:00),
  reminder lead time and channels. Created lazily, together with the default
  EN / मराठी / हिंदी templates.
* ``comms_templates`` — message templates per channel / purpose / language.
  Bodies may only use whitelisted placeholders (validated in
  ``app.comms.templates``); clinical content — diagnoses, medicines, results,
  appointment reasons — is never a placeholder. One ACTIVE template per
  (clinic, channel, purpose, language).
* ``comms_patient_preferences`` — preferred language + optional contact e-mail.
* ``comms_consents`` — current opt-in / opt-out state per patient per channel
  (source, actor, timestamp); ``comms_consent_events`` is its append-only
  history. Opt-out always wins: sending requires an explicit opt-in that has
  not been withdrawn.
* ``comms_delivery_log`` — one row per send ATTEMPT (sent_mock, suppressed,
  failed, skipped_*), with masked recipient, provider, cost estimate and the
  appointment / follow-up it belongs to. Append-only (REVOKE + trigger, as
  for the AI logs in 0012). A partial unique index on ``dedupe_key`` for
  delivered statuses makes reminders idempotent even under concurrency.
* ``follow_ups`` — clinician-directed recall worklist (planned → reminded →
  booked → completed / missed / cancelled) with an optional linked
  appointment. ``reason`` is a short NON-clinical label.

Permissions (seeded like 0011/0012): comms.read, comms.manage, comms.send,
comms.consent, followup.read, followup.create (clinicians), followup.write.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"

COMMS_PERMS = [
    ("comms.read", "View message templates, delivery log, consent statistics and quotas"),
    ("comms.manage", "Edit message templates and communication cost / reminder settings"),
    ("comms.send", "Run appointment reminders and send follow-up / missed-visit messages"),
    ("comms.consent", "Record a patient's communication opt-in / opt-out and language"),
    ("followup.read", "View the follow-up worklist and missed appointments"),
    ("followup.create", "Plan a follow-up visit for a patient (clinician)"),
    ("followup.write", "Update follow-ups: booked, completed, missed, cancelled"),
]
ROLE_GRANTS = {
    "owner": [p for p, _ in COMMS_PERMS],
    "admin": [p for p, _ in COMMS_PERMS],
    "doctor": ["comms.consent", "comms.send", "followup.read", "followup.create",
               "followup.write"],
    "receptionist": ["comms.read", "comms.send", "comms.consent", "followup.read",
                     "followup.write"],
    "nurse": ["followup.read"],
    # delivery log holds masked recipients only — fit for the auditor
    "auditor": ["comms.read"],
    # billing / pharmacist / lab / support: no patient-communication access
}

CHANNELS = "('email','sms','whatsapp')"
PURPOSES = "('appointment_reminder','follow_up','missed_appointment','generic')"
LANGS = "('en','mr','hi')"
DELIVERY_STATUSES = (
    "('queued','sent','sent_mock','suppressed','failed','skipped_no_consent',"
    "'skipped_quota','skipped_quiet_hours','skipped_no_recipient','skipped_no_template')"
)
FOLLOWUP_STATUSES = "('planned','reminded','booked','completed','missed','cancelled')"


def _ts(name: str, **kw) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def _org() -> sa.Column:
    return sa.Column("organization_id", UUID(as_uuid=True),
                     sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)


def _id() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID(as_uuid=True),
                     sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "comms_tenant_settings",
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("monthly_spend_cap_paise", sa.BigInteger(), nullable=True),
        sa.Column("quiet_start_hour", sa.SmallInteger(), nullable=False, server_default="21"),
        sa.Column("quiet_end_hour", sa.SmallInteger(), nullable=False, server_default="8"),
        sa.Column("reminder_hours_ahead", sa.SmallInteger(), nullable=False,
                  server_default="24"),
        sa.Column("reminder_channels", ARRAY(sa.String(20)), nullable=False,
                  server_default="{sms}"),
        _user("updated_by"),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("monthly_spend_cap_paise IS NULL OR monthly_spend_cap_paise >= 0",
                           name="ck_commsset_cap"),
        sa.CheckConstraint("quiet_start_hour BETWEEN 0 AND 23 AND quiet_end_hour BETWEEN 0 AND 23",
                           name="ck_commsset_quiet"),
        sa.CheckConstraint("reminder_hours_ahead BETWEEN 1 AND 168", name="ck_commsset_ahead"),
        sa.CheckConstraint(
            "reminder_channels <@ ARRAY['email','sms','whatsapp']::varchar[]",
            name="ck_commsset_channels"),
    )

    op.create_table(
        "comms_templates",
        _id(), _org(),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False, server_default=""),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("dlt_template_id", sa.String(40), nullable=True),
        sa.Column("whatsapp_template_name", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _user("created_by"), _user("updated_by"),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"channel IN {CHANNELS}", name="ck_commstpl_channel"),
        sa.CheckConstraint(f"purpose IN {PURPOSES}", name="ck_commstpl_purpose"),
        sa.CheckConstraint(f"language IN {LANGS}", name="ck_commstpl_language"),
        sa.CheckConstraint("dlt_template_id IS NULL OR dlt_template_id ~ '^[0-9]{10,30}$'",
                           name="ck_commstpl_dlt"),
        sa.CheckConstraint(
            "whatsapp_template_name IS NULL OR whatsapp_template_name ~ '^[a-z0-9_]{1,120}$'",
            name="ck_commstpl_wa"),
    )
    op.create_index("ix_commstpl_org", "comms_templates", ["organization_id", "channel"])
    op.create_index("uq_commstpl_active", "comms_templates",
                    ["organization_id", "channel", "purpose", "language"], unique=True,
                    postgresql_where=sa.text("is_active"))

    op.create_table(
        "comms_patient_preferences",
        _org(),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("preferred_language", sa.String(2), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        _user("updated_by"),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("organization_id", "patient_id", name="pk_comms_prefs"),
        sa.CheckConstraint(f"preferred_language IS NULL OR preferred_language IN {LANGS}",
                           name="ck_commspref_language"),
    )

    op.create_table(
        "comms_consents",
        _org(),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        _user("actor_user_id"),
        _ts("recorded_at", nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("organization_id", "patient_id", "channel",
                                name="pk_comms_consents"),
        sa.CheckConstraint(f"channel IN {CHANNELS}", name="ck_commsconsent_channel"),
        sa.CheckConstraint("status IN ('opted_in','opted_out')", name="ck_commsconsent_status"),
    )
    op.create_table(
        "comms_consent_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        _org(),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        _user("actor_user_id"),
        _ts("recorded_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"channel IN {CHANNELS}", name="ck_commsconsentev_channel"),
        sa.CheckConstraint("status IN ('opted_in','opted_out')",
                           name="ck_commsconsentev_status"),
    )
    op.create_index("ix_commsconsentev_patient", "comms_consent_events",
                    ["organization_id", "patient_id", "id"])

    op.create_table(
        "follow_ups",
        _id(), _org(),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="planned"),
        _user("assigned_user_id"),
        _user("created_by"),
        sa.Column("appointment_id", UUID(as_uuid=True),
                  sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status_note", sa.String(200), nullable=False, server_default=""),
        _ts("reminded_at", nullable=True),
        _ts("closed_at", nullable=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"status IN {FOLLOWUP_STATUSES}", name="ck_followup_status"),
        sa.CheckConstraint("status <> 'booked' OR appointment_id IS NOT NULL",
                           name="ck_followup_booked_has_appt"),
    )
    op.create_index("ix_followup_org_due", "follow_ups", ["organization_id", "status", "due_date"])
    op.create_index("ix_followup_org_patient", "follow_ups", ["organization_id", "patient_id"])

    op.create_table(
        "comms_delivery_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        _org(),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("language", sa.String(2), nullable=True),
        sa.Column("template_id", UUID(as_uuid=True),
                  sa.ForeignKey("comms_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("appointment_id", UUID(as_uuid=True),
                  sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("follow_up_id", UUID(as_uuid=True),
                  sa.ForeignKey("follow_ups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_masked", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("status", sa.String(25), nullable=False),
        sa.Column("cost_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=True),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("error", sa.String(300), nullable=True),
        _user("actor_user_id"),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"channel IN {CHANNELS}", name="ck_commslog_channel"),
        sa.CheckConstraint(f"purpose IN {PURPOSES}", name="ck_commslog_purpose"),
        sa.CheckConstraint(f"status IN {DELIVERY_STATUSES}", name="ck_commslog_status"),
        sa.CheckConstraint("cost_paise >= 0", name="ck_commslog_cost"),
        sa.CheckConstraint("period ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_commslog_period"),
        sa.CheckConstraint("trigger IN ('manual','reminder_run','scheduler')",
                           name="ck_commslog_trigger"),
    )
    op.create_index("ix_commslog_org_created", "comms_delivery_log",
                    ["organization_id", "created_at"])
    op.create_index("ix_commslog_org_period", "comms_delivery_log",
                    ["organization_id", "period", "channel"])
    # idempotency backstop: one delivered message per dedupe key
    op.create_index("uq_commslog_dedupe", "comms_delivery_log",
                    ["organization_id", "dedupe_key"], unique=True,
                    postgresql_where=sa.text(
                        "dedupe_key IS NOT NULL AND status IN "
                        "('queued','sent','sent_mock','suppressed')"))

    # ---------------------------------------------------- row-level security
    for table in ("comms_tenant_settings", "comms_templates", "comms_patient_preferences",
                  "comms_consents", "comms_consent_events", "comms_delivery_log",
                  "follow_ups"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""CREATE POLICY {table}_tenant ON {table}
            USING (organization_id = {GUC_ORG}) WITH CHECK (organization_id = {GUC_ORG});""")
    for table in ("comms_tenant_settings", "comms_templates", "comms_consents", "follow_ups"):
        # templates are deactivated, consents flipped, follow-ups cancelled — never deleted
        op.execute(f"REVOKE DELETE ON {table} FROM hms_app;")
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_comms_log_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only (blocked %)', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("comms_delivery_log", "comms_consent_events"):
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM hms_app;")
        op.execute(f"""CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE
            ON {table} FOR EACH ROW EXECUTE FUNCTION forbid_comms_log_mutation();""")
    # explicit grants (default privileges from 0001 also cover these)
    op.execute("""GRANT SELECT, INSERT, UPDATE ON comms_tenant_settings, comms_templates,
        comms_patient_preferences, comms_consents, follow_ups TO hms_app;""")
    op.execute("GRANT SELECT, INSERT ON comms_delivery_log, comms_consent_events TO hms_app;")

    # ---------------------------------------------------- RBAC seed
    op.bulk_insert(sa.table("permissions", sa.column("key", sa.String),
                            sa.column("description", sa.Text)),
                   [{"key": k, "description": d} for k, d in COMMS_PERMS])
    conn = op.get_bind()
    role_ids = {key: str(rid) for rid, key in
                conn.execute(sa.text("SELECT id, key FROM roles")).fetchall()}
    op.bulk_insert(
        sa.table("role_permissions", sa.column("role_id", sa.String),
                 sa.column("permission_key", sa.String)),
        [{"role_id": role_ids[r], "permission_key": p}
         for r, perms in ROLE_GRANTS.items() for p in perms if r in role_ids],
    )


def downgrade() -> None:
    conn = op.get_bind()
    keys = [p for p, _ in COMMS_PERMS]
    for stmt in ("DELETE FROM role_permissions WHERE permission_key IN :keys",
                 "DELETE FROM permissions WHERE key IN :keys"):
        conn.execute(sa.text(stmt).bindparams(sa.bindparam("keys", expanding=True)),
                     {"keys": keys})
    for table in ("comms_delivery_log", "comms_consent_events"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table};")
    op.execute("DROP FUNCTION IF EXISTS forbid_comms_log_mutation();")
    for table in ("comms_delivery_log", "follow_ups", "comms_consent_events", "comms_consents",
                  "comms_patient_preferences", "comms_templates", "comms_tenant_settings"):
        op.drop_table(table)
