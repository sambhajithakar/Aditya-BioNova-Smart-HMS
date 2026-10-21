"""M7.1: tenant administration, commercial editions, platform console, support.

Revision ID: 0011
Revises: 0010

* organizations: clinic profile (legal name, address, GSTIN, registration,
  letterhead note, language, timezone), role-aware MFA policy, offboarding
  request. branches: address / phone / GSTIN.
* plans / plan_features / plan_limits: the edition catalogue as DATA. Seven
  editions are seeded with features and limits; **prices are left NULL** —
  they are configured by the platform owner, never hard-coded.
* subscriptions (one per tenant) + append-only subscription_events.
* support_tickets / support_ticket_messages (internal vendor notes hidden
  from tenants by RLS).
* Platform access: a transaction-local GUC ``app.platform_admin`` that the
  API sets only for verified super-admins. It opens ONLY the commercial
  tables above (+ organizations); every clinical/PHI table keeps its strict
  tenant-only policy, so platform operators can never read patient data.
  ``platform_tenant_overview()`` (SECURITY DEFINER) returns per-tenant usage
  COUNTS (no PHI) for the console.
* Existing tenants are grandfathered onto an active ``hospital_advanced``
  subscription so nothing they use today is withdrawn by this migration.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

GUC_ORG = "nullif(current_setting('app.current_org_id', true), '')::uuid"
PLATFORM = "coalesce(current_setting('app.platform_admin', true), '') = 'true'"

M71_PERMS = [
    ("subscription.read", "View the clinic's edition, entitlements and usage"),
    ("subscription.manage", "Request edition / billing-cycle changes"),
    ("support.read", "View the clinic's support tickets"),
    ("support.write", "Open and reply to support tickets"),
    ("org.offboard", "Export all clinic data and request account closure"),
]
ROLE_GRANTS = {
    "owner": [p for p, _ in M71_PERMS],
    "admin": ["subscription.read", "subscription.manage", "support.read", "support.write"],
    "billing": ["subscription.read"],
    "auditor": ["subscription.read"],
    "support": ["support.read", "support.write"],
}

_CORE = ["patients", "appointments", "opd_queue", "consultation", "billing",
         "reports_basic", "mobile_offline", "comms_email"]
_STARTER = _CORE + ["pharmacy", "inventory", "expenses", "comms_sms"]
_PLUS_AI = _STARTER + ["laboratory", "reports_advanced", "comms_whatsapp",
                       "ai_scribe", "ai_copilot"]
_MULTI = _PLUS_AI + ["multi_branch", "departments", "ai_rag", "ai_document",
                     "audit_export"]
_HOSP_CORE = _PLUS_AI + ["ipd", "nursing", "emergency", "insurance_tpa", "multi_branch",
                         "departments"]
_HOSP_ADV = _HOSP_CORE + ["ot", "ai_agents", "ai_forecast", "ai_rag", "ai_document",
                          "abdm", "fhir_api", "audit_export"]
_ALL = sorted(set(_HOSP_ADV + ["api_access", "custom_roles", "priority_support"]))

# code, name, tier, trial_days, description, features, limits
EDITIONS = [
    ("rural_clinic", "BioNova Rural Clinic", 1, 30,
     "Offline-first Android workflows, trilingual, fast prescriptions and simple billing "
     "for single-doctor rural clinics.",
     ["patients", "appointments", "opd_queue", "consultation", "billing", "reports_basic",
      "mobile_offline", "comms_sms"],
     {"max_users": 3, "max_branches": 1, "max_beds": 0, "ai_credits_monthly": 0,
      "sms_monthly": 300, "whatsapp_monthly": 0}),
    ("clinic_starter", "Clinic Starter", 2, 30,
     "OPD, e-prescriptions, billing, pharmacy and basic reports for small clinics.",
     _STARTER,
     {"max_users": 5, "max_branches": 1, "max_beds": 0, "ai_credits_monthly": 0,
      "sms_monthly": 500, "whatsapp_monthly": 0}),
    ("clinic_plus_ai", "Clinic Plus + AI", 3, 30,
     "Adds laboratory, advanced analytics, WhatsApp and AI scribe / business copilot.",
     _PLUS_AI,
     {"max_users": 10, "max_branches": 2, "max_beds": 0, "ai_credits_monthly": 1000,
      "sms_monthly": 1000, "whatsapp_monthly": 1000}),
    ("multi_specialty_clinic", "Multi-Specialty Clinic", 4, 30,
     "Multiple departments and branches with knowledge assistant and document AI.",
     _MULTI,
     {"max_users": 30, "max_branches": 5, "max_beds": 10, "ai_credits_monthly": 3000,
      "sms_monthly": 3000, "whatsapp_monthly": 3000}),
    ("hospital_core", "Hospital Core", 5, 30,
     "IPD, beds, nursing, emergency and insurance/TPA workflows for hospitals.",
     _HOSP_CORE,
     {"max_users": 50, "max_branches": 3, "max_beds": 100, "ai_credits_monthly": 2000,
      "sms_monthly": 5000, "whatsapp_monthly": 5000}),
    ("hospital_advanced", "Hospital Advanced", 6, 30,
     "Adds OT scheduling, AI agents and forecasting, ABDM and FHIR interoperability.",
     _HOSP_ADV,
     {"max_users": 200, "max_branches": 10, "max_beds": 500, "ai_credits_monthly": 10000,
      "sms_monthly": 20000, "whatsapp_monthly": 20000}),
    ("enterprise", "Enterprise", 7, 0,
     "Unlimited scale, custom roles, API access and priority support — contract-based.",
     _ALL,
     {"max_users": None, "max_branches": None, "max_beds": None,
      "ai_credits_monthly": None, "sms_monthly": None, "whatsapp_monthly": None}),
]

PROFILE_COLUMNS = [
    ("legal_name", sa.String(200)), ("address_line1", sa.String(200)),
    ("address_line2", sa.String(200)), ("city", sa.String(100)), ("state", sa.String(100)),
    ("pincode", sa.String(6)), ("phone", sa.String(20)), ("email", sa.String(320)),
    ("gstin", sa.String(15)), ("registration_number", sa.String(60)),
    ("letterhead_note", sa.String(500)),
]


def _ts(name: str, **kw) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def upgrade() -> None:
    # ---------------------------------------------------- tenant profile
    for name, col_type in PROFILE_COLUMNS:
        op.add_column("organizations", sa.Column(name, col_type, nullable=True))
    op.add_column("organizations", sa.Column("default_language", sa.String(2),
                                             nullable=False, server_default="en"))
    op.add_column("organizations", sa.Column("timezone", sa.String(64), nullable=False,
                                             server_default="Asia/Kolkata"))
    op.add_column("organizations", sa.Column("mfa_required_roles", ARRAY(sa.String(40)),
                                             nullable=False, server_default="{}"))
    op.add_column("organizations", _ts("offboarding_requested_at", nullable=True))
    op.add_column("organizations", sa.Column("offboarding_requested_by", UUID(as_uuid=True),
                                             sa.ForeignKey("users.id", ondelete="SET NULL"),
                                             nullable=True))
    op.add_column("organizations", sa.Column("offboarding_reason", sa.String(500),
                                             nullable=True))
    op.create_check_constraint("ck_org_language", "organizations",
                               "default_language IN ('en','mr','hi')")
    op.create_check_constraint(
        "ck_org_gstin", "organizations",
        "gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'")
    op.create_check_constraint("ck_org_pincode", "organizations",
                               "pincode IS NULL OR pincode ~ '^[1-9][0-9]{5}$'")

    op.add_column("branches", sa.Column("address", sa.String(300), nullable=True))
    op.add_column("branches", sa.Column("phone", sa.String(20), nullable=True))
    op.add_column("branches", sa.Column("gstin", sa.String(15), nullable=True))
    op.add_column("branches", _ts("updated_at", nullable=False, server_default=sa.func.now()))
    op.create_check_constraint(
        "ck_branch_gstin", "branches",
        "gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'")

    # ---------------------------------------------------- edition catalogue
    op.create_table(
        "plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("price_monthly_paise", sa.BigInteger(), nullable=True),
        sa.Column("price_annual_paise", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("price_monthly_paise IS NULL OR price_monthly_paise >= 0",
                           name="ck_plan_price_monthly"),
        sa.CheckConstraint("price_annual_paise IS NULL OR price_annual_paise >= 0",
                           name="ck_plan_price_annual"),
        sa.CheckConstraint("trial_days BETWEEN 0 AND 365", name="ck_plan_trial_days"),
    )
    op.create_table(
        "plan_features",
        sa.Column("plan_id", UUID(as_uuid=True),
                  sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint("plan_id", "feature_key", name="pk_plan_features"),
    )
    op.create_table(
        "plan_limits",
        sa.Column("plan_id", UUID(as_uuid=True),
                  sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("limit_key", sa.String(40), nullable=False),
        sa.Column("limit_value", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("plan_id", "limit_key", name="pk_plan_limits"),
        sa.CheckConstraint("limit_value IS NULL OR limit_value >= 0",
                           name="ck_plan_limit_nonneg"),
    )

    # ---------------------------------------------------- subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("plan_id", UUID(as_uuid=True),
                  sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("billing_cycle", sa.String(10), nullable=False, server_default="monthly"),
        _ts("trial_ends_at", nullable=True),
        _ts("current_period_start", nullable=True),
        _ts("current_period_end", nullable=True),
        _ts("grace_until", nullable=True),
        sa.Column("feature_overrides", JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("limit_overrides", JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('trialing','active','past_due','read_only','suspended','cancelled')",
            name="ck_subscription_status"),
        sa.CheckConstraint("billing_cycle IN ('monthly','annual')",
                           name="ck_subscription_cycle"),
    )
    op.create_table(
        "subscription_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_plan", sa.String(40), nullable=True),
        sa.Column("to_plan", sa.String(40), nullable=True),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("actor_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subevent_org_created", "subscription_events",
                    ["organization_id", "created_at"])

    # ---------------------------------------------------- support
    op.execute("CREATE SEQUENCE support_ticket_number_seq START 1;")
    op.create_table(
        "support_tickets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(20), nullable=False, unique=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(25), nullable=False, server_default="open"),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "category IN ('technical','billing','account','feature_request',"
            "'data_request','other')", name="ck_ticket_category"),
        sa.CheckConstraint("priority IN ('low','normal','high','urgent')",
                           name="ck_ticket_priority"),
        sa.CheckConstraint(
            "status IN ('open','in_progress','waiting_on_customer','resolved','closed')",
            name="ck_ticket_status"),
    )
    op.create_index("ix_ticket_org_status", "support_tickets", ["organization_id", "status"])
    op.create_table(
        "support_ticket_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("ticket_id", UUID(as_uuid=True),
                  sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_side", sa.String(10), nullable=False),
        sa.Column("body", sa.String(5000), nullable=False),
        sa.Column("internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("author_side IN ('customer','vendor')", name="ck_ticketmsg_side"),
        sa.CheckConstraint("NOT internal OR author_side = 'vendor'",
                           name="ck_ticketmsg_internal_vendor"),
    )
    op.create_index("ix_ticketmsg_ticket", "support_ticket_messages", ["ticket_id", "id"])

    # ---------------------------------------------------- seed editions (no prices)
    conn = op.get_bind()
    for code, name, tier, trial, desc, features, limits in EDITIONS:
        plan_id = conn.execute(sa.text(
            "INSERT INTO plans (code, name, tier, trial_days, description, is_public) "
            "VALUES (:c, :n, :t, :d, :desc, :pub) RETURNING id"),
            {"c": code, "n": name, "t": tier, "d": trial, "desc": desc,
             "pub": code != "enterprise"}).scalar_one()
        for f in sorted(set(features)):
            conn.execute(sa.text("INSERT INTO plan_features VALUES (:p, :f)"),
                         {"p": plan_id, "f": f})
        for key, value in limits.items():
            conn.execute(sa.text("INSERT INTO plan_limits VALUES (:p, :k, :v)"),
                         {"p": plan_id, "k": key, "v": value})

    # grandfather existing tenants: keep everything they have today
    conn.execute(sa.text(
        """
        INSERT INTO subscriptions (organization_id, plan_id, status, billing_cycle)
        SELECT o.id, p.id, 'active', 'monthly'
        FROM organizations o, plans p WHERE p.code = 'hospital_advanced'
        """))
    conn.execute(sa.text(
        """
        INSERT INTO subscription_events (organization_id, to_plan, to_status, reason)
        SELECT s.organization_id, 'hospital_advanced', 'active',
               'M7.1 migration: existing tenant grandfathered'
        FROM subscriptions s
        """))

    # ---------------------------------------------------- RBAC seed
    op.bulk_insert(sa.table("permissions", sa.column("key", sa.String),
                            sa.column("description", sa.Text)),
                   [{"key": k, "description": d} for k, d in M71_PERMS])
    role_ids = {key: str(rid) for rid, key in
                conn.execute(sa.text("SELECT id, key FROM roles")).fetchall()}
    op.bulk_insert(
        sa.table("role_permissions", sa.column("role_id", sa.String),
                 sa.column("permission_key", sa.String)),
        [{"role_id": role_ids[r], "permission_key": p}
         for r, perms in ROLE_GRANTS.items() for p in perms],
    )

    # ---------------------------------------------------- row-level security
    op.execute(f"""
        CREATE POLICY org_select_platform ON organizations FOR SELECT USING ({PLATFORM});
    """)
    op.execute(f"""
        CREATE POLICY org_update_platform ON organizations FOR UPDATE
        USING ({PLATFORM}) WITH CHECK ({PLATFORM});
    """)
    for table in ("plans", "plan_features", "plan_limits"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (true);")
        op.execute(f"CREATE POLICY {table}_write ON {table} FOR ALL "
                   f"USING ({PLATFORM}) WITH CHECK ({PLATFORM});")

    op.execute("ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;")
    op.execute(f"""CREATE POLICY subscription_read ON subscriptions FOR SELECT
        USING (organization_id = {GUC_ORG} OR {PLATFORM});""")
    # a tenant creates its own row once (registration); only the platform changes it
    op.execute(f"""CREATE POLICY subscription_insert ON subscriptions FOR INSERT
        WITH CHECK (organization_id = {GUC_ORG} OR {PLATFORM});""")
    op.execute(f"""CREATE POLICY subscription_update ON subscriptions FOR UPDATE
        USING ({PLATFORM}) WITH CHECK ({PLATFORM});""")
    op.execute("REVOKE DELETE ON subscriptions FROM hms_app;")

    op.execute("ALTER TABLE subscription_events ENABLE ROW LEVEL SECURITY;")
    op.execute(f"""CREATE POLICY subevent_rw ON subscription_events
        USING (organization_id = {GUC_ORG} OR {PLATFORM})
        WITH CHECK (organization_id = {GUC_ORG} OR {PLATFORM});""")
    op.execute("REVOKE UPDATE, DELETE ON subscription_events FROM hms_app;")

    op.execute("ALTER TABLE support_tickets ENABLE ROW LEVEL SECURITY;")
    op.execute(f"""CREATE POLICY ticket_rw ON support_tickets
        USING (organization_id = {GUC_ORG} OR {PLATFORM})
        WITH CHECK (organization_id = {GUC_ORG} OR {PLATFORM});""")
    op.execute("REVOKE DELETE ON support_tickets FROM hms_app;")

    op.execute("ALTER TABLE support_ticket_messages ENABLE ROW LEVEL SECURITY;")
    op.execute(f"""CREATE POLICY ticketmsg_read ON support_ticket_messages FOR SELECT
        USING ((organization_id = {GUC_ORG} AND NOT internal) OR {PLATFORM});""")
    op.execute(f"""CREATE POLICY ticketmsg_insert ON support_ticket_messages FOR INSERT
        WITH CHECK ((organization_id = {GUC_ORG} AND NOT internal
                     AND author_side = 'customer') OR {PLATFORM});""")
    op.execute("REVOKE UPDATE, DELETE ON support_ticket_messages FROM hms_app;")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE support_ticket_number_seq TO hms_app;")

    op.execute(f"""
        CREATE OR REPLACE FUNCTION platform_tenant_overview()
        RETURNS TABLE (organization_id uuid, users bigint, branches bigint, beds bigint,
                       patients bigint)
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public
        AS $$
        BEGIN
            IF NOT ({PLATFORM}) THEN
                RAISE EXCEPTION 'platform access required';
            END IF;
            RETURN QUERY
            SELECT o.id,
                   (SELECT count(*) FROM memberships m
                     WHERE m.organization_id = o.id AND m.status = 'active'),
                   (SELECT count(*) FROM branches b
                     WHERE b.organization_id = o.id AND b.status = 'active'),
                   (SELECT count(*) FROM beds d WHERE d.organization_id = o.id),
                   (SELECT count(*) FROM patients p WHERE p.organization_id = o.id)
            FROM organizations o;
        END;
        $$;
    """)
    op.execute("REVOKE ALL ON FUNCTION platform_tenant_overview() FROM PUBLIC;")
    op.execute("GRANT EXECUTE ON FUNCTION platform_tenant_overview() TO hms_app;")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS platform_tenant_overview();")
    keys = [p for p, _ in M71_PERMS]
    conn = op.get_bind()
    for stmt in ("DELETE FROM role_permissions WHERE permission_key IN :keys",
                 "DELETE FROM permissions WHERE key IN :keys"):
        conn.execute(sa.text(stmt).bindparams(sa.bindparam("keys", expanding=True)),
                     {"keys": keys})
    for table in ("support_ticket_messages", "support_tickets", "subscription_events",
                  "subscriptions", "plan_limits", "plan_features", "plans"):
        op.drop_table(table)
    op.execute("DROP SEQUENCE IF EXISTS support_ticket_number_seq;")
    op.execute("DROP POLICY IF EXISTS org_update_platform ON organizations;")
    op.execute("DROP POLICY IF EXISTS org_select_platform ON organizations;")
    op.drop_constraint("ck_branch_gstin", "branches")
    for col in ("updated_at", "gstin", "phone", "address"):
        op.drop_column("branches", col)
    for name in ("ck_org_pincode", "ck_org_gstin", "ck_org_language"):
        op.drop_constraint(name, "organizations")
    for col in ("offboarding_reason", "offboarding_requested_by", "offboarding_requested_at",
                "mfa_required_roles", "timezone", "default_language"):
        op.drop_column("organizations", col)
    for name, _ in reversed(PROFILE_COLUMNS):
        op.drop_column("organizations", name)
