"""Smart Setup Wizard, Smart Patient QR Check-In and Smart Printer Setup.

Revision ID: 0015
Revises: 0012

* ``org_settings`` — one row per clinic: a versioned JSONB settings document
  (prescription template, clinic billing defaults, appointment schedule)
  validated by ``app.schemas_setup.OrgSettings`` before every write, plus the
  setup-wizard progress (``wizard`` JSONB). Clinic (patient) billing settings
  only — SaaS subscription billing stays in ``subscriptions``.
* ``branch_working_hours`` — weekday sessions per branch with an optional
  lunch break. Range sanity is enforced by CHECK constraints; overlaps between
  sessions of one day are rejected by the API (replace-the-week writes run
  under a per-branch advisory lock).
* ``fee_schedule`` — consultation fee master: one clinic default row
  (``provider_user_id IS NULL``) and optional per-doctor rows.
* ``checkin_tokens`` — privacy-preserving QR check-in. The QR carries ONLY a
  random 128-bit token; only its SHA-256 is stored (as invitation tokens,
  0009). Bound to one appointment, expires at the end of the appointment's
  clinic day, single use. At most one live token per appointment.
* ``printer_profiles`` — paper kind, margins, font scale and which documents
  a profile is the default for.

All five tables are tenant-scoped with strict RLS on
``app.current_org_id``; none is opened to the platform-admin flag.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0015"
down_revision = "0012"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"

SETUP_PERMS = [
    ("setup.read", "View clinic setup: working hours, fees, templates, printers"),
    ("setup.manage", "Run the setup wizard and change clinic setup and printers"),
    ("checkin.manage", "Issue patient check-in QR codes and check patients in"),
]
ROLE_GRANTS = {
    "owner": ["setup.read", "setup.manage", "checkin.manage"],
    "admin": ["setup.read", "setup.manage", "checkin.manage"],
    "receptionist": ["setup.read", "checkin.manage"],
    "doctor": ["setup.read"],
    "nurse": ["setup.read"],
    "billing": ["setup.read"],
    "pharmacist": ["setup.read"],
    "lab_technician": ["setup.read"],
}

TABLES = ("org_settings", "branch_working_hours", "fee_schedule", "checkin_tokens",
          "printer_profiles")


def _ts(name: str, **kw) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def _org_fk() -> sa.Column:
    return sa.Column("organization_id", UUID(as_uuid=True),
                     sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)


def _id() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True)


def upgrade() -> None:
    op.create_table(
        "org_settings",
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("settings", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("wizard", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _user_fk("updated_by"),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("schema_version >= 1", name="ck_orgsettings_version"),
        sa.CheckConstraint("jsonb_typeof(settings) = 'object' AND jsonb_typeof(wizard) = 'object'",
                           name="ck_orgsettings_objects"),
    )

    op.create_table(
        "branch_working_hours",
        _id(),
        _org_fk(),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),   # 0 = Monday
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.Column("break_starts_at", sa.Time(), nullable=True),
        sa.Column("break_ends_at", sa.Time(), nullable=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_bwh_weekday"),
        sa.CheckConstraint("opens_at < closes_at", name="ck_bwh_range"),
        sa.CheckConstraint(
            "(break_starts_at IS NULL AND break_ends_at IS NULL) OR "
            "(break_starts_at IS NOT NULL AND break_ends_at IS NOT NULL AND "
            " opens_at < break_starts_at AND break_starts_at < break_ends_at AND "
            " break_ends_at < closes_at)",
            name="ck_bwh_break"),
        sa.UniqueConstraint("organization_id", "branch_id", "weekday", "opens_at",
                            name="uq_bwh_session"),
    )
    op.create_index("ix_bwh_org_branch", "branch_working_hours",
                    ["organization_id", "branch_id", "weekday"])

    op.create_table(
        "fee_schedule",
        _id(),
        _org_fk(),
        sa.Column("provider_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("consultation_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("follow_up_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("follow_up_valid_days", sa.Integer(), nullable=True),
        _user_fk("updated_by"),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("consultation_fee >= 0 AND consultation_fee <= 1000000",
                           name="ck_fee_consultation"),
        sa.CheckConstraint("follow_up_fee IS NULL OR (follow_up_fee >= 0 "
                           "AND follow_up_fee <= 1000000)", name="ck_fee_follow_up"),
        sa.CheckConstraint("follow_up_valid_days IS NULL OR follow_up_valid_days "
                           "BETWEEN 0 AND 365", name="ck_fee_follow_up_days"),
    )
    # one default row and at most one row per doctor
    op.execute("""
        CREATE UNIQUE INDEX uq_fee_org_provider ON fee_schedule (organization_id,
            coalesce(provider_user_id, '00000000-0000-0000-0000-000000000000'::uuid));
    """)

    op.create_table(
        "checkin_tokens",
        _id(),
        _org_fk(),
        sa.Column("appointment_id", UUID(as_uuid=True),
                  sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        _ts("expires_at", nullable=False),
        _ts("used_at", nullable=True),
        _user_fk("used_by"),
        sa.Column("queue_entry_id", UUID(as_uuid=True),
                  sa.ForeignKey("opd_queue.id", ondelete="SET NULL"), nullable=True),
        _ts("revoked_at", nullable=True),
        _user_fk("created_by"),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_checkin_hash"),
        sa.CheckConstraint("used_at IS NULL OR revoked_at IS NULL", name="ck_checkin_state"),
    )
    op.create_index("ix_checkin_org_appt", "checkin_tokens", ["organization_id", "appointment_id"])
    op.execute("""
        CREATE UNIQUE INDEX uq_checkin_live_per_appt ON checkin_tokens (appointment_id)
        WHERE used_at IS NULL AND revoked_at IS NULL;
    """)
    # an appointment is checked in through at most one token
    op.execute("""
        CREATE UNIQUE INDEX uq_checkin_used_per_appt ON checkin_tokens (appointment_id)
        WHERE used_at IS NOT NULL;
    """)

    op.create_table(
        "printer_profiles",
        _id(),
        _org_fk(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("default_for", ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("margin_top_mm", sa.Numeric(4, 1), nullable=False, server_default="10"),
        sa.Column("margin_right_mm", sa.Numeric(4, 1), nullable=False, server_default="10"),
        sa.Column("margin_bottom_mm", sa.Numeric(4, 1), nullable=False, server_default="10"),
        sa.Column("margin_left_mm", sa.Numeric(4, 1), nullable=False, server_default="10"),
        sa.Column("font_scale", sa.Numeric(3, 2), nullable=False, server_default="1.00"),
        sa.Column("notes", sa.String(300), nullable=False, server_default=""),
        _user_fk("created_by"),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('a4','a5','thermal_80mm','thermal_58mm')",
                           name="ck_printer_kind"),
        sa.CheckConstraint(
            "default_for <@ ARRAY['prescription','receipt','lab_report']::varchar[]",
            name="ck_printer_default_for"),
        sa.CheckConstraint(
            "margin_top_mm BETWEEN 0 AND 50 AND margin_right_mm BETWEEN 0 AND 50 AND "
            "margin_bottom_mm BETWEEN 0 AND 50 AND margin_left_mm BETWEEN 0 AND 50",
            name="ck_printer_margins"),
        sa.CheckConstraint("font_scale BETWEEN 0.5 AND 2.0", name="ck_printer_font_scale"),
    )
    op.execute("CREATE UNIQUE INDEX uq_printer_org_name ON printer_profiles "
               "(organization_id, lower(name));")

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""CREATE POLICY {table}_tenant ON {table}
            USING (organization_id = {GUC_ORG}) WITH CHECK (organization_id = {GUC_ORG});""")
    # settings rows and check-in tokens are never deleted by the app (tokens
    # are revoked or used — the history backs the audit trail)
    op.execute("REVOKE DELETE ON org_settings, checkin_tokens FROM hms_app;")

    op.bulk_insert(sa.table("permissions", sa.column("key", sa.String),
                            sa.column("description", sa.Text)),
                   [{"key": k, "description": d} for k, d in SETUP_PERMS])
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
    keys = [p for p, _ in SETUP_PERMS]
    for stmt in ("DELETE FROM role_permissions WHERE permission_key IN :keys",
                 "DELETE FROM permissions WHERE key IN :keys"):
        conn.execute(sa.text(stmt).bindparams(sa.bindparam("keys", expanding=True)),
                     {"keys": keys})
    for table in reversed(TABLES):
        op.drop_table(table)
