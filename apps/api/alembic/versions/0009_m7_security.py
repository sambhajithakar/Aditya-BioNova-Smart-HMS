"""M7.0 security: MFA, password reset, invitations, rate limits, comms outbox.

Revision ID: 0009
Revises: 0008

* users: encrypted TOTP seed (+ pending seed during enrolment), replay guard
  (last accepted time step), password change timestamp.
* mfa_recovery_codes / password_reset_tokens: identity-level (no tenant), so
  like ``users`` they have no RLS; only SHA-256 hashes are stored.
* auth_sessions.absolute_expires_at: hard cap on a refresh-rotation family.
* member_invitations: tenant data with strict RLS. Accepting happens before
  any tenant context exists, so ``invitation_org_for_token()`` (SECURITY
  DEFINER) reveals only the organization id of a *pending, unexpired*
  invitation matching a token hash — nothing else.
* rate_limit_counters: hashed keys, fixed windows, shared across instances.
* comms_messages: outbound message log for the mock/suppressed providers.
* insert_audit_event(): the tenancy guard compared with ``<>``, which is NULL
  (= pass) when no org context is set; now ``IS DISTINCT FROM``.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"

_AUDIT_FN = """
    CREATE OR REPLACE FUNCTION insert_audit_event(
        p_organization_id uuid,
        p_actor_user_id uuid,
        p_action text,
        p_resource_type text,
        p_resource_id text,
        p_metadata jsonb,
        p_correlation_id text,
        p_ip_address text
    ) RETURNS void
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
    AS $$
    BEGIN
        IF p_organization_id IS NOT NULL
           AND p_organization_id IS {op}
               nullif(current_setting('app.current_org_id', true), '')::uuid THEN
            RAISE EXCEPTION 'audit insert denied for organization %', p_organization_id;
        END IF;
        INSERT INTO audit_events (
            organization_id, actor_user_id, action, resource_type,
            resource_id, metadata, correlation_id, ip_address
        ) VALUES (
            p_organization_id, p_actor_user_id, p_action, p_resource_type,
            p_resource_id, p_metadata, p_correlation_id, p_ip_address
        );
    END;
    $$;
"""


def upgrade() -> None:
    # --- users: MFA + password metadata
    op.add_column("users", sa.Column("mfa_totp_secret_enc", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_totp_pending_enc", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_totp_enabled_at",
                                     sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mfa_totp_last_step", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("password_changed_at",
                                     sa.DateTime(timezone=True), nullable=True))

    op.add_column("auth_sessions", sa.Column("absolute_expires_at",
                                             sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mfa_recovery_user", "mfa_recovery_codes", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("ip_address", sa.String(60), nullable=True),
    )
    op.create_index("ix_pwreset_user", "password_reset_tokens", ["user_id"])

    op.create_table(
        "member_invitations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invited_by_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accepted_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked')", name="ck_invitation_status"
        ),
    )
    op.create_index("ix_invitation_org_status", "member_invitations",
                    ["organization_id", "status"])
    op.execute("ALTER TABLE member_invitations ENABLE ROW LEVEL SECURITY;")
    op.execute(f"""
        CREATE POLICY invitation_tenant ON member_invitations
        USING (organization_id = {GUC_ORG})
        WITH CHECK (organization_id = {GUC_ORG});
    """)
    op.execute("REVOKE DELETE ON member_invitations FROM hms_app;")
    op.execute("""
        CREATE OR REPLACE FUNCTION invitation_org_for_token(p_token_hash text)
        RETURNS uuid
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT organization_id FROM member_invitations
            WHERE token_hash = p_token_hash
              AND status = 'pending'
              AND expires_at > now()
        $$;
    """)
    op.execute("REVOKE ALL ON FUNCTION invitation_org_for_token(text) FROM PUBLIC;")
    op.execute("GRANT EXECUTE ON FUNCTION invitation_org_for_token(text) TO hms_app;")

    op.create_table(
        "rate_limit_counters",
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key_hash", "window_start", name="pk_rate_limit_counters"),
    )
    op.create_index("ix_rate_limit_expires", "rate_limit_counters", ["expires_at"])

    op.create_table(
        "comms_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("channel IN ('email', 'sms', 'whatsapp')", name="ck_comms_channel"),
    )
    op.create_index("ix_comms_created", "comms_messages", ["created_at"])
    # the outbox is a log: the app may add and read rows, never rewrite them
    op.execute("REVOKE UPDATE, DELETE ON comms_messages FROM hms_app;")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE comms_messages_id_seq TO hms_app;")

    op.execute(_AUDIT_FN.replace("{op}", "DISTINCT FROM"))


def downgrade() -> None:
    op.execute(_AUDIT_FN.replace("IS {op}", "<>"))
    op.drop_table("comms_messages")
    op.drop_table("rate_limit_counters")
    op.execute("DROP FUNCTION IF EXISTS invitation_org_for_token(text);")
    op.execute("DROP POLICY IF EXISTS invitation_tenant ON member_invitations;")
    op.drop_table("member_invitations")
    op.drop_table("password_reset_tokens")
    op.drop_table("mfa_recovery_codes")
    op.drop_column("auth_sessions", "absolute_expires_at")
    for col in ("password_changed_at", "mfa_totp_last_step", "mfa_totp_enabled_at",
                "mfa_totp_pending_enc", "mfa_totp_secret_enc"):
        op.drop_column("users", col)
