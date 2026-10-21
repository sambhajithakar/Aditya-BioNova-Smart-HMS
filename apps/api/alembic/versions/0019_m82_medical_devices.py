"""M8.2: medical device register, device readings with provenance, clinician
review decisions.

* ``medical_devices`` — the tenant's allow-list. Only an administrator
  (``device.manage``) registers a device. Its Bluetooth address is stored only
  as a per-tenant SHA-256, never in clear. Identity fields are immutable; the
  only change allowed is active → retired. No DELETE.
* ``device_readings`` — APPEND-ONLY. The raw characteristic payload (hex), its
  SHA-256, the server's own parse, the source (``ble`` | ``simulator``), the
  device time and the time of capture, a clock-skew flag, who captured it and
  the app version. ``capture_id`` (made on the phone) makes a sync replay
  idempotent.
* ``device_reading_decisions`` — APPEND-ONLY, at most one per reading. An
  acceptance points at the ``encounter_vitals`` row it created; a rejection
  needs a reason. Nothing is ever accepted automatically: a reading without
  a decision is "pending review".
* ``encounter_vitals.device_reading_id`` — provenance from a vitals row back
  to the reading it came from (NULL for manual entry).

RLS: the strict ``organization_id = GUC`` policy used since 0001.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"

DEVICE_PERMS = [
    ("device.read", "View the clinic's registered medical devices"),
    ("device.manage", "Register and retire medical devices"),
    ("device.capture", "Capture readings from a registered medical device"),
    ("device.review", "Accept or reject device readings into the clinical record"),
]
ROLE_GRANTS = {
    "owner": ["device.read", "device.manage", "device.capture", "device.review"],
    "admin": ["device.read", "device.manage"],
    "doctor": ["device.read", "device.capture", "device.review"],
    "nurse": ["device.read", "device.capture", "device.review"],
}
FEATURE = "medical_devices"
TABLES = ("medical_devices", "device_readings", "device_reading_decisions")


def _uuid_pk() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _org() -> sa.Column:
    return sa.Column("organization_id", UUID(as_uuid=True),
                     sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True)


def _ts(name: str, **kw) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def upgrade() -> None:
    op.create_table(
        "medical_devices",
        _uuid_pk(), _org(),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("manufacturer", sa.String(80), nullable=False, server_default=""),
        sa.Column("model", sa.String(80), nullable=False, server_default=""),
        sa.Column("serial", sa.String(80), nullable=False, server_default=""),
        sa.Column("firmware", sa.String(40), nullable=False, server_default=""),
        sa.Column("address_hash", sa.String(64), nullable=False),
        sa.Column("is_simulator", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        _user("registered_by"),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _user("retired_by"),
        _ts("retired_at", nullable=True),
        sa.CheckConstraint("kind IN ('bp_monitor','pulse_oximeter')", name="ck_meddev_kind"),
        sa.CheckConstraint("status IN ('active','retired')", name="ck_meddev_status"),
        sa.CheckConstraint("(status = 'retired') = (retired_at IS NOT NULL)",
                           name="ck_meddev_retired"),
    )
    op.create_index("uq_meddev_active_address", "medical_devices",
                    ["organization_id", "address_hash"], unique=True,
                    postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_meddev_org", "medical_devices", ["organization_id", "status"])

    op.create_table(
        "device_readings",
        _uuid_pk(), _org(),
        sa.Column("device_id", UUID(as_uuid=True),
                  sa.ForeignKey("medical_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encounter_id", UUID(as_uuid=True),
                  sa.ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capture_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("characteristic", sa.String(4), nullable=False),
        sa.Column("raw_hex", sa.String(128), nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("parsed", JSONB(), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        _ts("device_time", nullable=True),
        _ts("captured_at", nullable=False),
        _ts("received_at", nullable=False, server_default=sa.func.now()),
        sa.Column("clock_skew", sa.Boolean(), nullable=False),
        _user("captured_by"),
        sa.Column("app_version", sa.String(40), nullable=False, server_default=""),
        sa.CheckConstraint("kind IN ('blood_pressure','spo2')", name="ck_devread_kind"),
        sa.CheckConstraint("characteristic IN ('2a35','2a5e','2a5f')", name="ck_devread_char"),
        sa.CheckConstraint("source IN ('ble','simulator')", name="ck_devread_source"),
        sa.CheckConstraint("raw_sha256 ~ '^[0-9a-f]{64}$'", name="ck_devread_sha"),
        sa.UniqueConstraint("organization_id", "capture_id", name="uq_devread_capture"),
    )
    op.create_index("ix_devread_encounter", "device_readings",
                    ["organization_id", "encounter_id", "received_at"])

    op.create_table(
        "device_reading_decisions",
        _uuid_pk(), _org(),
        sa.Column("reading_id", UUID(as_uuid=True),
                  sa.ForeignKey("device_readings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False, server_default=""),
        sa.Column("surface", sa.String(10), nullable=False),
        sa.Column("vitals_id", UUID(as_uuid=True),
                  sa.ForeignKey("encounter_vitals.id", ondelete="SET NULL"), nullable=True),
        _user("decided_by"),
        _ts("decided_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('accepted','rejected')", name="ck_devdec_decision"),
        sa.CheckConstraint("surface IN ('web','android')", name="ck_devdec_surface"),
        sa.CheckConstraint("decision = 'accepted' OR length(btrim(reason)) >= 3",
                           name="ck_devdec_reason"),
        sa.UniqueConstraint("reading_id", name="uq_devdec_reading"),
    )

    op.add_column("encounter_vitals", sa.Column(
        "device_reading_id", UUID(as_uuid=True),
        sa.ForeignKey("device_readings.id", ondelete="SET NULL"), nullable=True))
    op.create_index("uq_vitals_device_reading", "encounter_vitals", ["device_reading_id"],
                    unique=True, postgresql_where=sa.text("device_reading_id IS NOT NULL"))

    # --- RLS, grants, guards -----------------------------------------------------------
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""CREATE POLICY {table}_tenant ON {table}
            USING (organization_id = {GUC_ORG}) WITH CHECK (organization_id = {GUC_ORG});""")
        op.execute(f"REVOKE DELETE ON {table} FROM hms_app;")
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_device_record_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only (blocked %)', TG_TABLE_NAME, TG_OP
              USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("device_readings", "device_reading_decisions"):
        op.execute(f"REVOKE UPDATE ON {table} FROM hms_app;")
        op.execute(f"""CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE
            ON {table} FOR EACH ROW EXECUTE FUNCTION forbid_device_record_mutation();""")
    op.execute("""
        CREATE OR REPLACE FUNCTION guard_medical_device() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'medical_devices rows cannot be deleted (retire instead)'
                  USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.organization_id <> OLD.organization_id OR NEW.kind <> OLD.kind
               OR NEW.address_hash <> OLD.address_hash OR NEW.is_simulator <> OLD.is_simulator
               OR NEW.manufacturer <> OLD.manufacturer OR NEW.model <> OLD.model
               OR NEW.serial <> OLD.serial OR NEW.firmware <> OLD.firmware
               OR NEW.created_at <> OLD.created_at
               OR NEW.registered_by IS DISTINCT FROM OLD.registered_by THEN
                RAISE EXCEPTION 'medical device identity is immutable (register a new device)'
                  USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF OLD.status = 'retired' AND (NEW.status <> 'retired'
               OR NEW.retired_at IS DISTINCT FROM OLD.retired_at) THEN
                RAISE EXCEPTION 'a retired medical device cannot be reactivated'
                  USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""CREATE TRIGGER trg_medical_devices_guard BEFORE UPDATE OR DELETE
        ON medical_devices FOR EACH ROW EXECUTE FUNCTION guard_medical_device();""")

    # --- permissions and the edition feature ---------------------------------------------
    op.bulk_insert(sa.table("permissions", sa.column("key", sa.String),
                            sa.column("description", sa.Text)),
                   [{"key": k, "description": d} for k, d in DEVICE_PERMS])
    conn = op.get_bind()
    role_ids = {key: str(rid) for rid, key in
                conn.execute(sa.text("SELECT id, key FROM roles")).fetchall()}
    op.bulk_insert(
        sa.table("role_permissions", sa.column("role_id", sa.String),
                 sa.column("permission_key", sa.String)),
        [{"role_id": role_ids[r], "permission_key": p}
         for r, perms in ROLE_GRANTS.items() if r in role_ids for p in perms],
    )
    # editions with consultation get the feature; the platform console can change it
    conn.execute(sa.text(
        "INSERT INTO plan_features (plan_id, feature_key) SELECT plan_id, :f "
        "FROM plan_features WHERE feature_key = 'consultation' ON CONFLICT DO NOTHING"),
        {"f": FEATURE})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM plan_features WHERE feature_key = :f"), {"f": FEATURE})
    keys = [p for p, _ in DEVICE_PERMS]
    for stmt in ("DELETE FROM role_permissions WHERE permission_key IN :keys",
                 "DELETE FROM permissions WHERE key IN :keys"):
        conn.execute(sa.text(stmt).bindparams(sa.bindparam("keys", expanding=True)),
                     {"keys": keys})
    op.drop_index("uq_vitals_device_reading", table_name="encounter_vitals")
    op.drop_column("encounter_vitals", "device_reading_id")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS guard_medical_device()")
    op.execute("DROP FUNCTION IF EXISTS forbid_device_record_mutation()")
