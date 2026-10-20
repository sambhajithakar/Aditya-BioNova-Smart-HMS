# Database Schema (PostgreSQL 16)

> **Generated file.** Everything from the "Migrations" heading down is produced
> by `scripts/generate_db_schema.py` from the catalog of a freshly migrated
> database. The "Tenancy model" overview is maintained inside the generator.
> Do not edit by hand. To regenerate:
>
> ```bash
> # 1. empty database, migrated as the owner role
> psql -h 127.0.0.1 -p 5433 -U hms -d postgres \
>   -c "DROP DATABASE IF EXISTS hms_docs_gen" -c "CREATE DATABASE hms_docs_gen OWNER hms"
> cd apps/api && \
>   DATABASE_URL=postgresql+psycopg2://hms_app:<pw>@127.0.0.1:5433/hms_docs_gen \
>   MIGRATION_DATABASE_URL=postgresql+psycopg2://hms:<pw>@127.0.0.1:5433/hms_docs_gen \
>   JWT_SECRET=<48+ random chars> alembic upgrade head
> # 2. generate (as the OWNER role)
> cd ../.. && python scripts/generate_db_schema.py \
>   --dsn postgresql://hms:<pw>@127.0.0.1:5433/hms_docs_gen
> ```
>
> CI does not check this file; regenerate it whenever a migration is added.

## Tenancy model (overview)

- **Shared database, shared schema, row-level tenancy.** Every tenant-owned
  table carries `organization_id` and has PostgreSQL row-level security (RLS)
  enabled. Policies compare it with the GUC `app.current_org_id`.
- **Tenant context comes only from the verified token.** For each request the
  API sets transaction-local GUCs with `set_config(name, value, true)`:
  `app.current_org_id` and `app.current_user_id` (plus `app.is_bootstrap`
  during organization registration). Transaction-local means a pooled
  connection never carries one tenant's context into another request. No
  client header or parameter can set them.
- **Two roles.** Migrations run as the table **owner** (`MIGRATION_DATABASE_URL`).
  The application runs as **`hms_app`**, a non-owner, non-superuser role
  without `BYPASSRLS`, so RLS is always enforced for it. RLS is not `FORCE`d,
  so the owner role (migrations, backups, this generator) sees all rows. The
  "Grants for hms_app" lines below are the complete privilege set of the app.
- **Tables without RLS by design:**
  - `users`, `auth_sessions`, `mfa_recovery_codes`, `password_reset_tokens`:
    identity-level data. A user can belong to several organizations, and
    login, refresh, MFA and password reset happen *before* any tenant context
    exists. Access is scoped by the service layer to the authenticated user;
    secrets are stored only as hashes (or encrypted, for TOTP seeds).
  - `rate_limit_counters`: keyed by a hash of IP / account, consulted before
    authentication; contains no tenant data.
  - `comms_messages`: the outbound message log (e-mail/SMS/WhatsApp) of the
    mock/suppressed providers; written from pre-tenant flows such as
    password reset. The app may insert and read, never update or delete.
  - Reference catalogues (`roles`, `permissions`, `role_permissions`,
    `drug_catalog`, `lab_test_catalog`) are global, read-only for `hms_app`.
- **Cross-tenant ids look like "not found".** Because RLS hides other tenants'
  rows, the API returns 404 for them.
- **Append-only ledgers and immutable clinical records are enforced in the
  database**, not just in code: `BEFORE UPDATE/DELETE` triggers raise on
  `audit_events`, `ledger_entries`, stock and inventory movements, payments,
  refunds, signed prescriptions, dispenses, released lab results, issued
  invoices and similar (see the per-table "Triggers" lists), and `hms_app`
  additionally lacks `UPDATE`/`DELETE` grants on several of them. Trigger
  errors (`P0001`) are surfaced by the API as `409`.
- **SECURITY DEFINER functions** are the only paths that cross the RLS
  boundary (audit inserts with NULL organization for pre-tenant security
  events; resolving the organization of a pending invitation token). They are
  listed at the end with their `search_path` pinning.

## Migrations

Database at Alembic head **0016** (catalog read from PostgreSQL 16). Files in `apps/api/alembic/versions/`.

| Revision | Down | File | Summary |
|---|---|---|---|
| 0001 | - | `0001_initial_schema.py` | Initial schema: tenancy, identity, RBAC, sessions, audit + row-level security. |
| 0002 | 0001 | `0002_seed_rbac.py` | Seed the permission catalogue and system roles. |
| 0003 | 0002 | `0003_audit_insert_function.py` | Add insert_audit_event() SECURITY DEFINER helper. |
| 0004 | 0003 | `0004_fix_auditor_role.py` | Restrict the auditor role to true read-only access. |
| 0005 | 0004 | `0005_patients_appointments_queue.py` | M2: patients, appointments, OPD queue, idempotency keys + clinical RBAC. |
| 0006 | 0005 | `0006_m3_consultation_billing.py` | M3: encounters, vitals, diagnoses, prescriptions, billing + ledger. |
| 0007 | 0006 | `0007_m5_pharmacy_lab.py` | M5: pharmacy stock (batch/expiry/FEFO) + laboratory orders and results. |
| 0008 | 0007 | `0008_m6_ipd_operations.py` | M6: IPD (wards, beds, admissions, nursing, discharge) + operations (inventory, expenses) and the report backing tables. |
| 0009 | 0008 | `0009_m7_security.py` | M7.0 security: MFA, password reset, invitations, rate limits, comms outbox. |
| 0010 | 0009 | `0010_m7_integrity.py` | M7.0 integrity hardening: signed-Rx INSERT guard, dispense caps, lab order items, invoice/payment immutability, OPD queue uniqueness. |
| 0011 | 0010 | `0011_m71_tenancy_saas.py` | M7.1: tenant administration, commercial editions, platform console, support. |
| 0012 | 0011 | `0012_ai_gateway.py` | AI-0: AI gateway governance — tenant opt-in, AI request audit, credit ledger. |
| 0013 | 0012 | `0013_saas_billing.py` | M7.2: SaaS subscription billing — orders, payments, webhooks, invoices, refunds and AI credit packs (Razorpay sandbox / local payment simulator). |
| 0014 | 0013 | `0014_comms_followups.py` | Communications framework v2 + clinician-directed follow-up CRM. |
| 0015 | 0014 | `0015_setup_checkin_print.py` | Smart Setup Wizard, Smart Patient QR Check-In and Smart Printer Setup. |
| 0016 | 0015 | `0016_ai1.py` | AI-1: forecasting model runs, knowledge base (RAG), agent proposals with human approval, Clinical Scribe draft workflow. |

## Application role

`hms_app`: superuser=no, bypassrls=no, login=yes.

## Table index

| Table | RLS | Policies | Triggers | hms_app grants |
|---|---|---|---|---|
| [admission_transfers](#admission_transfers) | yes | 1 | 1 | SELECT, INSERT |
| [admissions](#admissions) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [ai_credit_ledger](#ai_credit_ledger) | yes | 1 | 1 | SELECT, INSERT |
| [ai_credit_packs](#ai_credit_packs) | yes | 2 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [ai_model_runs](#ai_model_runs) | yes | 1 | 1 | SELECT, INSERT |
| [ai_proposal_events](#ai_proposal_events) | yes | 1 | 1 | SELECT, INSERT |
| [ai_proposals](#ai_proposals) | yes | 1 | 1 | SELECT, INSERT, UPDATE |
| [ai_reorder_drafts](#ai_reorder_drafts) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [ai_requests](#ai_requests) | yes | 1 | 1 | SELECT, INSERT |
| [ai_staff_tasks](#ai_staff_tasks) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [ai_tenant_settings](#ai_tenant_settings) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [alembic_version](#alembic_version) | **no** | 0 | 0 | SELECT |
| [appointments](#appointments) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [audit_events](#audit_events) | yes | 2 | 1 | SELECT, INSERT |
| [auth_sessions](#auth_sessions) | **no** | 0 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [beds](#beds) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [branch_working_hours](#branch_working_hours) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [branches](#branches) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [checkin_tokens](#checkin_tokens) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [comms_consent_events](#comms_consent_events) | yes | 1 | 1 | SELECT, INSERT |
| [comms_consents](#comms_consents) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [comms_delivery_log](#comms_delivery_log) | yes | 1 | 1 | SELECT, INSERT |
| [comms_messages](#comms_messages) | **no** | 0 | 0 | SELECT, INSERT |
| [comms_patient_preferences](#comms_patient_preferences) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [comms_templates](#comms_templates) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [comms_tenant_settings](#comms_tenant_settings) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [dispense_items](#dispense_items) | yes | 1 | 1 | SELECT, INSERT |
| [dispenses](#dispenses) | yes | 1 | 1 | SELECT, INSERT |
| [drug_catalog](#drug_catalog) | **no** | 0 | 0 | SELECT |
| [encounter_diagnoses](#encounter_diagnoses) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [encounter_vitals](#encounter_vitals) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [encounters](#encounters) | yes | 1 | 2 | SELECT, INSERT, UPDATE, DELETE |
| [expenses](#expenses) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [fee_schedule](#fee_schedule) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [follow_ups](#follow_ups) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [idempotency_keys](#idempotency_keys) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [inventory_items](#inventory_items) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [inventory_movements](#inventory_movements) | yes | 1 | 2 | SELECT, INSERT |
| [invoice_items](#invoice_items) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [invoices](#invoices) | yes | 1 | 2 | SELECT, INSERT, UPDATE, DELETE |
| [kb_chunks](#kb_chunks) | yes | 1 | 1 | SELECT, INSERT |
| [kb_documents](#kb_documents) | yes | 1 | 1 | SELECT, INSERT, UPDATE |
| [lab_order_items](#lab_order_items) | yes | 1 | 1 | SELECT, INSERT, UPDATE |
| [lab_orders](#lab_orders) | yes | 1 | 2 | SELECT, INSERT, UPDATE, DELETE |
| [lab_results](#lab_results) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [lab_specimens](#lab_specimens) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [lab_test_catalog](#lab_test_catalog) | **no** | 0 | 0 | SELECT |
| [ledger_entries](#ledger_entries) | yes | 1 | 1 | SELECT, INSERT |
| [member_invitations](#member_invitations) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [memberships](#memberships) | yes | 4 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [mfa_recovery_codes](#mfa_recovery_codes) | **no** | 0 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [nursing_records](#nursing_records) | yes | 1 | 2 | SELECT, INSERT |
| [opd_queue](#opd_queue) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [org_settings](#org_settings) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [organizations](#organizations) | yes | 5 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [password_reset_tokens](#password_reset_tokens) | **no** | 0 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [patients](#patients) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [payments](#payments) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [permissions](#permissions) | **no** | 0 | 0 | SELECT |
| [plan_features](#plan_features) | yes | 2 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [plan_limits](#plan_limits) | yes | 2 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [plans](#plans) | yes | 2 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [prescription_items](#prescription_items) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [prescriptions](#prescriptions) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [printer_profiles](#printer_profiles) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [rate_limit_counters](#rate_limit_counters) | **no** | 0 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [refunds](#refunds) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [role_permissions](#role_permissions) | **no** | 0 | 0 | SELECT |
| [roles](#roles) | **no** | 0 | 0 | SELECT |
| [saas_invoices](#saas_invoices) | yes | 2 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [saas_orders](#saas_orders) | yes | 3 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [saas_payments](#saas_payments) | yes | 2 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [saas_refunds](#saas_refunds) | yes | 3 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [saas_webhook_events](#saas_webhook_events) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [scribe_consents](#scribe_consents) | yes | 1 | 1 | SELECT, INSERT |
| [scribe_sessions](#scribe_sessions) | yes | 1 | 1 | SELECT, INSERT, UPDATE |
| [stock_batches](#stock_batches) | yes | 1 | 1 | SELECT, INSERT, UPDATE, DELETE |
| [stock_movements](#stock_movements) | yes | 1 | 2 | SELECT, INSERT |
| [subscription_events](#subscription_events) | yes | 1 | 0 | SELECT, INSERT |
| [subscriptions](#subscriptions) | yes | 3 | 0 | SELECT, INSERT, UPDATE |
| [support_ticket_messages](#support_ticket_messages) | yes | 2 | 0 | SELECT, INSERT |
| [support_tickets](#support_tickets) | yes | 1 | 0 | SELECT, INSERT, UPDATE |
| [users](#users) | **no** | 0 | 0 | SELECT, INSERT, UPDATE, DELETE |
| [wards](#wards) | yes | 1 | 0 | SELECT, INSERT, UPDATE, DELETE |

## Tables

### admission_transfers

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `admission_id` | uuid | no |  |
| `from_bed_id` | uuid | no |  |
| `to_bed_id` | uuid | no |  |
| `reason` | character varying(300) | no | `''::character varying` |
| `transferred_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `admission_transfers_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `admission_transfers_admission_id_fkey`: `FOREIGN KEY (admission_id) REFERENCES admissions(id) ON DELETE RESTRICT`
- `admission_transfers_from_bed_id_fkey`: `FOREIGN KEY (from_bed_id) REFERENCES beds(id) ON DELETE RESTRICT`
- `admission_transfers_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `admission_transfers_to_bed_id_fkey`: `FOREIGN KEY (to_bed_id) REFERENCES beds(id) ON DELETE RESTRICT`
- `admission_transfers_transferred_by_fkey`: `FOREIGN KEY (transferred_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_transfer_distinct_beds`: `CHECK (from_bed_id <> to_bed_id)`

**Indexes**

- `ix_transfer_org_admission`: `btree (organization_id, admission_id, id)`

**RLS policies**

- `admission_transfers_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_transfer_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_append_only_mutation()`

### admissions

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `ward_id` | uuid | no |  |
| `bed_id` | uuid | no |  |
| `reason` | text | no | `''::text` |
| `attending_user_id` | uuid | yes |  |
| `status` | character varying(20) | no | `'admitted'::character varying` |
| `admitted_at` | timestamp with time zone | no | `now()` |
| `admitted_by` | uuid | yes |  |
| `discharge_outcome` | character varying(30) | yes |  |
| `discharge_summary` | text | no | `''::text` |
| `discharged_at` | timestamp with time zone | yes |  |
| `discharged_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `admissions_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `admissions_admitted_by_fkey`: `FOREIGN KEY (admitted_by) REFERENCES users(id) ON DELETE SET NULL`
- `admissions_attending_user_id_fkey`: `FOREIGN KEY (attending_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `admissions_bed_id_fkey`: `FOREIGN KEY (bed_id) REFERENCES beds(id) ON DELETE RESTRICT`
- `admissions_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `admissions_discharged_by_fkey`: `FOREIGN KEY (discharged_by) REFERENCES users(id) ON DELETE SET NULL`
- `admissions_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `admissions_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`
- `admissions_ward_id_fkey`: `FOREIGN KEY (ward_id) REFERENCES wards(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_admission_discharge_consistency`: `CHECK ((status::text = 'admitted'::text) = (discharged_at IS NULL))`
- `ck_admission_outcome`: `CHECK (discharge_outcome IS NULL OR (discharge_outcome::text = ANY (ARRAY['recovered'::character varying, 'improved'::character varying, 'referred'::character varying, 'left_against_advice'::character varying, 'death'::character varying, 'transfer_out'::character varying]::text[])))`
- `ck_admission_status`: `CHECK (status::text = ANY (ARRAY['admitted'::character varying, 'discharged'::character varying]::text[]))`

**Indexes**

- `ix_admissions_org_bed`: `btree (organization_id, bed_id)`
- `ix_admissions_org_patient`: `btree (organization_id, patient_id)`
- `ix_admissions_org_status`: `btree (organization_id, status)`
- `uq_admission_bed_occupied` (UNIQUE, partial): `btree (bed_id)` WHERE `((status)::text = 'admitted'::text)`
- `uq_admission_patient_active` (UNIQUE, partial): `btree (patient_id)` WHERE `((status)::text = 'admitted'::text)`

**RLS policies**

- `admissions_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_admission_immutable`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_admission_mutation()`

### ai_credit_ledger

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `period` | character varying(7) | no |  |
| `entry_type` | character varying(10) | no |  |
| `credits` | integer | no |  |
| `ai_request_id` | uuid | yes |  |
| `actor_user_id` | uuid | yes |  |
| `reason` | character varying(300) | no | `''::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `ai_credit_ledger_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `ai_credit_ledger_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `ai_credit_ledger_ai_request_id_fkey`: `FOREIGN KEY (ai_request_id) REFERENCES ai_requests(id) ON DELETE SET NULL`
- `ai_credit_ledger_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_aicredit_period`: `CHECK (period::text ~ '^[0-9]{4}-[0-9]{2}$'::text)`
- `ck_aicredit_type`: `CHECK (entry_type::text = ANY (ARRAY['consume'::character varying, 'grant'::character varying, 'adjust'::character varying]::text[]))`

**Indexes**

- `ix_aicredit_org_period`: `btree (organization_id, period)`

**RLS policies**

- `ai_credit_ledger_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_ai_credit_ledger_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_ai_log_mutation()`

### ai_credit_packs

- Row-level security: enabled (FORCE)
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `code` | character varying(40) | no |  |
| `name` | character varying(120) | no |  |
| `credits` | integer | no |  |
| `price_paise` | bigint | yes |  |
| `currency` | character varying(3) | no | `'INR'::character varying` |
| `is_active` | boolean | no | `true` |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `ai_credit_packs_pkey`: `PRIMARY KEY (id)`

**Unique constraints**

- `ai_credit_packs_code_key`: `UNIQUE (code)`

**Check constraints**

- `ck_aipack_credits`: `CHECK (credits > 0)`
- `ck_aipack_price`: `CHECK (price_paise IS NULL OR price_paise > 0)`

**RLS policies**

- `aipack_platform` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
- `aipack_read` FOR SELECT TO public
  - USING `true`

### ai_model_runs

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `kind` | character varying(30) | no |  |
| `scope` | character varying(80) | no | `'all'::character varying` |
| `engine_version` | character varying(40) | no |  |
| `method` | character varying(40) | no | `''::character varying` |
| `status` | character varying(20) | no |  |
| `params` | jsonb | no | `'{}'::jsonb` |
| `metrics` | jsonb | no | `'{}'::jsonb` |
| `baseline_metrics` | jsonb | no | `'{}'::jsonb` |
| `data_start` | date | yes |  |
| `data_end` | date | yes |  |
| `n_obs` | integer | no | `0` |
| `trained_by` | uuid | yes |  |
| `trained_at` | timestamp with time zone | no | `now()` |

**Primary key** `ai_model_runs_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `ai_model_runs_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `ai_model_runs_trained_by_fkey`: `FOREIGN KEY (trained_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_modelrun_kind`: `CHECK (kind::text = ANY (ARRAY['opd_demand'::character varying, 'no_show'::character varying, 'pharmacy_demand'::character varying, 'bed_occupancy'::character varying]::text[]))`
- `ck_modelrun_status`: `CHECK (status::text = ANY (ARRAY['ok'::character varying, 'insufficient_data'::character varying]::text[]))`

**Indexes**

- `ix_modelrun_org_kind`: `btree (organization_id, kind, trained_at)`

**RLS policies**

- `ai_model_runs_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_ai_model_runs_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_ai_log_mutation()`

### ai_proposal_events

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `proposal_id` | uuid | no |  |
| `from_status` | character varying(20) | yes |  |
| `to_status` | character varying(20) | no |  |
| `actor_user_id` | uuid | yes |  |
| `note` | character varying(500) | no | `''::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `ai_proposal_events_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `ai_proposal_events_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `ai_proposal_events_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `ai_proposal_events_proposal_id_fkey`: `FOREIGN KEY (proposal_id) REFERENCES ai_proposals(id) ON DELETE RESTRICT`

**Indexes**

- `ix_propevent_org_prop`: `btree (organization_id, proposal_id)`

**RLS policies**

- `ai_proposal_events_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_ai_proposal_events_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_ai_log_mutation()`

### ai_proposals

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `agent` | character varying(40) | no |  |
| `kind` | character varying(40) | no |  |
| `status` | character varying(20) | no | `'proposed'::character varying` |
| `branch_id` | uuid | yes |  |
| `title` | character varying(300) | no |  |
| `payload` | jsonb | no |  |
| `rationale` | text | no | `''::text` |
| `evidence` | jsonb | no | `'[]'::jsonb` |
| `args_sha256` | character varying(64) | no |  |
| `dedupe_key` | character varying(200) | no |  |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `expires_at` | timestamp with time zone | no |  |
| `decided_by` | uuid | yes |  |
| `decided_at` | timestamp with time zone | yes |  |
| `decision_note` | character varying(500) | no | `''::character varying` |
| `executed_at` | timestamp with time zone | yes |  |
| `result` | jsonb | yes |  |

**Primary key** `ai_proposals_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `ai_proposals_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `ai_proposals_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `ai_proposals_decided_by_fkey`: `FOREIGN KEY (decided_by) REFERENCES users(id) ON DELETE SET NULL`
- `ai_proposals_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_proposal_kind`: `CHECK (kind::text = ANY (ARRAY['followup_tasks'::character varying, 'inventory_reorder'::character varying, 'billing_reconciliation'::character varying, 'ops_daily_report'::character varying]::text[]))`
- `ck_proposal_status`: `CHECK (status::text = ANY (ARRAY['proposed'::character varying, 'approved'::character varying, 'rejected'::character varying, 'expired'::character varying, 'executed'::character varying, 'failed'::character varying]::text[]))`

**Indexes**

- `ix_proposal_org_status`: `btree (organization_id, status, created_at)`
- `uq_proposal_open_dedupe` (UNIQUE, partial): `btree (organization_id, dedupe_key)` WHERE `((status)::text = 'proposed'::text)`

**RLS policies**

- `ai_proposals_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_ai_proposals_guard`: BEFORE UPDATE FOR EACH ROW -> `guard_ai_proposal()`

### ai_reorder_drafts

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `proposal_id` | uuid | yes |  |
| `lines` | jsonb | no |  |
| `status` | character varying(20) | no | `'draft'::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `ai_reorder_drafts_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `ai_reorder_drafts_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `ai_reorder_drafts_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `ai_reorder_drafts_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `ai_reorder_drafts_proposal_id_fkey`: `FOREIGN KEY (proposal_id) REFERENCES ai_proposals(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_reorder_status`: `CHECK (status::text = ANY (ARRAY['draft'::character varying, 'ordered'::character varying, 'cancelled'::character varying]::text[]))`

**RLS policies**

- `ai_reorder_drafts_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### ai_requests

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `actor_user_id` | uuid | yes |  |
| `feature` | character varying(40) | no |  |
| `task` | character varying(40) | no |  |
| `provider` | character varying(40) | no |  |
| `model` | character varying(120) | no |  |
| `inference` | character varying(10) | no |  |
| `data_class` | character varying(2) | no |  |
| `deidentified` | boolean | no | `false` |
| `prompt_sha256` | character varying(64) | no |  |
| `prompt_redacted` | text | yes |  |
| `output_redacted` | text | yes |  |
| `output_valid` | boolean | yes |  |
| `tools_called` | jsonb | no | `'[]'::jsonb` |
| `credits` | integer | no | `0` |
| `input_units` | integer | yes |  |
| `output_units` | integer | yes |  |
| `latency_ms` | integer | yes |  |
| `status` | character varying(25) | no |  |
| `correlation_id` | character varying(64) | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `ai_requests_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `ai_requests_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `ai_requests_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_aireq_class`: `CHECK (data_class::text = ANY (ARRAY['C0'::character varying, 'C1'::character varying, 'C2'::character varying, 'C3'::character varying]::text[]))`
- `ck_aireq_credits`: `CHECK (credits >= 0)`
- `ck_aireq_inference`: `CHECK (inference::text = ANY (ARRAY['mock'::character varying, 'live'::character varying]::text[]))`
- `ck_aireq_status`: `CHECK (status::text = ANY (ARRAY['ok'::character varying, 'suppressed'::character varying, 'failed'::character varying, 'timeout'::character varying, 'rejected_output'::character varying, 'rejected_by_policy'::character varying, 'refused'::character varying]::text[]))`

**Indexes**

- `ix_aireq_org_created`: `btree (organization_id, created_at)`

**RLS policies**

- `ai_requests_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_ai_requests_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_ai_log_mutation()`

### ai_staff_tasks

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | yes |  |
| `proposal_id` | uuid | yes |  |
| `kind` | character varying(30) | no |  |
| `title` | character varying(300) | no |  |
| `subject_type` | character varying(30) | yes |  |
| `subject_id` | uuid | yes |  |
| `due_date` | date | yes |  |
| `priority` | character varying(10) | no | `'normal'::character varying` |
| `status` | character varying(20) | no | `'open'::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `completed_by` | uuid | yes |  |
| `completed_at` | timestamp with time zone | yes |  |

**Primary key** `ai_staff_tasks_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `ai_staff_tasks_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `ai_staff_tasks_completed_by_fkey`: `FOREIGN KEY (completed_by) REFERENCES users(id) ON DELETE SET NULL`
- `ai_staff_tasks_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `ai_staff_tasks_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `ai_staff_tasks_proposal_id_fkey`: `FOREIGN KEY (proposal_id) REFERENCES ai_proposals(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_stafftask_kind`: `CHECK (kind::text = 'reminder_call'::text)`
- `ck_stafftask_priority`: `CHECK (priority::text = ANY (ARRAY['high'::character varying, 'normal'::character varying]::text[]))`
- `ck_stafftask_status`: `CHECK (status::text = ANY (ARRAY['open'::character varying, 'done'::character varying, 'cancelled'::character varying]::text[]))`

**Indexes**

- `ix_stafftask_org_status`: `btree (organization_id, status, due_date)`

**RLS policies**

- `ai_staff_tasks_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### ai_tenant_settings

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `organization_id` | uuid | no |  |
| `enabled_features` | character varying(40)[] | no | `'{}'::character varying[]` |
| `updated_by` | uuid | yes |  |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `ai_tenant_settings_pkey`: `PRIMARY KEY (organization_id)`

**Foreign keys**

- `ai_tenant_settings_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `ai_tenant_settings_updated_by_fkey`: `FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL`

**RLS policies**

- `ai_tenant_settings_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### alembic_version

- Row-level security: **disabled**
- Grants for hms_app: SELECT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `version_num` | character varying(32) | no |  |

**Primary key** `alembic_version_pkc`: `PRIMARY KEY (version_num)`

### appointments

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `provider_user_id` | uuid | yes |  |
| `starts_at` | timestamp with time zone | no |  |
| `ends_at` | timestamp with time zone | no |  |
| `reason` | character varying(300) | no | `''::character varying` |
| `status` | character varying(20) | no | `'scheduled'::character varying` |
| `notes` | text | no | `''::text` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `appointments_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `appointments_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `appointments_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `appointments_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `appointments_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`
- `appointments_provider_user_id_fkey`: `FOREIGN KEY (provider_user_id) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_appt_end_after_start`: `CHECK (ends_at > starts_at)`
- `ck_appt_status`: `CHECK (status::text = ANY (ARRAY['scheduled'::character varying, 'checked_in'::character varying, 'completed'::character varying, 'cancelled'::character varying, 'no_show'::character varying]::text[]))`

**Indexes**

- `ix_appt_org_patient`: `btree (organization_id, patient_id)`
- `ix_appt_org_provider_starts`: `btree (organization_id, provider_user_id, starts_at)`
- `ix_appt_org_starts`: `btree (organization_id, starts_at)`

**RLS policies**

- `appointments_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### audit_events

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | yes |  |
| `actor_user_id` | uuid | yes |  |
| `action` | character varying(80) | no |  |
| `resource_type` | character varying(60) | yes |  |
| `resource_id` | character varying(80) | yes |  |
| `metadata` | jsonb | no | `'{}'::jsonb` |
| `correlation_id` | character varying(64) | yes |  |
| `ip_address` | character varying(60) | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `audit_events_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `audit_events_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `audit_events_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL`

**Indexes**

- `ix_audit_action`: `btree (action)`
- `ix_audit_org_created`: `btree (organization_id, created_at)`

**RLS policies**

- `audit_insert` FOR INSERT TO public
  - WITH CHECK `((organization_id IS NULL) OR (organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid))`
- `audit_select` FOR SELECT TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_audit_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbids_audit_mutation()`

### auth_sessions

- Row-level security: **disabled**
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `family_id` | uuid | no |  |
| `user_id` | uuid | no |  |
| `organization_id` | uuid | no |  |
| `token_hash` | character varying(64) | no |  |
| `issued_at` | timestamp with time zone | no | `now()` |
| `expires_at` | timestamp with time zone | no |  |
| `revoked_at` | timestamp with time zone | yes |  |
| `replaced_by` | uuid | yes |  |
| `user_agent` | character varying(400) | yes |  |
| `ip_address` | character varying(60) | yes |  |
| `absolute_expires_at` | timestamp with time zone | yes |  |

**Primary key** `auth_sessions_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `auth_sessions_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `auth_sessions_user_id_fkey`: `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`

**Unique constraints**

- `auth_sessions_token_hash_key`: `UNIQUE (token_hash)`

**Indexes**

- `ix_auth_sessions_family`: `btree (family_id)`
- `ix_auth_sessions_user_org`: `btree (user_id, organization_id)`

### beds

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `ward_id` | uuid | no |  |
| `label` | character varying(30) | no |  |
| `status` | character varying(20) | no | `'available'::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `beds_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `beds_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `beds_ward_id_fkey`: `FOREIGN KEY (ward_id) REFERENCES wards(id) ON DELETE RESTRICT`

**Unique constraints**

- `uq_bed_org_ward_label`: `UNIQUE (organization_id, ward_id, label)`

**Check constraints**

- `ck_bed_status`: `CHECK (status::text = ANY (ARRAY['available'::character varying, 'maintenance'::character varying, 'blocked'::character varying]::text[]))`

**Indexes**

- `ix_beds_org_status`: `btree (organization_id, status)`
- `ix_beds_org_ward`: `btree (organization_id, ward_id)`

**RLS policies**

- `beds_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### branch_working_hours

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `weekday` | smallint | no |  |
| `opens_at` | time without time zone | no |  |
| `closes_at` | time without time zone | no |  |
| `break_starts_at` | time without time zone | yes |  |
| `break_ends_at` | time without time zone | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `branch_working_hours_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `branch_working_hours_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE`
- `branch_working_hours_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_bwh_session`: `UNIQUE (organization_id, branch_id, weekday, opens_at)`

**Check constraints**

- `ck_bwh_break`: `CHECK (break_starts_at IS NULL AND break_ends_at IS NULL OR break_starts_at IS NOT NULL AND break_ends_at IS NOT NULL AND opens_at < break_starts_at AND break_starts_at < break_ends_at AND break_ends_at < closes_at)`
- `ck_bwh_range`: `CHECK (opens_at < closes_at)`
- `ck_bwh_weekday`: `CHECK (weekday >= 0 AND weekday <= 6)`

**Indexes**

- `ix_bwh_org_branch`: `btree (organization_id, branch_id, weekday)`

**RLS policies**

- `branch_working_hours_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### branches

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `name` | character varying(200) | no |  |
| `code` | character varying(30) | no |  |
| `status` | character varying(20) | no | `'active'::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |
| `address` | character varying(300) | yes |  |
| `phone` | character varying(20) | yes |  |
| `gstin` | character varying(15) | yes |  |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `branches_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `branches_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_branch_org_code`: `UNIQUE (organization_id, code)`

**Check constraints**

- `ck_branch_gstin`: `CHECK (gstin IS NULL OR gstin::text ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'::text)`
- `ck_branch_status`: `CHECK (status::text = ANY (ARRAY['active'::character varying, 'inactive'::character varying]::text[]))`

**Indexes**

- `ix_branches_org_created`: `btree (organization_id, created_at)`

**RLS policies**

- `branch_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### checkin_tokens

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `appointment_id` | uuid | no |  |
| `token_hash` | character varying(64) | no |  |
| `expires_at` | timestamp with time zone | no |  |
| `used_at` | timestamp with time zone | yes |  |
| `used_by` | uuid | yes |  |
| `queue_entry_id` | uuid | yes |  |
| `revoked_at` | timestamp with time zone | yes |  |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `checkin_tokens_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `checkin_tokens_appointment_id_fkey`: `FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE`
- `checkin_tokens_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `checkin_tokens_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `checkin_tokens_queue_entry_id_fkey`: `FOREIGN KEY (queue_entry_id) REFERENCES opd_queue(id) ON DELETE SET NULL`
- `checkin_tokens_used_by_fkey`: `FOREIGN KEY (used_by) REFERENCES users(id) ON DELETE SET NULL`

**Unique constraints**

- `checkin_tokens_token_hash_key`: `UNIQUE (token_hash)`

**Check constraints**

- `ck_checkin_hash`: `CHECK (token_hash::text ~ '^[0-9a-f]{64}$'::text)`
- `ck_checkin_state`: `CHECK (used_at IS NULL OR revoked_at IS NULL)`

**Indexes**

- `ix_checkin_org_appt`: `btree (organization_id, appointment_id)`
- `uq_checkin_live_per_appt` (UNIQUE, partial): `btree (appointment_id)` WHERE `((used_at IS NULL) AND (revoked_at IS NULL))`
- `uq_checkin_used_per_appt` (UNIQUE, partial): `btree (appointment_id)` WHERE `(used_at IS NOT NULL)`

**RLS policies**

- `checkin_tokens_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### comms_consent_events

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `channel` | character varying(20) | no |  |
| `status` | character varying(12) | no |  |
| `source` | character varying(30) | no |  |
| `actor_user_id` | uuid | yes |  |
| `recorded_at` | timestamp with time zone | no | `now()` |

**Primary key** `comms_consent_events_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `comms_consent_events_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `comms_consent_events_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `comms_consent_events_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE`

**Check constraints**

- `ck_commsconsentev_channel`: `CHECK (channel::text = ANY (ARRAY['email'::character varying, 'sms'::character varying, 'whatsapp'::character varying]::text[]))`
- `ck_commsconsentev_status`: `CHECK (status::text = ANY (ARRAY['opted_in'::character varying, 'opted_out'::character varying]::text[]))`

**Indexes**

- `ix_commsconsentev_patient`: `btree (organization_id, patient_id, id)`

**RLS policies**

- `comms_consent_events_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_comms_consent_events_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_comms_log_mutation()`

### comms_consents

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `organization_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `channel` | character varying(20) | no |  |
| `status` | character varying(12) | no |  |
| `source` | character varying(30) | no |  |
| `actor_user_id` | uuid | yes |  |
| `recorded_at` | timestamp with time zone | no | `now()` |

**Primary key** `pk_comms_consents`: `PRIMARY KEY (organization_id, patient_id, channel)`

**Foreign keys**

- `comms_consents_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `comms_consents_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `comms_consents_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE`

**Check constraints**

- `ck_commsconsent_channel`: `CHECK (channel::text = ANY (ARRAY['email'::character varying, 'sms'::character varying, 'whatsapp'::character varying]::text[]))`
- `ck_commsconsent_status`: `CHECK (status::text = ANY (ARRAY['opted_in'::character varying, 'opted_out'::character varying]::text[]))`

**RLS policies**

- `comms_consents_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### comms_delivery_log

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `channel` | character varying(20) | no |  |
| `purpose` | character varying(30) | no |  |
| `language` | character varying(2) | yes |  |
| `template_id` | uuid | yes |  |
| `patient_id` | uuid | yes |  |
| `appointment_id` | uuid | yes |  |
| `follow_up_id` | uuid | yes |  |
| `recipient_masked` | character varying(64) | yes |  |
| `provider` | character varying(40) | no |  |
| `status` | character varying(25) | no |  |
| `cost_paise` | integer | no | `0` |
| `period` | character varying(7) | no |  |
| `dedupe_key` | character varying(200) | yes |  |
| `trigger` | character varying(20) | no | `'manual'::character varying` |
| `error` | character varying(300) | yes |  |
| `actor_user_id` | uuid | yes |  |
| `correlation_id` | character varying(64) | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `comms_delivery_log_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `comms_delivery_log_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `comms_delivery_log_appointment_id_fkey`: `FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL`
- `comms_delivery_log_follow_up_id_fkey`: `FOREIGN KEY (follow_up_id) REFERENCES follow_ups(id) ON DELETE SET NULL`
- `comms_delivery_log_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `comms_delivery_log_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL`
- `comms_delivery_log_template_id_fkey`: `FOREIGN KEY (template_id) REFERENCES comms_templates(id) ON DELETE SET NULL`

**Check constraints**

- `ck_commslog_channel`: `CHECK (channel::text = ANY (ARRAY['email'::character varying, 'sms'::character varying, 'whatsapp'::character varying]::text[]))`
- `ck_commslog_cost`: `CHECK (cost_paise >= 0)`
- `ck_commslog_period`: `CHECK (period::text ~ '^[0-9]{4}-[0-9]{2}$'::text)`
- `ck_commslog_purpose`: `CHECK (purpose::text = ANY (ARRAY['appointment_reminder'::character varying, 'follow_up'::character varying, 'missed_appointment'::character varying, 'generic'::character varying]::text[]))`
- `ck_commslog_status`: `CHECK (status::text = ANY (ARRAY['queued'::character varying, 'sent'::character varying, 'sent_mock'::character varying, 'suppressed'::character varying, 'failed'::character varying, 'skipped_no_consent'::character varying, 'skipped_quota'::character varying, 'skipped_quiet_hours'::character varying, 'skipped_no_recipient'::character varying, 'skipped_no_template'::character varying]::text[]))`
- `ck_commslog_trigger`: `CHECK (trigger::text = ANY (ARRAY['manual'::character varying, 'reminder_run'::character varying, 'scheduler'::character varying]::text[]))`

**Indexes**

- `ix_commslog_org_created`: `btree (organization_id, created_at)`
- `ix_commslog_org_period`: `btree (organization_id, period, channel)`
- `uq_commslog_dedupe` (UNIQUE, partial): `btree (organization_id, dedupe_key)` WHERE `((dedupe_key IS NOT NULL) AND ((status)::text = ANY ((ARRAY['queued'::character varying, 'sent'::character varying, 'sent_mock'::character varying, 'suppressed'::character varying])::text[])))`

**RLS policies**

- `comms_delivery_log_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_comms_delivery_log_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_comms_log_mutation()`

### comms_messages

- Row-level security: **disabled**
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `nextval('comms_messages_id_seq'::regclass)` |
| `channel` | character varying(20) | no |  |
| `provider` | character varying(40) | no |  |
| `recipient` | character varying(320) | no |  |
| `subject` | character varying(300) | no | `''::character varying` |
| `body` | text | no |  |
| `status` | character varying(20) | no |  |
| `error` | character varying(500) | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `comms_messages_pkey`: `PRIMARY KEY (id)`

**Check constraints**

- `ck_comms_channel`: `CHECK (channel::text = ANY (ARRAY['email'::character varying, 'sms'::character varying, 'whatsapp'::character varying]::text[]))`

**Indexes**

- `ix_comms_created`: `btree (created_at)`

### comms_patient_preferences

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `organization_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `preferred_language` | character varying(2) | yes |  |
| `email` | character varying(320) | yes |  |
| `updated_by` | uuid | yes |  |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `pk_comms_prefs`: `PRIMARY KEY (organization_id, patient_id)`

**Foreign keys**

- `comms_patient_preferences_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `comms_patient_preferences_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE`
- `comms_patient_preferences_updated_by_fkey`: `FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_commspref_language`: `CHECK (preferred_language IS NULL OR (preferred_language::text = ANY (ARRAY['en'::character varying, 'mr'::character varying, 'hi'::character varying]::text[])))`

**RLS policies**

- `comms_patient_preferences_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### comms_templates

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `channel` | character varying(20) | no |  |
| `purpose` | character varying(30) | no |  |
| `language` | character varying(2) | no |  |
| `name` | character varying(120) | no |  |
| `subject` | character varying(200) | no | `''::character varying` |
| `body` | character varying(2000) | no |  |
| `dlt_template_id` | character varying(40) | yes |  |
| `whatsapp_template_name` | character varying(120) | yes |  |
| `is_active` | boolean | no | `true` |
| `is_default` | boolean | no | `false` |
| `created_by` | uuid | yes |  |
| `updated_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `comms_templates_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `comms_templates_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `comms_templates_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `comms_templates_updated_by_fkey`: `FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_commstpl_channel`: `CHECK (channel::text = ANY (ARRAY['email'::character varying, 'sms'::character varying, 'whatsapp'::character varying]::text[]))`
- `ck_commstpl_dlt`: `CHECK (dlt_template_id IS NULL OR dlt_template_id::text ~ '^[0-9]{10,30}$'::text)`
- `ck_commstpl_language`: `CHECK (language::text = ANY (ARRAY['en'::character varying, 'mr'::character varying, 'hi'::character varying]::text[]))`
- `ck_commstpl_purpose`: `CHECK (purpose::text = ANY (ARRAY['appointment_reminder'::character varying, 'follow_up'::character varying, 'missed_appointment'::character varying, 'generic'::character varying]::text[]))`
- `ck_commstpl_wa`: `CHECK (whatsapp_template_name IS NULL OR whatsapp_template_name::text ~ '^[a-z0-9_]{1,120}$'::text)`

**Indexes**

- `ix_commstpl_org`: `btree (organization_id, channel)`
- `uq_commstpl_active` (UNIQUE, partial): `btree (organization_id, channel, purpose, language)` WHERE `is_active`

**RLS policies**

- `comms_templates_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### comms_tenant_settings

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `organization_id` | uuid | no |  |
| `monthly_spend_cap_paise` | bigint | yes |  |
| `quiet_start_hour` | smallint | no | `'21'::smallint` |
| `quiet_end_hour` | smallint | no | `'8'::smallint` |
| `reminder_hours_ahead` | smallint | no | `'24'::smallint` |
| `reminder_channels` | character varying(20)[] | no | `'{sms}'::character varying[]` |
| `updated_by` | uuid | yes |  |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `comms_tenant_settings_pkey`: `PRIMARY KEY (organization_id)`

**Foreign keys**

- `comms_tenant_settings_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `comms_tenant_settings_updated_by_fkey`: `FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_commsset_ahead`: `CHECK (reminder_hours_ahead >= 1 AND reminder_hours_ahead <= 168)`
- `ck_commsset_cap`: `CHECK (monthly_spend_cap_paise IS NULL OR monthly_spend_cap_paise >= 0)`
- `ck_commsset_channels`: `CHECK (reminder_channels <@ ARRAY['email'::character varying, 'sms'::character varying, 'whatsapp'::character varying])`
- `ck_commsset_quiet`: `CHECK (quiet_start_hour >= 0 AND quiet_start_hour <= 23 AND quiet_end_hour >= 0 AND quiet_end_hour <= 23)`

**RLS policies**

- `comms_tenant_settings_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### dispense_items

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `dispense_id` | uuid | no |  |
| `batch_id` | uuid | no |  |
| `drug_id` | uuid | no |  |
| `quantity` | integer | no |  |
| `unit_price` | numeric(12,2) | no | `'0'::numeric` |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `dispense_items_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `dispense_items_batch_id_fkey`: `FOREIGN KEY (batch_id) REFERENCES stock_batches(id) ON DELETE RESTRICT`
- `dispense_items_dispense_id_fkey`: `FOREIGN KEY (dispense_id) REFERENCES dispenses(id) ON DELETE CASCADE`
- `dispense_items_drug_id_fkey`: `FOREIGN KEY (drug_id) REFERENCES drug_catalog(id) ON DELETE RESTRICT`
- `dispense_items_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_dispitem_price_nonneg`: `CHECK (unit_price >= 0::numeric)`
- `ck_dispitem_qty_positive`: `CHECK (quantity > 0)`

**Indexes**

- `ix_dispitem_org_batch`: `btree (organization_id, batch_id)`
- `ix_dispitem_org_dispense`: `btree (organization_id, dispense_id)`

**RLS policies**

- `dispense_items_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_dispense_item_immutable`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_dispense_mutation()`

### dispenses

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `prescription_id` | uuid | yes |  |
| `patient_id` | uuid | yes |  |
| `notes` | character varying(500) | no | `''::character varying` |
| `dispensed_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `dispenses_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `dispenses_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `dispenses_dispensed_by_fkey`: `FOREIGN KEY (dispensed_by) REFERENCES users(id) ON DELETE SET NULL`
- `dispenses_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `dispenses_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`
- `dispenses_prescription_id_fkey`: `FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_dispense_has_subject`: `CHECK (prescription_id IS NOT NULL OR patient_id IS NOT NULL)`

**Indexes**

- `ix_dispenses_org_created`: `btree (organization_id, created_at)`
- `ix_dispenses_org_rx`: `btree (organization_id, prescription_id)`

**RLS policies**

- `dispenses_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_dispense_immutable`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_dispense_mutation()`

### drug_catalog

- Row-level security: **disabled**
- Grants for hms_app: SELECT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `generic_name` | character varying(200) | no |  |
| `brand_hint` | character varying(200) | no | `''::character varying` |
| `drug_class` | character varying(100) | no | `''::character varying` |
| `allergy_terms` | character varying(300) | no | `''::character varying` |
| `is_active` | boolean | no | `true` |

**Primary key** `drug_catalog_pkey`: `PRIMARY KEY (id)`

**Unique constraints**

- `drug_catalog_generic_name_key`: `UNIQUE (generic_name)`

### encounter_diagnoses

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `encounter_id` | uuid | no |  |
| `code` | character varying(20) | no |  |
| `label` | character varying(300) | no |  |
| `kind` | character varying(20) | no | `'primary'::character varying` |
| `status` | character varying(20) | no | `'confirmed'::character varying` |
| `recorded_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `encounter_diagnoses_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `encounter_diagnoses_encounter_id_fkey`: `FOREIGN KEY (encounter_id) REFERENCES encounters(id) ON DELETE CASCADE`
- `encounter_diagnoses_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `encounter_diagnoses_recorded_by_fkey`: `FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_dx_kind`: `CHECK (kind::text = ANY (ARRAY['primary'::character varying, 'secondary'::character varying]::text[]))`
- `ck_dx_status`: `CHECK (status::text = ANY (ARRAY['suspected'::character varying, 'confirmed'::character varying, 'ruled_out'::character varying]::text[]))`

**Indexes**

- `ix_dx_org_enc`: `btree (organization_id, encounter_id)`

**RLS policies**

- `encounter_diagnoses_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### encounter_vitals

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `encounter_id` | uuid | no |  |
| `bp_systolic` | integer | yes |  |
| `bp_diastolic` | integer | yes |  |
| `pulse` | integer | yes |  |
| `temperature_c` | numeric(4,1) | yes |  |
| `spo2` | integer | yes |  |
| `respiratory_rate` | integer | yes |  |
| `weight_kg` | numeric(5,2) | yes |  |
| `height_cm` | numeric(5,1) | yes |  |
| `notes` | character varying(500) | no | `''::character varying` |
| `recorded_by` | uuid | yes |  |
| `recorded_at` | timestamp with time zone | no | `now()` |

**Primary key** `encounter_vitals_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `encounter_vitals_encounter_id_fkey`: `FOREIGN KEY (encounter_id) REFERENCES encounters(id) ON DELETE CASCADE`
- `encounter_vitals_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `encounter_vitals_recorded_by_fkey`: `FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_vitals_bp_pair`: `CHECK (bp_systolic IS NULL OR bp_diastolic IS NULL OR bp_systolic > bp_diastolic)`
- `ck_vitals_dia`: `CHECK (bp_diastolic IS NULL OR bp_diastolic >= 20 AND bp_diastolic <= 200)`
- `ck_vitals_height`: `CHECK (height_cm IS NULL OR height_cm >= 30::numeric AND height_cm <= 260::numeric)`
- `ck_vitals_pulse`: `CHECK (pulse IS NULL OR pulse >= 20 AND pulse <= 250)`
- `ck_vitals_rr`: `CHECK (respiratory_rate IS NULL OR respiratory_rate >= 5 AND respiratory_rate <= 80)`
- `ck_vitals_spo2`: `CHECK (spo2 IS NULL OR spo2 >= 40 AND spo2 <= 100)`
- `ck_vitals_sys`: `CHECK (bp_systolic IS NULL OR bp_systolic >= 40 AND bp_systolic <= 300)`
- `ck_vitals_temp`: `CHECK (temperature_c IS NULL OR temperature_c >= 30::numeric AND temperature_c <= 45::numeric)`
- `ck_vitals_weight`: `CHECK (weight_kg IS NULL OR weight_kg >= 0.5 AND weight_kg <= 400::numeric)`

**Indexes**

- `ix_vitals_org_enc`: `btree (organization_id, encounter_id)`

**RLS policies**

- `encounter_vitals_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### encounters

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `appointment_id` | uuid | yes |  |
| `queue_entry_id` | uuid | yes |  |
| `provider_user_id` | uuid | yes |  |
| `chief_complaint` | character varying(500) | no | `''::character varying` |
| `history` | text | no | `''::text` |
| `examination` | text | no | `''::text` |
| `assessment` | text | no | `''::text` |
| `plan` | text | no | `''::text` |
| `status` | character varying(20) | no | `'open'::character varying` |
| `started_at` | timestamp with time zone | no | `now()` |
| `ended_at` | timestamp with time zone | yes |  |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `encounters_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `encounters_appointment_id_fkey`: `FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL`
- `encounters_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `encounters_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `encounters_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `encounters_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`
- `encounters_provider_user_id_fkey`: `FOREIGN KEY (provider_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `encounters_queue_entry_id_fkey`: `FOREIGN KEY (queue_entry_id) REFERENCES opd_queue(id) ON DELETE SET NULL`

**Check constraints**

- `ck_enc_status`: `CHECK (status::text = ANY (ARRAY['open'::character varying, 'completed'::character varying]::text[]))`

**Indexes**

- `ix_enc_org_patient`: `btree (organization_id, patient_id)`
- `ix_enc_org_status`: `btree (organization_id, status)`
- `uq_enc_one_open` (UNIQUE, partial): `btree (organization_id, patient_id)` WHERE `((status)::text = 'open'::text)`

**RLS policies**

- `encounters_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_enc_completed_immutable`: BEFORE UPDATE FOR EACH ROW -> `forbid_closed_encounter()`
- `trg_enc_completed_no_delete`: BEFORE DELETE FOR EACH ROW -> `forbid_completed_encounter_delete()`

### expenses

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | yes |  |
| `category` | character varying(30) | no |  |
| `amount` | numeric(12,2) | no |  |
| `expense_date` | date | no |  |
| `description` | character varying(500) | no | `''::character varying` |
| `reference` | character varying(100) | no | `''::character varying` |
| `status` | character varying(20) | no | `'recorded'::character varying` |
| `void_reason` | character varying(300) | no | `''::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `expenses_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `expenses_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE SET NULL`
- `expenses_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `expenses_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_expense_amount_positive`: `CHECK (amount > 0::numeric)`
- `ck_expense_category`: `CHECK (category::text = ANY (ARRAY['rent'::character varying, 'salaries'::character varying, 'utilities'::character varying, 'supplies'::character varying, 'equipment'::character varying, 'maintenance'::character varying, 'service'::character varying, 'transport'::character varying, 'marketing'::character varying, 'other'::character varying]::text[]))`
- `ck_expense_status`: `CHECK (status::text = ANY (ARRAY['recorded'::character varying, 'void'::character varying]::text[]))`

**Indexes**

- `ix_expense_org_category`: `btree (organization_id, category)`
- `ix_expense_org_date`: `btree (organization_id, expense_date)`

**RLS policies**

- `expenses_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_expense_immutable`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_expense_mutation()`

### fee_schedule

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `provider_user_id` | uuid | yes |  |
| `consultation_fee` | numeric(12,2) | no |  |
| `follow_up_fee` | numeric(12,2) | yes |  |
| `follow_up_valid_days` | integer | yes |  |
| `updated_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `fee_schedule_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `fee_schedule_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `fee_schedule_provider_user_id_fkey`: `FOREIGN KEY (provider_user_id) REFERENCES users(id) ON DELETE CASCADE`
- `fee_schedule_updated_by_fkey`: `FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_fee_consultation`: `CHECK (consultation_fee >= 0::numeric AND consultation_fee <= 1000000::numeric)`
- `ck_fee_follow_up`: `CHECK (follow_up_fee IS NULL OR follow_up_fee >= 0::numeric AND follow_up_fee <= 1000000::numeric)`
- `ck_fee_follow_up_days`: `CHECK (follow_up_valid_days IS NULL OR follow_up_valid_days >= 0 AND follow_up_valid_days <= 365)`

**Indexes**

- `uq_fee_org_provider` (UNIQUE): `btree (organization_id, COALESCE(provider_user_id, '00000000-0000-0000-0000-000000000000'::uuid))`

**RLS policies**

- `fee_schedule_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### follow_ups

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `branch_id` | uuid | yes |  |
| `due_date` | date | no |  |
| `reason` | character varying(80) | no |  |
| `status` | character varying(12) | no | `'planned'::character varying` |
| `assigned_user_id` | uuid | yes |  |
| `created_by` | uuid | yes |  |
| `appointment_id` | uuid | yes |  |
| `status_note` | character varying(200) | no | `''::character varying` |
| `reminded_at` | timestamp with time zone | yes |  |
| `closed_at` | timestamp with time zone | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `follow_ups_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `follow_ups_appointment_id_fkey`: `FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL`
- `follow_ups_assigned_user_id_fkey`: `FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `follow_ups_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE SET NULL`
- `follow_ups_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `follow_ups_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `follow_ups_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_followup_booked_has_appt`: `CHECK (status::text <> 'booked'::text OR appointment_id IS NOT NULL)`
- `ck_followup_status`: `CHECK (status::text = ANY (ARRAY['planned'::character varying, 'reminded'::character varying, 'booked'::character varying, 'completed'::character varying, 'missed'::character varying, 'cancelled'::character varying]::text[]))`

**Indexes**

- `ix_followup_org_due`: `btree (organization_id, status, due_date)`
- `ix_followup_org_patient`: `btree (organization_id, patient_id)`

**RLS policies**

- `follow_ups_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### idempotency_keys

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `idempotency_key` | character varying(100) | no |  |
| `endpoint` | character varying(120) | no |  |
| `request_hash` | character varying(64) | no |  |
| `response_status` | integer | no |  |
| `response_body` | jsonb | no |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `idempotency_keys_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `idempotency_keys_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_idem_org_key`: `UNIQUE (organization_id, idempotency_key)`

**Indexes**

- `ix_idem_org_created`: `btree (organization_id, created_at)`

**RLS policies**

- `idempotency_keys_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### inventory_items

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `name` | character varying(120) | no |  |
| `sku` | character varying(60) | no | `''::character varying` |
| `unit` | character varying(30) | no | `'pcs'::character varying` |
| `quantity_on_hand` | integer | no | `0` |
| `reorder_level` | integer | no | `0` |
| `unit_cost` | numeric(12,2) | no | `'0'::numeric` |
| `status` | character varying(20) | no | `'active'::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `inventory_items_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `inventory_items_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `inventory_items_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_invitem_org_branch_name`: `UNIQUE (organization_id, branch_id, name)`

**Check constraints**

- `ck_invitem_cost_nonneg`: `CHECK (unit_cost >= 0::numeric)`
- `ck_invitem_on_hand_nonneg`: `CHECK (quantity_on_hand >= 0)`
- `ck_invitem_reorder_nonneg`: `CHECK (reorder_level >= 0)`
- `ck_invitem_status`: `CHECK (status::text = ANY (ARRAY['active'::character varying, 'retired'::character varying]::text[]))`

**Indexes**

- `ix_invitem_org_branch`: `btree (organization_id, branch_id)`

**RLS policies**

- `inventory_items_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### inventory_movements

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `item_id` | uuid | no |  |
| `movement_type` | character varying(20) | no |  |
| `direction` | character varying(4) | no |  |
| `quantity` | integer | no |  |
| `reason` | character varying(300) | no | `''::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `inventory_movements_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `inventory_movements_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `inventory_movements_item_id_fkey`: `FOREIGN KEY (item_id) REFERENCES inventory_items(id) ON DELETE RESTRICT`
- `inventory_movements_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_invmovement_direction`: `CHECK (direction::text = ANY (ARRAY['in'::character varying, 'out'::character varying]::text[]))`
- `ck_invmovement_qty_positive`: `CHECK (quantity > 0)`
- `ck_invmovement_type`: `CHECK (movement_type::text = ANY (ARRAY['receive'::character varying, 'issue'::character varying, 'adjustment'::character varying, 'return'::character varying]::text[]))`

**Indexes**

- `ix_invmovement_org_item`: `btree (organization_id, item_id, id)`

**RLS policies**

- `inventory_movements_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_inventory_movement_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_append_only_mutation()`
- `trg_inventory_movement_apply`: BEFORE INSERT FOR EACH ROW -> `apply_inventory_movement()`

### invoice_items

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `invoice_id` | uuid | no |  |
| `item_type` | character varying(30) | no |  |
| `description` | character varying(300) | no |  |
| `quantity` | integer | no | `1` |
| `unit_price` | numeric(12,2) | no |  |
| `tax_rate` | numeric(5,2) | no | `'0'::numeric` |
| `line_total` | numeric(12,2) | no |  |
| `seq` | integer | no | `0` |

**Primary key** `invoice_items_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `invoice_items_invoice_id_fkey`: `FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE`
- `invoice_items_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_invitem_amounts`: `CHECK (quantity > 0 AND unit_price >= 0::numeric AND tax_rate >= 0::numeric AND line_total >= 0::numeric)`
- `ck_invitem_type`: `CHECK (item_type::text = ANY (ARRAY['consultation'::character varying, 'procedure'::character varying, 'pharmacy'::character varying, 'lab'::character varying, 'other'::character varying]::text[]))`

**Indexes**

- `ix_invitem_org_inv`: `btree (organization_id, invoice_id)`

**RLS policies**

- `invoice_items_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_invitem_frozen`: BEFORE INSERT OR UPDATE OR DELETE FOR EACH ROW -> `forbid_issued_item_change()`

### invoices

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `encounter_id` | uuid | yes |  |
| `invoice_number` | character varying(20) | no |  |
| `status` | character varying(20) | no | `'draft'::character varying` |
| `subtotal` | numeric(12,2) | no | `'0'::numeric` |
| `discount` | numeric(12,2) | no | `'0'::numeric` |
| `tax_total` | numeric(12,2) | no | `'0'::numeric` |
| `total` | numeric(12,2) | no | `'0'::numeric` |
| `amount_paid` | numeric(12,2) | no | `'0'::numeric` |
| `notes` | character varying(500) | no | `''::character varying` |
| `issued_at` | timestamp with time zone | yes |  |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `invoices_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `invoices_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `invoices_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `invoices_encounter_id_fkey`: `FOREIGN KEY (encounter_id) REFERENCES encounters(id) ON DELETE SET NULL`
- `invoices_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `invoices_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`

**Unique constraints**

- `uq_invoice_org_number`: `UNIQUE (organization_id, invoice_number)`

**Check constraints**

- `ck_inv_amount_paid_bound`: `CHECK (amount_paid >= 0::numeric AND amount_paid <= total)`
- `ck_inv_amounts_nonneg`: `CHECK (subtotal >= 0::numeric AND discount >= 0::numeric AND tax_total >= 0::numeric AND total >= 0::numeric AND amount_paid >= 0::numeric)`
- `ck_inv_discount_bound`: `CHECK (discount <= subtotal)`
- `ck_inv_status`: `CHECK (status::text = ANY (ARRAY['draft'::character varying, 'issued'::character varying, 'paid'::character varying, 'void'::character varying]::text[]))`

**Indexes**

- `ix_inv_org_patient`: `btree (organization_id, patient_id)`
- `ix_inv_org_status`: `btree (organization_id, status)`

**RLS policies**

- `invoices_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_inv_issued_frozen`: BEFORE UPDATE FOR EACH ROW -> `forbid_issued_invoice_change()`
- `trg_inv_status_forward`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_invoice_regression()`

### kb_chunks

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `document_id` | uuid | no |  |
| `ordinal` | integer | no |  |
| `section` | character varying(300) | no | `''::character varying` |
| `text` | text | no |  |
| `tokens` | text[] | no | `'{}'::text[]` |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `kb_chunks_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `kb_chunks_document_id_fkey`: `FOREIGN KEY (document_id) REFERENCES kb_documents(id) ON DELETE RESTRICT`
- `kb_chunks_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_kbchunk_doc_ord`: `UNIQUE (document_id, ordinal)`

**Indexes**

- `ix_kbchunk_org_doc`: `btree (organization_id, document_id)`

**RLS policies**

- `kb_chunks_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_kb_chunks_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_ai_log_mutation()`

### kb_documents

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `title` | character varying(200) | no |  |
| `doc_type` | character varying(20) | no |  |
| `language` | character varying(5) | no |  |
| `version` | integer | no | `1` |
| `status` | character varying(20) | no | `'draft'::character varying` |
| `visibility_roles` | character varying(40)[] | no | `'{}'::character varying[]` |
| `body` | text | no |  |
| `sha256` | character varying(64) | no |  |
| `injection_flags` | integer | no | `0` |
| `chunk_count` | integer | no | `0` |
| `uploaded_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `approved_by` | uuid | yes |  |
| `approved_at` | timestamp with time zone | yes |  |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `kb_documents_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `kb_documents_approved_by_fkey`: `FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL`
- `kb_documents_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `kb_documents_uploaded_by_fkey`: `FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL`

**Unique constraints**

- `uq_kbdoc_title_ver`: `UNIQUE (organization_id, title, version)`

**Check constraints**

- `ck_kbdoc_lang`: `CHECK (language::text = ANY (ARRAY['en'::character varying, 'mr'::character varying, 'hi'::character varying, 'mixed'::character varying]::text[]))`
- `ck_kbdoc_size`: `CHECK (length(body) <= 200000)`
- `ck_kbdoc_status`: `CHECK (status::text = ANY (ARRAY['draft'::character varying, 'approved'::character varying, 'superseded'::character varying, 'archived'::character varying]::text[]))`
- `ck_kbdoc_type`: `CHECK (doc_type::text = ANY (ARRAY['sop'::character varying, 'manual'::character varying, 'policy'::character varying, 'training'::character varying, 'other'::character varying]::text[]))`

**Indexes**

- `ix_kbdoc_org_status`: `btree (organization_id, status)`

**RLS policies**

- `kb_documents_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_kb_documents_guard`: BEFORE UPDATE FOR EACH ROW -> `guard_kb_document()`

### lab_order_items

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `order_id` | uuid | no |  |
| `test_id` | uuid | no |  |
| `status` | character varying(20) | no | `'ordered'::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `lab_order_items_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `lab_order_items_order_id_fkey`: `FOREIGN KEY (order_id) REFERENCES lab_orders(id) ON DELETE CASCADE`
- `lab_order_items_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `lab_order_items_test_id_fkey`: `FOREIGN KEY (test_id) REFERENCES lab_test_catalog(id) ON DELETE RESTRICT`

**Unique constraints**

- `uq_laborderitem_test`: `UNIQUE (order_id, test_id)`

**Check constraints**

- `ck_laborderitem_status`: `CHECK (status::text = ANY (ARRAY['ordered'::character varying, 'resulted'::character varying, 'cancelled'::character varying]::text[]))`

**Indexes**

- `ix_laborderitem_org_order`: `btree (organization_id, order_id)`

**RLS policies**

- `lab_order_items_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_laborderitem_guard`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_laborderitem_mutation()`

### lab_orders

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `encounter_id` | uuid | yes |  |
| `branch_id` | uuid | no |  |
| `status` | character varying(20) | no | `'ordered'::character varying` |
| `priority` | character varying(10) | no | `'routine'::character varying` |
| `clinical_notes` | text | no | `''::text` |
| `cancel_reason` | character varying(300) | no | `''::character varying` |
| `ordered_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `lab_orders_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `lab_orders_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `lab_orders_encounter_id_fkey`: `FOREIGN KEY (encounter_id) REFERENCES encounters(id) ON DELETE SET NULL`
- `lab_orders_ordered_by_fkey`: `FOREIGN KEY (ordered_by) REFERENCES users(id) ON DELETE SET NULL`
- `lab_orders_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `lab_orders_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_laborder_priority`: `CHECK (priority::text = ANY (ARRAY['routine'::character varying, 'urgent'::character varying]::text[]))`
- `ck_laborder_status`: `CHECK (status::text = ANY (ARRAY['ordered'::character varying, 'specimen_collected'::character varying, 'in_progress'::character varying, 'released'::character varying, 'cancelled'::character varying]::text[]))`

**Indexes**

- `ix_laborder_org_patient`: `btree (organization_id, patient_id)`
- `ix_laborder_org_status`: `btree (organization_id, status)`

**RLS policies**

- `lab_orders_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_laborder_frozen`: BEFORE UPDATE FOR EACH ROW -> `forbid_closed_laborder()`
- `trg_laborder_release_complete`: BEFORE UPDATE FOR EACH ROW -> `check_laborder_release()`

### lab_results

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `order_id` | uuid | no |  |
| `test_id` | uuid | no |  |
| `specimen_id` | uuid | yes |  |
| `value_text` | character varying(200) | no | `''::character varying` |
| `value_numeric` | numeric(14,3) | yes |  |
| `unit` | character varying(40) | no | `''::character varying` |
| `reference_range` | character varying(120) | no | `''::character varying` |
| `flag` | character varying(20) | no | `'normal'::character varying` |
| `status` | character varying(20) | no | `'imported'::character varying` |
| `superseded_by_id` | uuid | yes |  |
| `amendment_reason` | character varying(300) | no | `''::character varying` |
| `imported_by` | uuid | yes |  |
| `verified_by` | uuid | yes |  |
| `verified_at` | timestamp with time zone | yes |  |
| `released_by` | uuid | yes |  |
| `released_at` | timestamp with time zone | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `lab_results_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `lab_results_imported_by_fkey`: `FOREIGN KEY (imported_by) REFERENCES users(id) ON DELETE SET NULL`
- `lab_results_order_id_fkey`: `FOREIGN KEY (order_id) REFERENCES lab_orders(id) ON DELETE CASCADE`
- `lab_results_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `lab_results_released_by_fkey`: `FOREIGN KEY (released_by) REFERENCES users(id) ON DELETE SET NULL`
- `lab_results_specimen_id_fkey`: `FOREIGN KEY (specimen_id) REFERENCES lab_specimens(id) ON DELETE SET NULL`
- `lab_results_superseded_by_id_fkey`: `FOREIGN KEY (superseded_by_id) REFERENCES lab_results(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED`
- `lab_results_test_id_fkey`: `FOREIGN KEY (test_id) REFERENCES lab_test_catalog(id) ON DELETE RESTRICT`
- `lab_results_verified_by_fkey`: `FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_labresult_flag`: `CHECK (flag::text = ANY (ARRAY['normal'::character varying, 'low'::character varying, 'high'::character varying, 'abnormal'::character varying, 'critical'::character varying]::text[]))`
- `ck_labresult_status`: `CHECK (status::text = ANY (ARRAY['imported'::character varying, 'verified'::character varying, 'released'::character varying, 'superseded'::character varying]::text[]))`

**Indexes**

- `ix_labresult_org_order`: `btree (organization_id, order_id)`
- `ix_labresult_org_status`: `btree (organization_id, status)`
- `uq_labresult_live_per_test` (UNIQUE, partial): `btree (order_id, test_id)` WHERE `((status)::text <> 'superseded'::text)`

**RLS policies**

- `lab_results_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_labresult_immutable`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_labresult_mutation()`

### lab_specimens

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `order_id` | uuid | no |  |
| `barcode` | character varying(20) | no |  |
| `specimen_type` | character varying(30) | no |  |
| `status` | character varying(20) | no | `'collected'::character varying` |
| `rejection_reason` | character varying(300) | no | `''::character varying` |
| `collected_at` | timestamp with time zone | no | `now()` |
| `collected_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `lab_specimens_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `lab_specimens_collected_by_fkey`: `FOREIGN KEY (collected_by) REFERENCES users(id) ON DELETE SET NULL`
- `lab_specimens_order_id_fkey`: `FOREIGN KEY (order_id) REFERENCES lab_orders(id) ON DELETE CASCADE`
- `lab_specimens_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_specimen_org_barcode`: `UNIQUE (organization_id, barcode)`

**Check constraints**

- `ck_specimen_status`: `CHECK (status::text = ANY (ARRAY['collected'::character varying, 'rejected'::character varying]::text[]))`
- `ck_specimen_type`: `CHECK (specimen_type::text = ANY (ARRAY['blood'::character varying, 'urine'::character varying, 'stool'::character varying, 'swab'::character varying, 'sputum'::character varying, 'tissue'::character varying, 'other'::character varying]::text[]))`

**Indexes**

- `ix_specimen_org_order`: `btree (organization_id, order_id)`

**RLS policies**

- `lab_specimens_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_specimen_immutable`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_specimen_mutation()`

### lab_test_catalog

- Row-level security: **disabled**
- Grants for hms_app: SELECT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `code` | character varying(30) | no |  |
| `name` | character varying(200) | no |  |
| `specimen_type` | character varying(30) | no |  |
| `unit` | character varying(40) | no | `''::character varying` |
| `reference_range` | character varying(120) | no | `''::character varying` |
| `is_active` | boolean | no | `true` |

**Primary key** `lab_test_catalog_pkey`: `PRIMARY KEY (id)`

**Unique constraints**

- `lab_test_catalog_code_key`: `UNIQUE (code)`

### ledger_entries

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `invoice_id` | uuid | no |  |
| `payment_id` | uuid | yes |  |
| `refund_id` | uuid | yes |  |
| `entry_type` | character varying(30) | no |  |
| `direction` | character varying(10) | no |  |
| `amount` | numeric(12,2) | no |  |
| `description` | character varying(300) | no |  |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `ledger_entries_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `ledger_entries_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `ledger_entries_invoice_id_fkey`: `FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE RESTRICT`
- `ledger_entries_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `ledger_entries_payment_id_fkey`: `FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE SET NULL`
- `ledger_entries_refund_id_fkey`: `FOREIGN KEY (refund_id) REFERENCES refunds(id) ON DELETE SET NULL`

**Check constraints**

- `ck_ledger_amount_positive`: `CHECK (amount > 0::numeric)`
- `ck_ledger_direction`: `CHECK (direction::text = ANY (ARRAY['debit'::character varying, 'credit'::character varying]::text[]))`
- `ck_ledger_type`: `CHECK (entry_type::text = ANY (ARRAY['charge'::character varying, 'payment'::character varying, 'refund'::character varying, 'adjustment'::character varying]::text[]))`

**Indexes**

- `ix_ledger_org_invoice`: `btree (organization_id, invoice_id, id)`
- `uq_ledger_charge_per_invoice` (UNIQUE, partial): `btree (invoice_id)` WHERE `((entry_type)::text = 'charge'::text)`
- `uq_ledger_payment_once` (UNIQUE, partial): `btree (payment_id)` WHERE `((payment_id IS NOT NULL) AND ((entry_type)::text = 'payment'::text))`
- `uq_ledger_refund_once` (UNIQUE, partial): `btree (refund_id)` WHERE `((refund_id IS NOT NULL) AND ((entry_type)::text = 'refund'::text))`
- `uq_ledger_void_per_invoice` (UNIQUE, partial): `btree (invoice_id)` WHERE `((entry_type)::text = 'adjustment'::text)`

**RLS policies**

- `ledger_entries_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_ledger_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_ledger_mutation()`

### member_invitations

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `email` | character varying(320) | no |  |
| `role_id` | uuid | no |  |
| `branch_id` | uuid | yes |  |
| `token_hash` | character varying(64) | no |  |
| `status` | character varying(20) | no | `'pending'::character varying` |
| `invited_by_user_id` | uuid | yes |  |
| `accepted_user_id` | uuid | yes |  |
| `expires_at` | timestamp with time zone | no |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `member_invitations_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `member_invitations_accepted_user_id_fkey`: `FOREIGN KEY (accepted_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `member_invitations_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE SET NULL`
- `member_invitations_invited_by_user_id_fkey`: `FOREIGN KEY (invited_by_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `member_invitations_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `member_invitations_role_id_fkey`: `FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT`

**Unique constraints**

- `member_invitations_token_hash_key`: `UNIQUE (token_hash)`

**Check constraints**

- `ck_invitation_status`: `CHECK (status::text = ANY (ARRAY['pending'::character varying, 'accepted'::character varying, 'revoked'::character varying]::text[]))`

**Indexes**

- `ix_invitation_org_status`: `btree (organization_id, status)`

**RLS policies**

- `invitation_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### memberships

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `user_id` | uuid | no |  |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | yes |  |
| `role_id` | uuid | no |  |
| `status` | character varying(20) | no | `'active'::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `memberships_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `memberships_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE SET NULL`
- `memberships_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `memberships_role_id_fkey`: `FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT`
- `memberships_user_id_fkey`: `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_membership_user_org`: `UNIQUE (user_id, organization_id)`

**Check constraints**

- `ck_membership_status`: `CHECK (status::text = ANY (ARRAY['active'::character varying, 'suspended'::character varying]::text[]))`

**Indexes**

- `ix_memberships_org`: `btree (organization_id)`

**RLS policies**

- `membership_delete` FOR DELETE TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
- `membership_insert` FOR INSERT TO public
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
- `membership_select` FOR SELECT TO public
  - USING `((user_id = (NULLIF(current_setting('app.current_user_id'::text, true), ''::text))::uuid) OR (organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid))`
- `membership_update` FOR UPDATE TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### mfa_recovery_codes

- Row-level security: **disabled**
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `user_id` | uuid | no |  |
| `code_hash` | character varying(64) | no |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `used_at` | timestamp with time zone | yes |  |

**Primary key** `mfa_recovery_codes_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `mfa_recovery_codes_user_id_fkey`: `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`

**Unique constraints**

- `mfa_recovery_codes_code_hash_key`: `UNIQUE (code_hash)`

**Indexes**

- `ix_mfa_recovery_user`: `btree (user_id)`

### nursing_records

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `admission_id` | uuid | no |  |
| `note_type` | character varying(20) | no | `'note'::character varying` |
| `note` | text | no | `''::text` |
| `bp_systolic` | integer | yes |  |
| `bp_diastolic` | integer | yes |  |
| `pulse` | integer | yes |  |
| `respiratory_rate` | integer | yes |  |
| `temperature_c` | numeric(4,1) | yes |  |
| `spo2` | integer | yes |  |
| `recorded_at` | timestamp with time zone | no | `now()` |
| `recorded_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `nursing_records_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `nursing_records_admission_id_fkey`: `FOREIGN KEY (admission_id) REFERENCES admissions(id) ON DELETE RESTRICT`
- `nursing_records_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `nursing_records_recorded_by_fkey`: `FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_nursing_bp_order`: `CHECK (bp_systolic IS NULL OR bp_diastolic IS NULL OR bp_systolic > bp_diastolic)`
- `ck_nursing_diastolic`: `CHECK (bp_diastolic IS NULL OR bp_diastolic >= 20 AND bp_diastolic <= 200)`
- `ck_nursing_has_content`: `CHECK (note <> ''::text OR bp_systolic IS NOT NULL OR pulse IS NOT NULL OR temperature_c IS NOT NULL OR spo2 IS NOT NULL)`
- `ck_nursing_note_type`: `CHECK (note_type::text = ANY (ARRAY['vitals'::character varying, 'note'::character varying, 'intake_output'::character varying, 'care'::character varying]::text[]))`
- `ck_nursing_pulse`: `CHECK (pulse IS NULL OR pulse >= 20 AND pulse <= 250)`
- `ck_nursing_rr`: `CHECK (respiratory_rate IS NULL OR respiratory_rate >= 5 AND respiratory_rate <= 80)`
- `ck_nursing_spo2`: `CHECK (spo2 IS NULL OR spo2 >= 50 AND spo2 <= 100)`
- `ck_nursing_systolic`: `CHECK (bp_systolic IS NULL OR bp_systolic >= 40 AND bp_systolic <= 300)`
- `ck_nursing_temp`: `CHECK (temperature_c IS NULL OR temperature_c >= 30::numeric AND temperature_c <= 45::numeric)`

**Indexes**

- `ix_nursing_org_admission`: `btree (organization_id, admission_id, recorded_at)`

**RLS policies**

- `nursing_records_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_nursing_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_append_only_mutation()`
- `trg_nursing_check_admission`: BEFORE INSERT FOR EACH ROW -> `check_nursing_admission()`

### opd_queue

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `appointment_id` | uuid | yes |  |
| `service_date` | date | no |  |
| `token_number` | integer | no |  |
| `status` | character varying(20) | no | `'waiting'::character varying` |
| `priority` | character varying(20) | no | `'normal'::character varying` |
| `doctor_user_id` | uuid | yes |  |
| `called_at` | timestamp with time zone | yes |  |
| `started_at` | timestamp with time zone | yes |  |
| `completed_at` | timestamp with time zone | yes |  |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `opd_queue_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `opd_queue_appointment_id_fkey`: `FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL`
- `opd_queue_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `opd_queue_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `opd_queue_doctor_user_id_fkey`: `FOREIGN KEY (doctor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `opd_queue_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `opd_queue_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`

**Unique constraints**

- `uq_queue_org_date_token`: `UNIQUE (organization_id, service_date, token_number)`

**Check constraints**

- `ck_queue_priority`: `CHECK (priority::text = ANY (ARRAY['normal'::character varying, 'urgent'::character varying]::text[]))`
- `ck_queue_status`: `CHECK (status::text = ANY (ARRAY['waiting'::character varying, 'called'::character varying, 'in_consultation'::character varying, 'completed'::character varying, 'skipped'::character varying, 'cancelled'::character varying]::text[]))`
- `ck_queue_token_positive`: `CHECK (token_number > 0)`

**Indexes**

- `ix_queue_org_date`: `btree (organization_id, service_date)`
- `ix_queue_org_status`: `btree (organization_id, status)`
- `uq_queue_one_active` (UNIQUE, partial): `btree (organization_id, patient_id, service_date)` WHERE `((status)::text = ANY ((ARRAY['waiting'::character varying, 'called'::character varying, 'in_consultation'::character varying])::text[]))`

**RLS policies**

- `opd_queue_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### org_settings

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `organization_id` | uuid | no |  |
| `schema_version` | integer | no | `1` |
| `settings` | jsonb | no | `'{}'::jsonb` |
| `wizard` | jsonb | no | `'{}'::jsonb` |
| `updated_by` | uuid | yes |  |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `org_settings_pkey`: `PRIMARY KEY (organization_id)`

**Foreign keys**

- `org_settings_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `org_settings_updated_by_fkey`: `FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL`

**Check constraints**

- `ck_orgsettings_objects`: `CHECK (jsonb_typeof(settings) = 'object'::text AND jsonb_typeof(wizard) = 'object'::text)`
- `ck_orgsettings_version`: `CHECK (schema_version >= 1)`

**RLS policies**

- `org_settings_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### organizations

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `name` | character varying(200) | no |  |
| `slug` | character varying(80) | no |  |
| `status` | character varying(20) | no | `'active'::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |
| `legal_name` | character varying(200) | yes |  |
| `address_line1` | character varying(200) | yes |  |
| `address_line2` | character varying(200) | yes |  |
| `city` | character varying(100) | yes |  |
| `state` | character varying(100) | yes |  |
| `pincode` | character varying(6) | yes |  |
| `phone` | character varying(20) | yes |  |
| `email` | character varying(320) | yes |  |
| `gstin` | character varying(15) | yes |  |
| `registration_number` | character varying(60) | yes |  |
| `letterhead_note` | character varying(500) | yes |  |
| `default_language` | character varying(2) | no | `'en'::character varying` |
| `timezone` | character varying(64) | no | `'Asia/Kolkata'::character varying` |
| `mfa_required_roles` | character varying(40)[] | no | `'{}'::character varying[]` |
| `offboarding_requested_at` | timestamp with time zone | yes |  |
| `offboarding_requested_by` | uuid | yes |  |
| `offboarding_reason` | character varying(500) | yes |  |

**Primary key** `organizations_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `organizations_offboarding_requested_by_fkey`: `FOREIGN KEY (offboarding_requested_by) REFERENCES users(id) ON DELETE SET NULL`

**Unique constraints**

- `organizations_slug_key`: `UNIQUE (slug)`

**Check constraints**

- `ck_org_gstin`: `CHECK (gstin IS NULL OR gstin::text ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'::text)`
- `ck_org_language`: `CHECK (default_language::text = ANY (ARRAY['en'::character varying, 'mr'::character varying, 'hi'::character varying]::text[]))`
- `ck_org_pincode`: `CHECK (pincode IS NULL OR pincode::text ~ '^[1-9][0-9]{5}$'::text)`
- `ck_org_status`: `CHECK (status::text = ANY (ARRAY['active'::character varying, 'suspended'::character varying, 'deleting'::character varying]::text[]))`

**RLS policies**

- `org_insert_bootstrap` FOR INSERT TO public
  - WITH CHECK `(current_setting('app.is_bootstrap'::text, true) = 'true'::text)`
- `org_select_member` FOR SELECT TO public
  - USING `((id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) OR (EXISTS ( SELECT 1 FROM memberships m WHERE ((m.organization_id = organizations.id) AND (m.user_id = (NULLIF(current_setting('app.current_user_id'::text, true), ''::text))::uuid)))))`
- `org_select_platform` FOR SELECT TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
- `org_update_member` FOR UPDATE TO public
  - USING `(EXISTS ( SELECT 1 FROM memberships m WHERE ((m.organization_id = organizations.id) AND (m.user_id = (NULLIF(current_setting('app.current_user_id'::text, true), ''::text))::uuid) AND ((m.status)::text = 'active'::text))))`
  - WITH CHECK `true`
- `org_update_platform` FOR UPDATE TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`

### password_reset_tokens

- Row-level security: **disabled**
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `user_id` | uuid | no |  |
| `token_hash` | character varying(64) | no |  |
| `expires_at` | timestamp with time zone | no |  |
| `used_at` | timestamp with time zone | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `ip_address` | character varying(60) | yes |  |

**Primary key** `password_reset_tokens_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `password_reset_tokens_user_id_fkey`: `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`

**Unique constraints**

- `password_reset_tokens_token_hash_key`: `UNIQUE (token_hash)`

**Indexes**

- `ix_pwreset_user`: `btree (user_id)`

### patients

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `uhid` | character varying(20) | no |  |
| `full_name` | character varying(200) | no |  |
| `gender` | character varying(20) | no |  |
| `date_of_birth` | date | yes |  |
| `dob_estimated` | boolean | no | `false` |
| `phone` | character varying(20) | yes |  |
| `address` | text | no | `''::text` |
| `blood_group` | character varying(5) | yes |  |
| `allergies` | text | no | `''::text` |
| `status` | character varying(20) | no | `'active'::character varying` |
| `merged_into_id` | uuid | yes |  |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `patients_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `patients_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `patients_merged_into_id_fkey`: `FOREIGN KEY (merged_into_id) REFERENCES patients(id) ON DELETE SET NULL`
- `patients_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_patient_org_uhid`: `UNIQUE (organization_id, uhid)`

**Check constraints**

- `ck_patient_blood_group`: `CHECK (blood_group IS NULL OR (blood_group::text = ANY (ARRAY['A+'::character varying, 'A-'::character varying, 'B+'::character varying, 'B-'::character varying, 'AB+'::character varying, 'AB-'::character varying, 'O+'::character varying, 'O-'::character varying]::text[])))`
- `ck_patient_gender`: `CHECK (gender::text = ANY (ARRAY['male'::character varying, 'female'::character varying, 'other'::character varying, 'unknown'::character varying]::text[]))`
- `ck_patient_status`: `CHECK (status::text = ANY (ARRAY['active'::character varying, 'inactive'::character varying, 'merged'::character varying]::text[]))`

**Indexes**

- `ix_patients_org_created`: `btree (organization_id, created_at)`
- `ix_patients_org_name`: `btree (organization_id, lower((full_name)::text))`
- `ix_patients_org_phone`: `btree (organization_id, phone)`

**RLS policies**

- `patients_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### payments

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `invoice_id` | uuid | no |  |
| `amount` | numeric(12,2) | no |  |
| `method` | character varying(20) | no |  |
| `gateway` | character varying(20) | no | `'manual'::character varying` |
| `status` | character varying(20) | no | `'pending'::character varying` |
| `gateway_ref` | character varying(120) | no | `''::character varying` |
| `failure_reason` | character varying(300) | no | `''::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `payments_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `payments_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `payments_invoice_id_fkey`: `FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE RESTRICT`
- `payments_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_pay_amount_positive`: `CHECK (amount > 0::numeric)`
- `ck_pay_gateway`: `CHECK (gateway::text = ANY (ARRAY['manual'::character varying, 'sandbox'::character varying]::text[]))`
- `ck_pay_method`: `CHECK (method::text = ANY (ARRAY['cash'::character varying, 'upi'::character varying, 'card'::character varying, 'insurance'::character varying, 'other'::character varying]::text[]))`
- `ck_pay_status`: `CHECK (status::text = ANY (ARRAY['pending'::character varying, 'succeeded'::character varying, 'failed'::character varying, 'refunded'::character varying, 'partially_refunded'::character varying]::text[]))`

**Indexes**

- `ix_pay_org_invoice`: `btree (organization_id, invoice_id)`

**RLS policies**

- `payments_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_payment_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_payment_mutation()`

### permissions

- Row-level security: **disabled**
- Grants for hms_app: SELECT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `key` | character varying(60) | no |  |
| `description` | text | no | `''::text` |

**Primary key** `permissions_pkey`: `PRIMARY KEY (key)`

### plan_features

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `plan_id` | uuid | no |  |
| `feature_key` | character varying(40) | no |  |

**Primary key** `pk_plan_features`: `PRIMARY KEY (plan_id, feature_key)`

**Foreign keys**

- `plan_features_plan_id_fkey`: `FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE`

**RLS policies**

- `plan_features_read` FOR SELECT TO public
  - USING `true`
- `plan_features_write` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`

### plan_limits

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `plan_id` | uuid | no |  |
| `limit_key` | character varying(40) | no |  |
| `limit_value` | bigint | yes |  |

**Primary key** `pk_plan_limits`: `PRIMARY KEY (plan_id, limit_key)`

**Foreign keys**

- `plan_limits_plan_id_fkey`: `FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE`

**Check constraints**

- `ck_plan_limit_nonneg`: `CHECK (limit_value IS NULL OR limit_value >= 0)`

**RLS policies**

- `plan_limits_read` FOR SELECT TO public
  - USING `true`
- `plan_limits_write` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`

### plans

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `code` | character varying(40) | no |  |
| `name` | character varying(120) | no |  |
| `description` | character varying(1000) | no | `''::character varying` |
| `tier` | integer | no |  |
| `price_monthly_paise` | bigint | yes |  |
| `price_annual_paise` | bigint | yes |  |
| `currency` | character varying(3) | no | `'INR'::character varying` |
| `trial_days` | integer | no | `30` |
| `is_active` | boolean | no | `true` |
| `is_public` | boolean | no | `true` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `plans_pkey`: `PRIMARY KEY (id)`

**Unique constraints**

- `plans_code_key`: `UNIQUE (code)`

**Check constraints**

- `ck_plan_price_annual`: `CHECK (price_annual_paise IS NULL OR price_annual_paise >= 0)`
- `ck_plan_price_monthly`: `CHECK (price_monthly_paise IS NULL OR price_monthly_paise >= 0)`
- `ck_plan_trial_days`: `CHECK (trial_days >= 0 AND trial_days <= 365)`

**RLS policies**

- `plans_read` FOR SELECT TO public
  - USING `true`
- `plans_write` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`

### prescription_items

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `prescription_id` | uuid | no |  |
| `drug_id` | uuid | no |  |
| `dose` | character varying(100) | no |  |
| `route` | character varying(40) | no | `'oral'::character varying` |
| `frequency` | character varying(100) | no |  |
| `duration_days` | integer | no |  |
| `quantity` | character varying(100) | no | `''::character varying` |
| `instructions` | character varying(500) | no | `''::character varying` |
| `seq` | integer | no | `0` |
| `dispense_quantity` | integer | yes |  |

**Primary key** `prescription_items_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `prescription_items_drug_id_fkey`: `FOREIGN KEY (drug_id) REFERENCES drug_catalog(id) ON DELETE RESTRICT`
- `prescription_items_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `prescription_items_prescription_id_fkey`: `FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE`

**Check constraints**

- `ck_rxitem_dispense_qty`: `CHECK (dispense_quantity IS NULL OR dispense_quantity >= 1 AND dispense_quantity <= 10000)`
- `ck_rxitem_duration`: `CHECK (duration_days >= 1 AND duration_days <= 365)`
- `ck_rxitem_seq`: `CHECK (seq >= 0)`

**Indexes**

- `ix_rxitem_org_rx`: `btree (organization_id, prescription_id)`

**RLS policies**

- `prescription_items_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_rxitem_immutable`: BEFORE INSERT OR UPDATE OR DELETE FOR EACH ROW -> `forbid_rxitem_mutation()`

### prescriptions

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `encounter_id` | uuid | yes |  |
| `patient_id` | uuid | no |  |
| `created_by` | uuid | yes |  |
| `prescriber_user_id` | uuid | yes |  |
| `status` | character varying(20) | no | `'draft'::character varying` |
| `version` | integer | no | `1` |
| `supersedes_id` | uuid | yes |  |
| `diagnosis_text` | character varying(500) | no | `''::character varying` |
| `advice` | text | no | `''::text` |
| `follow_up` | character varying(300) | no | `''::character varying` |
| `allergy_acknowledged` | boolean | no | `false` |
| `signed_at` | timestamp with time zone | yes |  |
| `amendment_reason` | character varying(500) | no | `''::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `prescriptions_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `prescriptions_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `prescriptions_encounter_id_fkey`: `FOREIGN KEY (encounter_id) REFERENCES encounters(id) ON DELETE RESTRICT`
- `prescriptions_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `prescriptions_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`
- `prescriptions_prescriber_user_id_fkey`: `FOREIGN KEY (prescriber_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `prescriptions_supersedes_id_fkey`: `FOREIGN KEY (supersedes_id) REFERENCES prescriptions(id) ON DELETE SET NULL`

**Check constraints**

- `ck_rx_status`: `CHECK (status::text = ANY (ARRAY['draft'::character varying, 'signed'::character varying, 'superseded'::character varying]::text[]))`
- `ck_rx_version`: `CHECK (version >= 1)`

**Indexes**

- `ix_rx_org_patient`: `btree (organization_id, patient_id)`
- `ix_rx_org_status`: `btree (organization_id, status)`

**RLS policies**

- `prescriptions_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_rx_immutable`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_rx_mutation()`

### printer_profiles

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `name` | character varying(80) | no |  |
| `kind` | character varying(20) | no |  |
| `default_for` | character varying(20)[] | no | `'{}'::character varying[]` |
| `margin_top_mm` | numeric(4,1) | no | `'10'::numeric` |
| `margin_right_mm` | numeric(4,1) | no | `'10'::numeric` |
| `margin_bottom_mm` | numeric(4,1) | no | `'10'::numeric` |
| `margin_left_mm` | numeric(4,1) | no | `'10'::numeric` |
| `font_scale` | numeric(3,2) | no | `1.00` |
| `notes` | character varying(300) | no | `''::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `printer_profiles_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `printer_profiles_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `printer_profiles_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Check constraints**

- `ck_printer_default_for`: `CHECK (default_for <@ ARRAY['prescription'::character varying, 'receipt'::character varying, 'lab_report'::character varying])`
- `ck_printer_font_scale`: `CHECK (font_scale >= 0.5 AND font_scale <= 2.0)`
- `ck_printer_kind`: `CHECK (kind::text = ANY (ARRAY['a4'::character varying, 'a5'::character varying, 'thermal_80mm'::character varying, 'thermal_58mm'::character varying]::text[]))`
- `ck_printer_margins`: `CHECK (margin_top_mm >= 0::numeric AND margin_top_mm <= 50::numeric AND margin_right_mm >= 0::numeric AND margin_right_mm <= 50::numeric AND margin_bottom_mm >= 0::numeric AND margin_bottom_mm <= 50::numeric AND margin_left_mm >= 0::numeric AND margin_left_mm <= 50::numeric)`

**Indexes**

- `uq_printer_org_name` (UNIQUE): `btree (organization_id, lower((name)::text))`

**RLS policies**

- `printer_profiles_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

### rate_limit_counters

- Row-level security: **disabled**
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `key_hash` | character varying(64) | no |  |
| `window_start` | timestamp with time zone | no |  |
| `hits` | integer | no | `0` |
| `expires_at` | timestamp with time zone | no |  |

**Primary key** `pk_rate_limit_counters`: `PRIMARY KEY (key_hash, window_start)`

**Indexes**

- `ix_rate_limit_expires`: `btree (expires_at)`

### refunds

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `payment_id` | uuid | no |  |
| `amount` | numeric(12,2) | no |  |
| `reason` | character varying(300) | no |  |
| `status` | character varying(20) | no | `'succeeded'::character varying` |
| `gateway_ref` | character varying(120) | no | `''::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `refunds_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `refunds_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `refunds_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `refunds_payment_id_fkey`: `FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_ref_amount_positive`: `CHECK (amount > 0::numeric)`
- `ck_ref_status`: `CHECK (status::text = ANY (ARRAY['succeeded'::character varying, 'failed'::character varying]::text[]))`

**Indexes**

- `ix_ref_org_payment`: `btree (organization_id, payment_id)`

**RLS policies**

- `refunds_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_refund_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_refund_mutation()`

### role_permissions

- Row-level security: **disabled**
- Grants for hms_app: SELECT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `role_id` | uuid | no |  |
| `permission_key` | character varying(60) | no |  |

**Primary key** `role_permissions_pkey`: `PRIMARY KEY (role_id, permission_key)`

**Foreign keys**

- `role_permissions_permission_key_fkey`: `FOREIGN KEY (permission_key) REFERENCES permissions(key) ON DELETE CASCADE`
- `role_permissions_role_id_fkey`: `FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE`

### roles

- Row-level security: **disabled**
- Grants for hms_app: SELECT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `key` | character varying(40) | no |  |
| `name` | character varying(100) | no |  |
| `description` | text | no | `''::text` |
| `system` | boolean | no | `true` |

**Primary key** `roles_pkey`: `PRIMARY KEY (id)`

**Unique constraints**

- `roles_key_key`: `UNIQUE (key)`

### saas_invoices

- Row-level security: enabled (FORCE)
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `number` | character varying(30) | no |  |
| `kind` | character varying(12) | no |  |
| `order_id` | uuid | no |  |
| `refund_id` | uuid | yes |  |
| `related_invoice_id` | uuid | yes |  |
| `issued_at` | timestamp with time zone | no | `now()` |
| `period_start` | timestamp with time zone | yes |  |
| `period_end` | timestamp with time zone | yes |  |
| `seller` | jsonb | no |  |
| `buyer` | jsonb | no |  |
| `lines` | jsonb | no |  |
| `subtotal_paise` | bigint | no |  |
| `tax_breakdown` | jsonb | no |  |
| `tax_paise` | bigint | no |  |
| `total_paise` | bigint | no |  |
| `currency` | character varying(3) | no |  |

**Primary key** `saas_invoices_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `saas_invoices_order_id_fkey`: `FOREIGN KEY (order_id) REFERENCES saas_orders(id)`
- `saas_invoices_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT`
- `saas_invoices_related_invoice_id_fkey`: `FOREIGN KEY (related_invoice_id) REFERENCES saas_invoices(id)`

**Unique constraints**

- `saas_invoices_number_key`: `UNIQUE (number)`

**Check constraints**

- `ck_saasinv_kind`: `CHECK (kind::text = ANY (ARRAY['invoice'::character varying, 'credit_note'::character varying]::text[]))`
- `ck_saasinv_total`: `CHECK (total_paise = (subtotal_paise + tax_paise))`

**Indexes**

- `uq_saasinv_order_invoice` (UNIQUE, partial): `btree (order_id)` WHERE `((kind)::text = 'invoice'::text)`

**RLS policies**

- `saas_invoices_platform` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
- `saas_invoices_tenant_read` FOR SELECT TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_saas_invoices_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_billing_record_mutation()`

### saas_orders

- Row-level security: enabled (FORCE)
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `kind` | character varying(20) | no |  |
| `plan_id` | uuid | yes |  |
| `billing_cycle` | character varying(10) | yes |  |
| `pack_id` | uuid | yes |  |
| `credits` | integer | yes |  |
| `description` | character varying(200) | no |  |
| `amount_paise` | bigint | no |  |
| `tax_paise` | bigint | no |  |
| `total_paise` | bigint | no |  |
| `currency` | character varying(3) | no | `'INR'::character varying` |
| `gst_rate_bp` | integer | no |  |
| `provider` | character varying(20) | no |  |
| `provider_order_id` | character varying(64) | no |  |
| `idempotency_key` | character varying(100) | no |  |
| `status` | character varying(12) | no | `'created'::character varying` |
| `failure_reason` | character varying(300) | yes |  |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `paid_at` | timestamp with time zone | yes |  |

**Primary key** `saas_orders_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `saas_orders_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `saas_orders_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT`
- `saas_orders_pack_id_fkey`: `FOREIGN KEY (pack_id) REFERENCES ai_credit_packs(id)`
- `saas_orders_plan_id_fkey`: `FOREIGN KEY (plan_id) REFERENCES plans(id)`

**Unique constraints**

- `saas_orders_provider_order_id_key`: `UNIQUE (provider_order_id)`
- `uq_saasorder_idem`: `UNIQUE (organization_id, idempotency_key)`

**Check constraints**

- `ck_saasorder_amounts`: `CHECK (amount_paise > 0 AND tax_paise >= 0 AND total_paise = (amount_paise + tax_paise))`
- `ck_saasorder_kind`: `CHECK (kind::text = ANY (ARRAY['subscription'::character varying, 'ai_credits'::character varying]::text[]))`
- `ck_saasorder_provider`: `CHECK (provider::text = ANY (ARRAY['razorpay'::character varying, 'simulator'::character varying]::text[]))`
- `ck_saasorder_shape`: `CHECK (kind::text = 'subscription'::text AND plan_id IS NOT NULL AND (billing_cycle::text = ANY (ARRAY['monthly'::character varying, 'annual'::character varying]::text[])) OR kind::text = 'ai_credits'::text AND pack_id IS NOT NULL AND credits > 0)`
- `ck_saasorder_status`: `CHECK (status::text = ANY (ARRAY['created'::character varying, 'paid'::character varying, 'failed'::character varying, 'expired'::character varying, 'cancelled'::character varying]::text[]))`

**Indexes**

- `ix_saasorder_org_created`: `btree (organization_id, created_at)`

**RLS policies**

- `saas_orders_platform` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
- `saas_orders_tenant_create` FOR INSERT TO public
  - WITH CHECK `((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) AND ((status)::text = 'created'::text))`
- `saas_orders_tenant_read` FOR SELECT TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_saas_orders_transition`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `guard_saas_order_transition()`

### saas_payments

- Row-level security: enabled (FORCE)
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `order_id` | uuid | no |  |
| `provider` | character varying(20) | no |  |
| `provider_payment_id` | character varying(64) | no |  |
| `amount_paise` | bigint | no |  |
| `currency` | character varying(3) | no |  |
| `status` | character varying(10) | no |  |
| `method` | character varying(30) | yes |  |
| `source` | character varying(20) | no |  |
| `signature_verified` | boolean | no |  |
| `error` | character varying(300) | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `saas_payments_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `saas_payments_order_id_fkey`: `FOREIGN KEY (order_id) REFERENCES saas_orders(id)`
- `saas_payments_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT`

**Unique constraints**

- `saas_payments_provider_payment_id_key`: `UNIQUE (provider_payment_id)`

**Check constraints**

- `ck_saaspay_amount`: `CHECK (amount_paise > 0)`
- `ck_saaspay_source`: `CHECK (source::text = ANY (ARRAY['checkout'::character varying, 'webhook'::character varying, 'reconciliation'::character varying]::text[]))`
- `ck_saaspay_status`: `CHECK (status::text = ANY (ARRAY['captured'::character varying, 'failed'::character varying]::text[]))`

**Indexes**

- `ix_saaspay_order`: `btree (order_id)`

**RLS policies**

- `saas_payments_platform` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
- `saas_payments_tenant_read` FOR SELECT TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_saas_payments_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_billing_record_mutation()`

### saas_refunds

- Row-level security: enabled (FORCE)
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `payment_id` | uuid | no |  |
| `amount_paise` | bigint | no |  |
| `reason` | character varying(500) | no |  |
| `status` | character varying(12) | no | `'requested'::character varying` |
| `requested_by` | uuid | yes |  |
| `decided_by` | uuid | yes |  |
| `decided_at` | timestamp with time zone | yes |  |
| `decision_note` | character varying(500) | yes |  |
| `provider_refund_id` | character varying(64) | yes |  |
| `error` | character varying(300) | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `saas_refunds_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `saas_refunds_decided_by_fkey`: `FOREIGN KEY (decided_by) REFERENCES users(id) ON DELETE SET NULL`
- `saas_refunds_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT`
- `saas_refunds_payment_id_fkey`: `FOREIGN KEY (payment_id) REFERENCES saas_payments(id)`
- `saas_refunds_requested_by_fkey`: `FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE SET NULL`

**Unique constraints**

- `saas_refunds_provider_refund_id_key`: `UNIQUE (provider_refund_id)`

**Check constraints**

- `ck_saasrefund_amount`: `CHECK (amount_paise > 0)`
- `ck_saasrefund_four_eyes`: `CHECK (decided_by IS NULL OR decided_by IS DISTINCT FROM requested_by)`
- `ck_saasrefund_status`: `CHECK (status::text = ANY (ARRAY['requested'::character varying, 'rejected'::character varying, 'processed'::character varying, 'failed'::character varying]::text[]))`

**RLS policies**

- `saas_refunds_platform` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
- `saas_refunds_tenant_read` FOR SELECT TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
- `saas_refunds_tenant_request` FOR INSERT TO public
  - WITH CHECK `((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) AND ((status)::text = 'requested'::text) AND (decided_by IS NULL))`

**Triggers**

- `trg_saas_refunds_transition`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `guard_saas_refund_transition()`

### saas_webhook_events

- Row-level security: enabled (FORCE)
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `provider` | character varying(20) | no |  |
| `event_id` | character varying(100) | no |  |
| `event_type` | character varying(60) | no |  |
| `signature_valid` | boolean | no |  |
| `payload_sha256` | character varying(64) | no |  |
| `payload` | jsonb | yes |  |
| `organization_id` | uuid | yes |  |
| `outcome` | character varying(20) | no |  |
| `detail` | character varying(300) | no | `''::character varying` |
| `received_at` | timestamp with time zone | no | `now()` |

**Primary key** `saas_webhook_events_pkey`: `PRIMARY KEY (id)`

**Unique constraints**

- `uq_saaswebhook_event`: `UNIQUE (provider, event_id)`

**Check constraints**

- `ck_saaswebhook_outcome`: `CHECK (outcome::text = ANY (ARRAY['processed'::character varying, 'duplicate'::character varying, 'ignored'::character varying, 'rejected'::character varying, 'mismatch'::character varying, 'failed'::character varying]::text[]))`

**RLS policies**

- `saaswebhook_platform` FOR ALL TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`

**Triggers**

- `trg_saas_webhook_events_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_billing_record_mutation()`

### scribe_consents

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `encounter_id` | uuid | no |  |
| `obtained_by` | uuid | no |  |
| `method` | character varying(20) | no |  |
| `notice_language` | character varying(5) | no |  |
| `notice_version` | character varying(20) | no |  |
| `given_at` | timestamp with time zone | no | `now()` |

**Primary key** `scribe_consents_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `scribe_consents_encounter_id_fkey`: `FOREIGN KEY (encounter_id) REFERENCES encounters(id) ON DELETE RESTRICT`
- `scribe_consents_obtained_by_fkey`: `FOREIGN KEY (obtained_by) REFERENCES users(id) ON DELETE SET NULL`
- `scribe_consents_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `scribe_consents_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_scribeconsent_lang`: `CHECK (notice_language::text = ANY (ARRAY['en'::character varying, 'mr'::character varying, 'hi'::character varying]::text[]))`
- `ck_scribeconsent_method`: `CHECK (method::text = 'verbal'::text)`

**RLS policies**

- `scribe_consents_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_scribe_consents_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_ai_log_mutation()`

### scribe_sessions

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `encounter_id` | uuid | no |  |
| `patient_id` | uuid | no |  |
| `clinician_id` | uuid | no |  |
| `consent_id` | uuid | no |  |
| `status` | character varying(20) | no | `'consented'::character varying` |
| `transcriber` | character varying(40) | no | `''::character varying` |
| `transcript_sealed` | text | yes |  |
| `segment_count` | integer | no | `0` |
| `draft_sealed` | text | yes |  |
| `draft_valid` | boolean | yes |  |
| `ai_request_id` | uuid | yes |  |
| `audio_stored` | boolean | no | `false` |
| `accepted_by` | uuid | yes |  |
| `accepted_at` | timestamp with time zone | yes |  |
| `accepted_fields` | character varying(30)[] | no | `'{}'::character varying[]` |
| `edit_ratio` | numeric(5,4) | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `scribe_sessions_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `scribe_sessions_accepted_by_fkey`: `FOREIGN KEY (accepted_by) REFERENCES users(id) ON DELETE SET NULL`
- `scribe_sessions_ai_request_id_fkey`: `FOREIGN KEY (ai_request_id) REFERENCES ai_requests(id) ON DELETE SET NULL`
- `scribe_sessions_clinician_id_fkey`: `FOREIGN KEY (clinician_id) REFERENCES users(id) ON DELETE SET NULL`
- `scribe_sessions_consent_id_fkey`: `FOREIGN KEY (consent_id) REFERENCES scribe_consents(id) ON DELETE RESTRICT`
- `scribe_sessions_encounter_id_fkey`: `FOREIGN KEY (encounter_id) REFERENCES encounters(id) ON DELETE RESTRICT`
- `scribe_sessions_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `scribe_sessions_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT`

**Check constraints**

- `ck_scribesession_no_audio`: `CHECK (audio_stored = false)`
- `ck_scribesession_status`: `CHECK (status::text = ANY (ARRAY['consented'::character varying, 'drafted'::character varying, 'accepted'::character varying, 'discarded'::character varying]::text[]))`

**Indexes**

- `ix_scribesession_org_enc`: `btree (organization_id, encounter_id)`

**RLS policies**

- `scribe_sessions_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_scribe_sessions_guard`: BEFORE UPDATE FOR EACH ROW -> `guard_scribe_session()`

### stock_batches

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `drug_id` | uuid | no |  |
| `batch_number` | character varying(60) | no |  |
| `expiry_date` | date | no |  |
| `quantity_received` | integer | no |  |
| `quantity_on_hand` | integer | no | `0` |
| `unit_cost` | numeric(12,2) | no | `'0'::numeric` |
| `supplier` | character varying(200) | no | `''::character varying` |
| `status` | character varying(20) | no | `'active'::character varying` |
| `received_at` | timestamp with time zone | no | `now()` |
| `received_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `stock_batches_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `stock_batches_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `stock_batches_drug_id_fkey`: `FOREIGN KEY (drug_id) REFERENCES drug_catalog(id) ON DELETE RESTRICT`
- `stock_batches_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `stock_batches_received_by_fkey`: `FOREIGN KEY (received_by) REFERENCES users(id) ON DELETE SET NULL`

**Unique constraints**

- `uq_batch_org_branch_drug_no`: `UNIQUE (organization_id, branch_id, drug_id, batch_number)`

**Check constraints**

- `ck_batch_on_hand_nonneg`: `CHECK (quantity_on_hand >= 0)`
- `ck_batch_qty_received_positive`: `CHECK (quantity_received > 0)`
- `ck_batch_status`: `CHECK (status::text = ANY (ARRAY['active'::character varying, 'depleted'::character varying, 'expired'::character varying, 'recalled'::character varying]::text[]))`
- `ck_batch_unit_cost_nonneg`: `CHECK (unit_cost >= 0::numeric)`

**Indexes**

- `ix_batches_org_branch`: `btree (organization_id, branch_id)`
- `ix_batches_org_drug_expiry`: `btree (organization_id, drug_id, expiry_date)`
- `ix_batches_org_status`: `btree (organization_id, status)`

**RLS policies**

- `stock_batches_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_batch_recall_frozen`: BEFORE UPDATE FOR EACH ROW -> `forbid_recalled_batch_change()`

### stock_movements

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `batch_id` | uuid | no |  |
| `movement_type` | character varying(20) | no |  |
| `direction` | character varying(4) | no |  |
| `quantity` | integer | no |  |
| `dispense_id` | uuid | yes |  |
| `patient_id` | uuid | yes |  |
| `reason` | character varying(300) | no | `''::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `stock_movements_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `stock_movements_batch_id_fkey`: `FOREIGN KEY (batch_id) REFERENCES stock_batches(id) ON DELETE RESTRICT`
- `stock_movements_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `stock_movements_dispense_id_fkey`: `FOREIGN KEY (dispense_id) REFERENCES dispenses(id) ON DELETE SET NULL`
- `stock_movements_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `stock_movements_patient_id_fkey`: `FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL`

**Check constraints**

- `ck_movement_direction`: `CHECK (direction::text = ANY (ARRAY['in'::character varying, 'out'::character varying]::text[]))`
- `ck_movement_qty_positive`: `CHECK (quantity > 0)`
- `ck_movement_type`: `CHECK (movement_type::text = ANY (ARRAY['receive'::character varying, 'dispense'::character varying, 'adjustment'::character varying, 'return'::character varying]::text[]))`

**Indexes**

- `ix_movement_org_batch`: `btree (organization_id, batch_id, id)`

**RLS policies**

- `stock_movements_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

**Triggers**

- `trg_movement_append_only`: BEFORE UPDATE OR DELETE FOR EACH ROW -> `forbid_movement_mutation()`
- `trg_movement_apply`: BEFORE INSERT FOR EACH ROW -> `apply_stock_movement()`

### subscription_events

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `organization_id` | uuid | no |  |
| `from_plan` | character varying(40) | yes |  |
| `to_plan` | character varying(40) | yes |  |
| `from_status` | character varying(20) | yes |  |
| `to_status` | character varying(20) | yes |  |
| `reason` | character varying(500) | no | `''::character varying` |
| `actor_user_id` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `subscription_events_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `subscription_events_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `subscription_events_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Indexes**

- `ix_subevent_org_created`: `btree (organization_id, created_at)`

**RLS policies**

- `subevent_rw` FOR ALL TO public
  - USING `((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) OR (COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text))`
  - WITH CHECK `((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) OR (COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text))`

### subscriptions

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `plan_id` | uuid | no |  |
| `status` | character varying(20) | no |  |
| `billing_cycle` | character varying(10) | no | `'monthly'::character varying` |
| `trial_ends_at` | timestamp with time zone | yes |  |
| `current_period_start` | timestamp with time zone | yes |  |
| `current_period_end` | timestamp with time zone | yes |  |
| `grace_until` | timestamp with time zone | yes |  |
| `feature_overrides` | jsonb | no | `'{}'::jsonb` |
| `limit_overrides` | jsonb | no | `'{}'::jsonb` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `subscriptions_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `subscriptions_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `subscriptions_plan_id_fkey`: `FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE RESTRICT`

**Unique constraints**

- `subscriptions_organization_id_key`: `UNIQUE (organization_id)`

**Check constraints**

- `ck_subscription_cycle`: `CHECK (billing_cycle::text = ANY (ARRAY['monthly'::character varying, 'annual'::character varying]::text[]))`
- `ck_subscription_status`: `CHECK (status::text = ANY (ARRAY['trialing'::character varying, 'active'::character varying, 'past_due'::character varying, 'read_only'::character varying, 'suspended'::character varying, 'cancelled'::character varying]::text[]))`

**RLS policies**

- `subscription_insert` FOR INSERT TO public
  - WITH CHECK `((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) OR (COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text))`
- `subscription_read` FOR SELECT TO public
  - USING `((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) OR (COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text))`
- `subscription_update` FOR UPDATE TO public
  - USING `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`
  - WITH CHECK `(COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text)`

### support_ticket_messages

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | bigint | no | `identity BY DEFAULT` |
| `ticket_id` | uuid | no |  |
| `organization_id` | uuid | no |  |
| `author_user_id` | uuid | yes |  |
| `author_side` | character varying(10) | no |  |
| `body` | character varying(5000) | no |  |
| `internal` | boolean | no | `false` |
| `created_at` | timestamp with time zone | no | `now()` |

**Primary key** `support_ticket_messages_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `support_ticket_messages_author_user_id_fkey`: `FOREIGN KEY (author_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `support_ticket_messages_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`
- `support_ticket_messages_ticket_id_fkey`: `FOREIGN KEY (ticket_id) REFERENCES support_tickets(id) ON DELETE CASCADE`

**Check constraints**

- `ck_ticketmsg_internal_vendor`: `CHECK (NOT internal OR author_side::text = 'vendor'::text)`
- `ck_ticketmsg_side`: `CHECK (author_side::text = ANY (ARRAY['customer'::character varying, 'vendor'::character varying]::text[]))`

**Indexes**

- `ix_ticketmsg_ticket`: `btree (ticket_id, id)`

**RLS policies**

- `ticketmsg_insert` FOR INSERT TO public
  - WITH CHECK `(((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) AND (NOT internal) AND ((author_side)::text = 'customer'::text)) OR (COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text))`
- `ticketmsg_read` FOR SELECT TO public
  - USING `(((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) AND (NOT internal)) OR (COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text))`

### support_tickets

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `number` | character varying(20) | no |  |
| `subject` | character varying(200) | no |  |
| `category` | character varying(20) | no |  |
| `priority` | character varying(10) | no | `'normal'::character varying` |
| `status` | character varying(25) | no | `'open'::character varying` |
| `created_by` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `support_tickets_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `support_tickets_created_by_fkey`: `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `support_tickets_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `support_tickets_number_key`: `UNIQUE (number)`

**Check constraints**

- `ck_ticket_category`: `CHECK (category::text = ANY (ARRAY['technical'::character varying, 'billing'::character varying, 'account'::character varying, 'feature_request'::character varying, 'data_request'::character varying, 'other'::character varying]::text[]))`
- `ck_ticket_priority`: `CHECK (priority::text = ANY (ARRAY['low'::character varying, 'normal'::character varying, 'high'::character varying, 'urgent'::character varying]::text[]))`
- `ck_ticket_status`: `CHECK (status::text = ANY (ARRAY['open'::character varying, 'in_progress'::character varying, 'waiting_on_customer'::character varying, 'resolved'::character varying, 'closed'::character varying]::text[]))`

**Indexes**

- `ix_ticket_org_status`: `btree (organization_id, status)`

**RLS policies**

- `ticket_rw` FOR ALL TO public
  - USING `((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) OR (COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text))`
  - WITH CHECK `((organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid) OR (COALESCE(current_setting('app.platform_admin'::text, true), ''::text) = 'true'::text))`

### users

- Row-level security: **disabled**
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `email` | character varying(320) | no |  |
| `full_name` | character varying(200) | no |  |
| `password_hash` | character varying(255) | no |  |
| `status` | character varying(20) | no | `'active'::character varying` |
| `is_superadmin` | boolean | no | `false` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |
| `mfa_totp_secret_enc` | text | yes |  |
| `mfa_totp_pending_enc` | text | yes |  |
| `mfa_totp_enabled_at` | timestamp with time zone | yes |  |
| `mfa_totp_last_step` | bigint | yes |  |
| `password_changed_at` | timestamp with time zone | yes |  |
| `registration_number` | character varying(60) | yes |  |

**Primary key** `users_pkey`: `PRIMARY KEY (id)`

**Unique constraints**

- `users_email_key`: `UNIQUE (email)`

**Check constraints**

- `ck_user_status`: `CHECK (status::text = ANY (ARRAY['active'::character varying, 'disabled'::character varying]::text[]))`

### wards

- Row-level security: enabled
- Grants for hms_app: SELECT, INSERT, UPDATE, DELETE

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `organization_id` | uuid | no |  |
| `branch_id` | uuid | no |  |
| `name` | character varying(120) | no |  |
| `code` | character varying(30) | no |  |
| `ward_type` | character varying(30) | no | `'general'::character varying` |
| `status` | character varying(20) | no | `'active'::character varying` |
| `created_at` | timestamp with time zone | no | `now()` |
| `updated_at` | timestamp with time zone | no | `now()` |

**Primary key** `wards_pkey`: `PRIMARY KEY (id)`

**Foreign keys**

- `wards_branch_id_fkey`: `FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT`
- `wards_organization_id_fkey`: `FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE`

**Unique constraints**

- `uq_ward_org_branch_code`: `UNIQUE (organization_id, branch_id, code)`

**Check constraints**

- `ck_ward_status`: `CHECK (status::text = ANY (ARRAY['active'::character varying, 'closed'::character varying]::text[]))`
- `ck_ward_type`: `CHECK (ward_type::text = ANY (ARRAY['general'::character varying, 'icu'::character varying, 'maternity'::character varying, 'pediatric'::character varying, 'isolation'::character varying, 'day_care'::character varying, 'private'::character varying, 'other'::character varying]::text[]))`

**Indexes**

- `ix_wards_org_branch`: `btree (organization_id, branch_id)`

**RLS policies**

- `wards_tenant` FOR ALL TO public
  - USING `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`
  - WITH CHECK `(organization_id = (NULLIF(current_setting('app.current_org_id'::text, true), ''::text))::uuid)`

## Sequences

| Sequence | hms_app grants |
|---|---|
| `admission_transfers_id_seq` | (none) |
| `ai_credit_ledger_id_seq` | (none) |
| `ai_proposal_events_id_seq` | (none) |
| `audit_events_id_seq` | SELECT, USAGE |
| `comms_consent_events_id_seq` | (none) |
| `comms_delivery_log_id_seq` | (none) |
| `comms_messages_id_seq` | SELECT, USAGE |
| `inventory_movements_id_seq` | (none) |
| `ledger_entries_id_seq` | (none) |
| `saas_credit_note_number_seq` | USAGE |
| `saas_invoice_number_seq` | USAGE |
| `saas_webhook_events_id_seq` | USAGE |
| `stock_movements_id_seq` | (none) |
| `subscription_events_id_seq` | (none) |
| `support_ticket_messages_id_seq` | (none) |
| `support_ticket_number_seq` | SELECT, USAGE |

## SECURITY DEFINER functions

| Function | Returns | Language | Config | Owner | hms_app EXECUTE |
|---|---|---|---|---|---|
| `insert_audit_event(p_organization_id uuid, p_actor_user_id uuid, p_action text, p_resource_type text, p_resource_id text, p_metadata jsonb, p_correlation_id text, p_ip_address text)` | void | plpgsql | `search_path=public` | hms | yes |
| `invitation_org_for_token(p_token_hash text)` | uuid | sql | `search_path=public` | hms | yes |
| `platform_tenant_overview()` | TABLE(organization_id uuid, users bigint, branches bigint, beds bigint, patients bigint) | plpgsql | `search_path=public` | hms | yes |

## Other functions (SECURITY INVOKER)

| Function | Returns | Language |
|---|---|---|
| `apply_inventory_movement()` | trigger | plpgsql |
| `apply_stock_movement()` | trigger | plpgsql |
| `check_laborder_release()` | trigger | plpgsql |
| `check_nursing_admission()` | trigger | plpgsql |
| `forbid_admission_mutation()` | trigger | plpgsql |
| `forbid_ai_log_mutation()` | trigger | plpgsql |
| `forbid_append_only_mutation()` | trigger | plpgsql |
| `forbid_billing_record_mutation()` | trigger | plpgsql |
| `forbid_closed_encounter()` | trigger | plpgsql |
| `forbid_closed_laborder()` | trigger | plpgsql |
| `forbid_comms_log_mutation()` | trigger | plpgsql |
| `forbid_completed_encounter_delete()` | trigger | plpgsql |
| `forbid_dispense_mutation()` | trigger | plpgsql |
| `forbid_expense_mutation()` | trigger | plpgsql |
| `forbid_invoice_regression()` | trigger | plpgsql |
| `forbid_issued_invoice_change()` | trigger | plpgsql |
| `forbid_issued_item_change()` | trigger | plpgsql |
| `forbid_laborderitem_mutation()` | trigger | plpgsql |
| `forbid_labresult_mutation()` | trigger | plpgsql |
| `forbid_ledger_mutation()` | trigger | plpgsql |
| `forbid_movement_mutation()` | trigger | plpgsql |
| `forbid_payment_mutation()` | trigger | plpgsql |
| `forbid_recalled_batch_change()` | trigger | plpgsql |
| `forbid_refund_mutation()` | trigger | plpgsql |
| `forbid_rx_mutation()` | trigger | plpgsql |
| `forbid_rxitem_mutation()` | trigger | plpgsql |
| `forbid_specimen_mutation()` | trigger | plpgsql |
| `forbids_audit_mutation()` | trigger | plpgsql |
| `guard_ai_proposal()` | trigger | plpgsql |
| `guard_kb_document()` | trigger | plpgsql |
| `guard_saas_order_transition()` | trigger | plpgsql |
| `guard_saas_refund_transition()` | trigger | plpgsql |
| `guard_scribe_session()` | trigger | plpgsql |

## Seeded RBAC catalogue

69 permission keys (seeded by migrations):

`admission.manage`, `ai.agents.approve`, `ai.agents.use`, `ai.audit.read`, `ai.copilot.use`, `ai.forecast.read`, `ai.knowledge.manage`, `ai.knowledge.use`, `ai.scribe.use`, `ai.settings.manage`, `appointment.read`, `appointment.write`, `audit.read`, `bed.manage`, `bed.read`, `billing.invoice`, `billing.payment`, `billing.read`, `billing.refund`, `billing.saas.pay`, `billing.saas.read`, `billing.saas.refund_request`, `branch.manage`, `branch.read`, `checkin.manage`, `comms.consent`, `comms.manage`, `comms.read`, `comms.send`, `discharge`, `encounter.read`, `encounter.write`, `expense.manage`, `expense.read`, `followup.create`, `followup.read`, `followup.write`, `inventory.manage`, `inventory.read`, `lab.import`, `lab.order`, `lab.read`, `lab.release`, `lab.verify`, `member.manage`, `member.read`, `nursing.read`, `nursing.write`, `org.manage`, `org.offboard`, `org.read`, `org.transfer_ownership`, `patient.merge`, `patient.read`, `patient.write`, `pharmacy.dispense`, `pharmacy.manage`, `pharmacy.read`, `prescription.read`, `prescription.sign`, `queue.manage`, `queue.read`, `report.read`, `setup.manage`, `setup.read`, `subscription.manage`, `subscription.read`, `support.read`, `support.write`

| System role | Permissions |
|---|---|
| `admin` | admission.manage, ai.agents.approve, ai.agents.use, ai.audit.read, ai.copilot.use, ai.forecast.read, ai.knowledge.manage, ai.knowledge.use, ai.settings.manage, appointment.read, appointment.write, audit.read, bed.manage, bed.read, billing.invoice, billing.payment, billing.read, billing.refund, billing.saas.pay, billing.saas.read, branch.manage, branch.read, checkin.manage, comms.consent, comms.manage, comms.read, comms.send, discharge, encounter.read, encounter.write, expense.manage, expense.read, followup.create, followup.read, followup.write, inventory.manage, inventory.read, lab.import, lab.order, lab.read, lab.release, lab.verify, member.manage, member.read, nursing.read, nursing.write, org.manage, org.read, patient.merge, patient.read, patient.write, pharmacy.dispense, pharmacy.manage, pharmacy.read, prescription.read, prescription.sign, queue.manage, queue.read, report.read, setup.manage, setup.read, subscription.manage, subscription.read, support.read, support.write |
| `auditor` | ai.audit.read, audit.read, billing.saas.read, branch.read, comms.read, member.read, org.read, subscription.read |
| `billing` | ai.copilot.use, ai.knowledge.use, appointment.read, bed.read, billing.invoice, billing.payment, billing.read, billing.refund, billing.saas.read, branch.read, expense.manage, expense.read, lab.read, member.read, org.read, patient.read, pharmacy.read, report.read, setup.read, subscription.read |
| `doctor` | admission.manage, ai.copilot.use, ai.forecast.read, ai.knowledge.use, ai.scribe.use, appointment.read, bed.read, billing.read, branch.read, comms.consent, comms.send, discharge, encounter.read, encounter.write, expense.read, followup.create, followup.read, followup.write, inventory.read, lab.order, lab.read, lab.release, lab.verify, member.read, nursing.read, nursing.write, org.read, patient.read, pharmacy.read, prescription.read, prescription.sign, queue.manage, queue.read, report.read, setup.read |
| `lab_technician` | ai.knowledge.use, bed.read, branch.read, lab.import, lab.order, lab.read, lab.verify, member.read, org.read, patient.read, setup.read |
| `nurse` | admission.manage, ai.forecast.read, ai.knowledge.use, appointment.read, bed.read, branch.read, encounter.read, encounter.write, followup.read, inventory.read, lab.order, lab.read, member.read, nursing.read, nursing.write, org.read, patient.read, pharmacy.read, prescription.read, queue.read, report.read, setup.read |
| `owner` | admission.manage, ai.agents.approve, ai.agents.use, ai.audit.read, ai.copilot.use, ai.forecast.read, ai.knowledge.manage, ai.knowledge.use, ai.scribe.use, ai.settings.manage, appointment.read, appointment.write, audit.read, bed.manage, bed.read, billing.invoice, billing.payment, billing.read, billing.refund, billing.saas.pay, billing.saas.read, billing.saas.refund_request, branch.manage, branch.read, checkin.manage, comms.consent, comms.manage, comms.read, comms.send, discharge, encounter.read, encounter.write, expense.manage, expense.read, followup.create, followup.read, followup.write, inventory.manage, inventory.read, lab.import, lab.order, lab.read, lab.release, lab.verify, member.manage, member.read, nursing.read, nursing.write, org.manage, org.offboard, org.read, org.transfer_ownership, patient.merge, patient.read, patient.write, pharmacy.dispense, pharmacy.manage, pharmacy.read, prescription.read, prescription.sign, queue.manage, queue.read, report.read, setup.manage, setup.read, subscription.manage, subscription.read, support.read, support.write |
| `pharmacist` | ai.forecast.read, ai.knowledge.use, bed.read, branch.read, inventory.read, lab.read, member.read, org.read, patient.read, pharmacy.dispense, pharmacy.manage, pharmacy.read, prescription.read, setup.read |
| `receptionist` | admission.manage, ai.forecast.read, ai.knowledge.use, appointment.read, appointment.write, bed.read, billing.invoice, billing.payment, billing.read, branch.read, checkin.manage, comms.consent, comms.read, comms.send, followup.read, followup.write, lab.read, member.read, org.read, patient.read, patient.write, pharmacy.read, prescription.read, queue.manage, queue.read, setup.read |
| `support` | org.read, support.read, support.write |
