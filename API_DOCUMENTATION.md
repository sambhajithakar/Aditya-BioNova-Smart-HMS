# API Documentation

> **Generated file.** Everything below the "Endpoints" heading is produced by
> `scripts/generate_api_docs.py` from `packages/contracts/openapi.json`
> (which `scripts/generate-contracts.sh` exports from the FastAPI app).
> Do not edit by hand: regenerate with
> `scripts/generate-contracts.sh && python3 scripts/generate_api_docs.py`.
> CI (`contracts` job) fails when this file is stale. The overview section is
> maintained inside the generator script.

Interactive docs (development only): `http://127.0.0.1:8000/api/v1/docs`.
Machine-readable spec: `packages/contracts/openapi.json`.

## Overview

### Base path and format

- Every endpoint lives under **`/api/v1`**. JSON request and response bodies
  (`Content-Type: application/json`).
- Every response carries `X-Request-ID` (the correlation id). A client may send
  its own `X-Request-ID`; otherwise the server generates one.
- The tenant (organization) is **never** taken from the client. It comes from
  the verified access token; there is no `organization_id` request parameter.
- List endpoints page with `limit` / `offset` query parameters.

### Authentication

- `Authorization: Bearer <access_token>`. Access tokens are short-lived JWTs
  (**30 minutes** by default, `ACCESS_TOKEN_TTL_SECONDS=1800`) bound to a
  server-side session; logout or session
  revocation invalidates them immediately.
- Refresh tokens are **rotating**: `POST /api/v1/auth/refresh` returns a new
  pair and retires the old refresh token. Replaying a retired refresh token
  revokes the whole session family (reuse detection) and is audited.
- **MFA challenge flow.** When the account has TOTP enabled,
  `POST /api/v1/auth/login` (and `POST /api/v1/auth/invitations/accept`)
  answers `200` with `{"mfa_required": true, "mfa_token": "...",
  "methods": ["totp"], "expires_in": ...}` instead of a token pair. The client
  then calls `POST /api/v1/auth/mfa/verify` with the `mfa_token` and a TOTP or
  recovery code to obtain the session.
- "Permission" in the tables below is the RBAC permission key the caller's
  role must hold (`403 Missing permission: <key>` otherwise); handlers may
  apply further business rules on top. "authenticated"
  means any valid session; "public" means no token is required; "-" means the
  generator could not determine it statically.

### Idempotency

Create endpoints marked **Idempotency-Key: yes** accept an optional
`Idempotency-Key` header. A retry with the same key and the same payload
replays the stored response; the same key with a different payload returns
`409`. Keys are scoped to the organization.

### Errors

Error bodies are JSON with a `detail` field (a string, or a list of field
errors for `422`). Errors raised by the database layer (trigger guards,
constraint violations) and `500`s use `{"detail": ..., "correlation_id": "..."}`;
for all errors the correlation id is also in the `X-Request-ID` response
header. Status codes used across the API:

- **400** - invalid or expired one-time token (password reset link,
  invitation).
- **401** - missing/invalid/expired access token or revoked session; login
  failures are generic (no account enumeration).
- **403** - authenticated but the role lacks the required permission, or the
  action is not allowed for the role.
- **404** - not found. **Resources of another tenant also return 404**
  (never 403), so ids cannot be probed across organizations.
- **409** - conflict: duplicates, Idempotency-Key reuse with a different
  payload, state-machine / append-only violations raised by database
  triggers, concurrent update (retry).
- **422** - validation error (request schema, or database value
  constraints such as NOT NULL / length / range).
- **429** - rate limited (login, MFA, password reset, ...); the response
  carries a `Retry-After` header (seconds).
- **500** - internal error; the body contains only a generic message and
  `correlation_id`.

### Development-only endpoints

`GET /api/v1/dev/outbox` (tag `dev`) exposes the outbound message outbox
(password reset, invitation e-mails) so they can be read without a mail
server. The router is mounted **only when the environment is development**;
it does not exist in staging or production builds.

## Endpoints

Spec: **Aditya BioNova Smart HMS API** version `0.1.0-m1`, OpenAPI 3.1.0. 257 operations in 35 tags.

### Summary

| Tag | Method | Path | Permission | Idempotency-Key |
|---|---|---|---|---|
| ai | POST | `/api/v1/ai/copilot/ask` | `ai.copilot.use` |  |
| ai | GET | `/api/v1/ai/copilot/catalog` | `ai.copilot.use` |  |
| ai | GET | `/api/v1/ai/requests` | `ai.audit.read` |  |
| ai | GET | `/api/v1/ai/settings` | `ai.settings.manage` |  |
| ai | PATCH | `/api/v1/ai/settings` | `ai.settings.manage` |  |
| ai | GET | `/api/v1/ai/usage` | `ai.audit.read` |  |
| ai-agents | GET | `/api/v1/ai/agents/catalog` | `ai.agents.use` |  |
| ai-agents | GET | `/api/v1/ai/agents/proposals` | `ai.agents.use` |  |
| ai-agents | GET | `/api/v1/ai/agents/proposals/{pid}` | `ai.agents.use` |  |
| ai-agents | POST | `/api/v1/ai/agents/proposals/{pid}/approve` | `ai.agents.approve` |  |
| ai-agents | POST | `/api/v1/ai/agents/proposals/{pid}/reject` | `ai.agents.approve` |  |
| ai-agents | GET | `/api/v1/ai/agents/reorder-drafts` | `ai.agents.use` |  |
| ai-agents | POST | `/api/v1/ai/agents/run` | `ai.agents.use` |  |
| ai-agents | GET | `/api/v1/ai/agents/tasks` | `appointment.read` |  |
| ai-agents | POST | `/api/v1/ai/agents/tasks/{task_id}/done` | `appointment.write` |  |
| ai-forecast | GET | `/api/v1/ai/forecast/beds` | `ai.forecast.read` |  |
| ai-forecast | GET | `/api/v1/ai/forecast/inventory` | `ai.forecast.read` |  |
| ai-forecast | GET | `/api/v1/ai/forecast/model-runs` | `ai.forecast.read` |  |
| ai-forecast | GET | `/api/v1/ai/forecast/no-show` | `ai.forecast.read` |  |
| ai-forecast | GET | `/api/v1/ai/forecast/opd` | `ai.forecast.read` |  |
| ai-forecast | GET | `/api/v1/ai/forecast/pharmacy` | `ai.forecast.read` |  |
| ai-governance | GET | `/api/v1/ai/governance/usage` | `ai.audit.read` |  |
| ai-knowledge | POST | `/api/v1/ai/knowledge/ask` | `ai.knowledge.use` |  |
| ai-knowledge | GET | `/api/v1/ai/knowledge/documents` | `ai.knowledge.use` |  |
| ai-knowledge | POST | `/api/v1/ai/knowledge/documents` | `ai.knowledge.manage` |  |
| ai-knowledge | GET | `/api/v1/ai/knowledge/documents/{doc_id}` | `ai.knowledge.use` |  |
| ai-knowledge | POST | `/api/v1/ai/knowledge/documents/{doc_id}/approve` | `ai.knowledge.manage` |  |
| ai-knowledge | POST | `/api/v1/ai/knowledge/documents/{doc_id}/archive` | `ai.knowledge.manage` |  |
| ai-knowledge | GET | `/api/v1/ai/knowledge/stats` | `ai.knowledge.use` |  |
| ai-scribe | GET | `/api/v1/ai/scribe/info` | `ai.scribe.use` |  |
| ai-scribe | GET | `/api/v1/ai/scribe/sessions` | `ai.scribe.use` |  |
| ai-scribe | POST | `/api/v1/ai/scribe/sessions` | `ai.scribe.use` |  |
| ai-scribe | GET | `/api/v1/ai/scribe/sessions/{sid}` | `ai.scribe.use` |  |
| ai-scribe | POST | `/api/v1/ai/scribe/sessions/{sid}/accept` | `ai.scribe.use` |  |
| ai-scribe | POST | `/api/v1/ai/scribe/sessions/{sid}/discard` | `ai.scribe.use` |  |
| ai-scribe | POST | `/api/v1/ai/scribe/sessions/{sid}/transcript` | `ai.scribe.use` |  |
| appointments | GET | `/api/v1/appointments` | `appointment.read` |  |
| appointments | POST | `/api/v1/appointments` | `appointment.write` |  |
| appointments | GET | `/api/v1/appointments/slots` | `appointment.read` |  |
| appointments | GET | `/api/v1/appointments/{appointment_id}` | `appointment.read` |  |
| appointments | PATCH | `/api/v1/appointments/{appointment_id}` | `appointment.write` |  |
| audit | GET | `/api/v1/audit-events` | `audit.read` |  |
| auth | POST | `/api/v1/auth/invitations/accept` | public |  |
| auth | POST | `/api/v1/auth/login` | public |  |
| auth | POST | `/api/v1/auth/logout` | authenticated |  |
| auth | GET | `/api/v1/auth/me` | authenticated |  |
| auth | PATCH | `/api/v1/auth/me` | authenticated |  |
| auth | POST | `/api/v1/auth/mfa/disable` | authenticated |  |
| auth | GET | `/api/v1/auth/mfa/status` | authenticated |  |
| auth | POST | `/api/v1/auth/mfa/totp/enable` | authenticated |  |
| auth | POST | `/api/v1/auth/mfa/totp/setup` | authenticated |  |
| auth | POST | `/api/v1/auth/mfa/verify` | public |  |
| auth | POST | `/api/v1/auth/password/change` | authenticated |  |
| auth | POST | `/api/v1/auth/password/forgot` | public |  |
| auth | POST | `/api/v1/auth/password/reset` | public |  |
| auth | POST | `/api/v1/auth/refresh` | public |  |
| auth | POST | `/api/v1/auth/register` | public |  |
| auth | GET | `/api/v1/auth/sessions` | authenticated |  |
| auth | POST | `/api/v1/auth/sessions/revoke-others` | authenticated |  |
| auth | POST | `/api/v1/auth/sessions/{session_id}/revoke` | authenticated |  |
| billing | GET | `/api/v1/billing/invoices` | `billing.read` |  |
| billing | POST | `/api/v1/billing/invoices` | `billing.invoice` | yes |
| billing | GET | `/api/v1/billing/invoices/{invoice_id}` | `billing.read` |  |
| billing | POST | `/api/v1/billing/invoices/{invoice_id}/issue` | `billing.invoice` |  |
| billing | GET | `/api/v1/billing/invoices/{invoice_id}/ledger` | `billing.read` |  |
| billing | POST | `/api/v1/billing/invoices/{invoice_id}/payments` | `billing.payment` | yes |
| billing | GET | `/api/v1/billing/invoices/{invoice_id}/receipt` | `billing.read` |  |
| billing | POST | `/api/v1/billing/invoices/{invoice_id}/void` | `billing.invoice` |  |
| billing | GET | `/api/v1/billing/ledger` | `billing.read` |  |
| billing | POST | `/api/v1/billing/payments/{payment_id}/confirm` | `billing.payment` |  |
| billing | POST | `/api/v1/billing/payments/{payment_id}/fail` | `billing.payment` |  |
| billing | POST | `/api/v1/billing/payments/{payment_id}/refund` | `billing.refund` |  |
| branches | GET | `/api/v1/branches` | `branch.read` |  |
| branches | POST | `/api/v1/branches` | `branch.manage` |  |
| branches | GET | `/api/v1/branches/{branch_id}` | `branch.read` |  |
| branches | PATCH | `/api/v1/branches/{branch_id}` | `branch.manage` |  |
| checkin | POST | `/api/v1/checkin/appointments/{appointment_id}/token` | `checkin.manage` |  |
| checkin | POST | `/api/v1/checkin/confirm` | `checkin.manage` |  |
| checkin | POST | `/api/v1/checkin/kiosk` | `checkin.manage` |  |
| checkin | POST | `/api/v1/checkin/verify` | `checkin.manage` |  |
| communications | GET | `/api/v1/comms/delivery-log` | `comms.read` |  |
| communications | GET | `/api/v1/comms/overview` | `comms.read` |  |
| communications | GET | `/api/v1/comms/patients/{patient_id}` | `patient.read` |  |
| communications | PUT | `/api/v1/comms/patients/{patient_id}/consent` | `comms.consent` |  |
| communications | POST | `/api/v1/comms/patients/{patient_id}/opt-out` | `comms.consent` |  |
| communications | PUT | `/api/v1/comms/patients/{patient_id}/preferences` | `comms.consent` |  |
| communications | GET | `/api/v1/comms/placeholders` | `comms.read` |  |
| communications | POST | `/api/v1/comms/reminders/run` | `comms.send` |  |
| communications | GET | `/api/v1/comms/settings` | `comms.read` |  |
| communications | PUT | `/api/v1/comms/settings` | `comms.manage` |  |
| communications | GET | `/api/v1/comms/templates` | `comms.read` |  |
| communications | POST | `/api/v1/comms/templates` | `comms.manage` |  |
| communications | POST | `/api/v1/comms/templates/preview` | `comms.read` |  |
| communications | PATCH | `/api/v1/comms/templates/{template_id}` | `comms.manage` |  |
| dev | GET | `/api/v1/dev/outbox` | public |  |
| devices | GET | `/api/v1/device-readings` | public |  |
| devices | POST | `/api/v1/device-readings` | `device.capture` |  |
| devices | GET | `/api/v1/device-readings/{reading_id}` | public |  |
| devices | POST | `/api/v1/device-readings/{reading_id}/accept` | `device.review` |  |
| devices | POST | `/api/v1/device-readings/{reading_id}/reject` | `device.review` |  |
| devices | GET | `/api/v1/devices` | `device.read` |  |
| devices | POST | `/api/v1/devices` | `device.manage` |  |
| devices | POST | `/api/v1/devices/{device_id}/retire` | `device.manage` |  |
| devices | POST | `/api/v1/devices/{device_id}/verify-address` | `device.capture` |  |
| encounters | GET | `/api/v1/encounters` | `encounter.read` |  |
| encounters | POST | `/api/v1/encounters` | `encounter.write` |  |
| encounters | GET | `/api/v1/encounters/{encounter_id}` | `encounter.read` |  |
| encounters | PATCH | `/api/v1/encounters/{encounter_id}` | `encounter.write` |  |
| encounters | POST | `/api/v1/encounters/{encounter_id}/complete` | `encounter.write` |  |
| encounters | POST | `/api/v1/encounters/{encounter_id}/diagnoses` | `encounter.write` |  |
| encounters | POST | `/api/v1/encounters/{encounter_id}/vitals` | `encounter.write` |  |
| expenses | GET | `/api/v1/expenses` | `expense.read` |  |
| expenses | POST | `/api/v1/expenses` | `expense.manage` | yes |
| expenses | GET | `/api/v1/expenses/summary` | `expense.read` |  |
| expenses | POST | `/api/v1/expenses/{expense_id}/void` | `expense.manage` |  |
| follow-ups | GET | `/api/v1/follow-ups` | `followup.read` |  |
| follow-ups | POST | `/api/v1/follow-ups` | `followup.create` |  |
| follow-ups | GET | `/api/v1/follow-ups/missed-appointments` | `followup.read` |  |
| follow-ups | POST | `/api/v1/follow-ups/missed-appointments/{appointment_id}/notify` | `comms.send` |  |
| follow-ups | GET | `/api/v1/follow-ups/summary` | `followup.read` |  |
| follow-ups | GET | `/api/v1/follow-ups/{follow_up_id}` | `followup.read` |  |
| follow-ups | POST | `/api/v1/follow-ups/{follow_up_id}/book` | `followup.write` |  |
| follow-ups | POST | `/api/v1/follow-ups/{follow_up_id}/cancel` | `followup.write` |  |
| follow-ups | POST | `/api/v1/follow-ups/{follow_up_id}/complete` | `followup.write` |  |
| follow-ups | POST | `/api/v1/follow-ups/{follow_up_id}/missed` | `followup.write` |  |
| follow-ups | POST | `/api/v1/follow-ups/{follow_up_id}/remind` | `comms.send` |  |
| inventory | GET | `/api/v1/inventory/alerts` | `inventory.read` |  |
| inventory | GET | `/api/v1/inventory/items` | `inventory.read` |  |
| inventory | POST | `/api/v1/inventory/items` | `inventory.manage` |  |
| inventory | PATCH | `/api/v1/inventory/items/{item_id}` | `inventory.manage` |  |
| inventory | POST | `/api/v1/inventory/items/{item_id}/movements` | `inventory.manage` | yes |
| inventory | GET | `/api/v1/inventory/movements` | `inventory.read` |  |
| ipd | GET | `/api/v1/ipd/admissions` | `bed.read` |  |
| ipd | POST | `/api/v1/ipd/admissions` | `admission.manage` | yes |
| ipd | GET | `/api/v1/ipd/admissions/{admission_id}` | `bed.read` |  |
| ipd | POST | `/api/v1/ipd/admissions/{admission_id}/discharge` | `discharge` |  |
| ipd | GET | `/api/v1/ipd/admissions/{admission_id}/nursing` | `nursing.read` |  |
| ipd | POST | `/api/v1/ipd/admissions/{admission_id}/nursing` | `nursing.write` |  |
| ipd | POST | `/api/v1/ipd/admissions/{admission_id}/transfer` | `admission.manage` |  |
| ipd | GET | `/api/v1/ipd/beds` | `bed.read` |  |
| ipd | POST | `/api/v1/ipd/beds` | `bed.manage` |  |
| ipd | PATCH | `/api/v1/ipd/beds/{bed_id}` | `bed.manage` |  |
| ipd | GET | `/api/v1/ipd/wards` | `bed.read` |  |
| ipd | POST | `/api/v1/ipd/wards` | `bed.manage` |  |
| lab | GET | `/api/v1/lab/orders` | `lab.read` |  |
| lab | POST | `/api/v1/lab/orders` | `lab.order` |  |
| lab | GET | `/api/v1/lab/orders/{order_id}` | `lab.read` |  |
| lab | POST | `/api/v1/lab/orders/{order_id}/cancel` | `lab.order` |  |
| lab | POST | `/api/v1/lab/orders/{order_id}/results` | `lab.import` |  |
| lab | POST | `/api/v1/lab/orders/{order_id}/specimens` | `lab.order` |  |
| lab | POST | `/api/v1/lab/results/{result_id}/amend` | `lab.import` |  |
| lab | POST | `/api/v1/lab/results/{result_id}/release` | `lab.release` |  |
| lab | POST | `/api/v1/lab/results/{result_id}/verify` | `lab.verify` |  |
| lab | POST | `/api/v1/lab/specimens/{specimen_id}/reject` | `lab.order` |  |
| lab | GET | `/api/v1/lab/tests` | `lab.read` |  |
| members | GET | `/api/v1/members` | `member.read` |  |
| members | POST | `/api/v1/members` | `member.manage` |  |
| members | GET | `/api/v1/members/invitations` | `member.manage` |  |
| members | POST | `/api/v1/members/invitations` | `member.manage` |  |
| members | POST | `/api/v1/members/invitations/{invitation_id}/revoke` | `member.manage` |  |
| members | PATCH | `/api/v1/members/{membership_id}` | `member.manage` |  |
| members | POST | `/api/v1/members/{membership_id}/sessions/revoke` | `member.manage` |  |
| opd-queue | GET | `/api/v1/opd/queue` | `queue.read` |  |
| opd-queue | POST | `/api/v1/opd/queue` | `queue.manage` | yes |
| opd-queue | POST | `/api/v1/opd/queue/{entry_id}/call` | `queue.manage` |  |
| opd-queue | POST | `/api/v1/opd/queue/{entry_id}/complete` | `queue.manage` |  |
| opd-queue | POST | `/api/v1/opd/queue/{entry_id}/skip` | `queue.manage` |  |
| opd-queue | POST | `/api/v1/opd/queue/{entry_id}/start` | `queue.manage` |  |
| organization | GET | `/api/v1/organization` | `org.read` |  |
| organization | PATCH | `/api/v1/organization` | `org.manage` |  |
| organization | POST | `/api/v1/organization/export` | `org.offboard` |  |
| organization | POST | `/api/v1/organization/offboarding` | `org.offboard` |  |
| organization | DELETE | `/api/v1/organization/offboarding` | `org.offboard` |  |
| organization | GET | `/api/v1/organization/onboarding` | `org.read` |  |
| patients | GET | `/api/v1/patients` | `patient.read` |  |
| patients | POST | `/api/v1/patients` | `patient.write` | yes |
| patients | GET | `/api/v1/patients/{patient_id}` | `patient.read` |  |
| patients | PATCH | `/api/v1/patients/{patient_id}` | `patient.write` |  |
| patients | POST | `/api/v1/patients/{patient_id}/merge` | `patient.merge` |  |
| pharmacy | GET | `/api/v1/pharmacy/dispenses` | `pharmacy.read` |  |
| pharmacy | POST | `/api/v1/pharmacy/dispenses` | `pharmacy.dispense` | yes |
| pharmacy | GET | `/api/v1/pharmacy/stock/alerts` | `pharmacy.read` |  |
| pharmacy | GET | `/api/v1/pharmacy/stock/batches` | `pharmacy.read` |  |
| pharmacy | POST | `/api/v1/pharmacy/stock/batches` | `pharmacy.manage` | yes |
| pharmacy | POST | `/api/v1/pharmacy/stock/batches/{batch_id}/adjust` | `pharmacy.manage` |  |
| pharmacy | GET | `/api/v1/pharmacy/stock/movements` | `pharmacy.read` |  |
| platform | GET | `/api/v1/platform/billing/credit-packs` | - |  |
| platform | PUT | `/api/v1/platform/billing/credit-packs/{code}` | - |  |
| platform | POST | `/api/v1/platform/billing/lifecycle` | - |  |
| platform | GET | `/api/v1/platform/billing/orders` | - |  |
| platform | GET | `/api/v1/platform/billing/reconciliation` | - |  |
| platform | GET | `/api/v1/platform/billing/refunds` | - |  |
| platform | POST | `/api/v1/platform/billing/refunds/{refund_id}/decide` | - |  |
| platform | POST | `/api/v1/platform/billing/refunds/{refund_id}/resume` | - |  |
| platform | GET | `/api/v1/platform/catalog` | public |  |
| platform | GET | `/api/v1/platform/overview` | public |  |
| platform | GET | `/api/v1/platform/plans` | public |  |
| platform | PATCH | `/api/v1/platform/plans/{code}` | public |  |
| platform | PUT | `/api/v1/platform/plans/{code}/features` | public |  |
| platform | PUT | `/api/v1/platform/plans/{code}/limits` | public |  |
| platform | GET | `/api/v1/platform/support/tickets` | public |  |
| platform | GET | `/api/v1/platform/support/tickets/{ticket_id}` | public |  |
| platform | PATCH | `/api/v1/platform/support/tickets/{ticket_id}` | public |  |
| platform | POST | `/api/v1/platform/support/tickets/{ticket_id}/messages` | public |  |
| platform | GET | `/api/v1/platform/tenants` | public |  |
| platform | GET | `/api/v1/platform/tenants/{org_id}` | public |  |
| platform | PATCH | `/api/v1/platform/tenants/{org_id}` | public |  |
| platform | PUT | `/api/v1/platform/tenants/{org_id}/subscription` | public |  |
| prescriptions | GET | `/api/v1/prescriptions` | `prescription.read` |  |
| prescriptions | POST | `/api/v1/prescriptions` | `prescription.sign` | yes |
| prescriptions | GET | `/api/v1/prescriptions/drugs` | `prescription.read` |  |
| prescriptions | GET | `/api/v1/prescriptions/{rx_id}` | `prescription.read` |  |
| prescriptions | POST | `/api/v1/prescriptions/{rx_id}/amend` | `prescription.sign` |  |
| prescriptions | POST | `/api/v1/prescriptions/{rx_id}/sign` | `prescription.sign` |  |
| prescriptions | POST | `/api/v1/prescriptions/{rx_id}/warnings` | `prescription.sign` |  |
| printers | GET | `/api/v1/setup/printers` | `setup.read` |  |
| printers | POST | `/api/v1/setup/printers` | `setup.manage` |  |
| printers | GET | `/api/v1/setup/printers/defaults` | `setup.read` |  |
| printers | GET | `/api/v1/setup/printers/{profile_id}` | `setup.read` |  |
| printers | PATCH | `/api/v1/setup/printers/{profile_id}` | `setup.manage` |  |
| printers | DELETE | `/api/v1/setup/printers/{profile_id}` | `setup.manage` |  |
| reports | GET | `/api/v1/reports/summary` | `report.read` |  |
| saas-billing | GET | `/api/v1/saas/catalog` | - |  |
| saas-billing | GET | `/api/v1/saas/credits` | - |  |
| saas-billing | GET | `/api/v1/saas/invoices` | - |  |
| saas-billing | GET | `/api/v1/saas/invoices/{invoice_id}` | - |  |
| saas-billing | GET | `/api/v1/saas/orders` | - |  |
| saas-billing | POST | `/api/v1/saas/orders` | - | yes |
| saas-billing | POST | `/api/v1/saas/orders/{order_id}/retry` | - | yes |
| saas-billing | POST | `/api/v1/saas/orders/{order_id}/simulate` | - |  |
| saas-billing | POST | `/api/v1/saas/orders/{order_id}/verify` | - |  |
| saas-billing | GET | `/api/v1/saas/payments` | - |  |
| saas-billing | GET | `/api/v1/saas/refunds` | - |  |
| saas-billing | POST | `/api/v1/saas/refunds` | - |  |
| saas-billing | POST | `/api/v1/saas/webhooks/razorpay` | - |  |
| setup | GET | `/api/v1/setup/branches/{branch_id}/working-hours` | `setup.read` |  |
| setup | PUT | `/api/v1/setup/branches/{branch_id}/working-hours` | `setup.manage` |  |
| setup | GET | `/api/v1/setup/fees` | `setup.read` |  |
| setup | PUT | `/api/v1/setup/fees/default` | `setup.manage` |  |
| setup | GET | `/api/v1/setup/fees/effective` | `setup.read` |  |
| setup | PUT | `/api/v1/setup/fees/providers/{user_id}` | `setup.manage` |  |
| setup | DELETE | `/api/v1/setup/fees/providers/{user_id}` | `setup.manage` |  |
| setup | GET | `/api/v1/setup/settings` | `setup.read` |  |
| setup | PATCH | `/api/v1/setup/settings` | `setup.manage` |  |
| setup | GET | `/api/v1/setup/wizard` | `setup.read` |  |
| setup | PATCH | `/api/v1/setup/wizard` | `setup.manage` |  |
| setup | POST | `/api/v1/setup/wizard/steps/{step_key}` | `setup.manage` |  |
| subscription | GET | `/api/v1/plans` | public |  |
| subscription | GET | `/api/v1/subscription` | `subscription.read` |  |
| subscription | POST | `/api/v1/subscription/change-request` | `subscription.manage` |  |
| support | GET | `/api/v1/support/tickets` | `support.read` |  |
| support | POST | `/api/v1/support/tickets` | `support.write` |  |
| support | GET | `/api/v1/support/tickets/{ticket_id}` | `support.read` |  |
| support | POST | `/api/v1/support/tickets/{ticket_id}/close` | `support.write` |  |
| support | POST | `/api/v1/support/tickets/{ticket_id}/messages` | `support.write` |  |
| system | GET | `/api/v1/health` | public |  |
| system | GET | `/api/v1/health/ready` | public |  |

### ai

#### `POST /api/v1/ai/copilot/ask`

**Ask**

- Permission: `ai.copilot.use`
- operationId: `ask_api_v1_ai_copilot_ask_post`
- Request body: `CopilotAskIn`
- Response: `200 CopilotAnswerOut`

#### `GET /api/v1/ai/copilot/catalog`

**Catalog**

- Permission: `ai.copilot.use`
- operationId: `catalog_api_v1_ai_copilot_catalog_get`
- Request body: -
- Response: `200 list[CopilotCatalogEntry]`

#### `GET /api/v1/ai/requests`

**List Requests**

- Permission: `ai.audit.read`
- operationId: `list_requests_api_v1_ai_requests_get`
- Request body: -
- Response: `200 list[AiRequestOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |

#### `GET /api/v1/ai/settings`

**Get Ai Settings**

- Permission: `ai.settings.manage`
- operationId: `get_ai_settings_api_v1_ai_settings_get`
- Request body: -
- Response: `200 AiSettingsOut`

#### `PATCH /api/v1/ai/settings`

**Update Ai Settings**

- Permission: `ai.settings.manage`
- operationId: `update_ai_settings_api_v1_ai_settings_patch`
- Request body: `AiSettingsIn`
- Response: `200 AiSettingsOut`

#### `GET /api/v1/ai/usage`

**Usage**

- Permission: `ai.audit.read`
- operationId: `usage_api_v1_ai_usage_get`
- Request body: -
- Response: `200 AiUsageOut`

### ai-agents

#### `GET /api/v1/ai/agents/catalog`

**Catalog**

- Permission: `ai.agents.use`
- operationId: `catalog_api_v1_ai_agents_catalog_get`
- Request body: -
- Response: `200 list[object]`

#### `GET /api/v1/ai/agents/proposals`

**List Proposals**

- Permission: `ai.agents.use`
- operationId: `list_proposals_api_v1_ai_agents_proposals_get`
- Request body: -
- Response: `200 list[ProposalOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `status` | query | string \| null | no |

#### `GET /api/v1/ai/agents/proposals/{pid}`

**Get Proposal**

- Permission: `ai.agents.use`
- operationId: `get_proposal_api_v1_ai_agents_proposals__pid__get`
- Request body: -
- Response: `200 object`

| Parameter | In | Type | Required |
|---|---|---|---|
| `pid` | path | string(uuid) | yes |

#### `POST /api/v1/ai/agents/proposals/{pid}/approve`

**Approve**

- Permission: `ai.agents.approve`
- operationId: `approve_api_v1_ai_agents_proposals__pid__approve_post`
- Request body: `ProposalDecisionIn`
- Response: `200 ProposalOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `pid` | path | string(uuid) | yes |

#### `POST /api/v1/ai/agents/proposals/{pid}/reject`

**Reject**

- Permission: `ai.agents.approve`
- operationId: `reject_api_v1_ai_agents_proposals__pid__reject_post`
- Request body: `ProposalDecisionIn`
- Response: `200 ProposalOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `pid` | path | string(uuid) | yes |

#### `GET /api/v1/ai/agents/reorder-drafts`

**List Reorder Drafts**

- Permission: `ai.agents.use`
- operationId: `list_reorder_drafts_api_v1_ai_agents_reorder_drafts_get`
- Request body: -
- Response: `200 list[ReorderDraftOut]`

#### `POST /api/v1/ai/agents/run`

**Run Agent**

- Permission: `ai.agents.use`
- operationId: `run_agent_api_v1_ai_agents_run_post`
- Request body: `AgentRunIn`
- Response: `200 AgentRunOut`

#### `GET /api/v1/ai/agents/tasks`

**List Tasks**

- Permission: `appointment.read`
- operationId: `list_tasks_api_v1_ai_agents_tasks_get`
- Request body: -
- Response: `200 list[StaffTaskOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string | no |

#### `POST /api/v1/ai/agents/tasks/{task_id}/done`

**Complete Task**

- Permission: `appointment.write`
- operationId: `complete_task_api_v1_ai_agents_tasks__task_id__done_post`
- Request body: -
- Response: `200 StaffTaskOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `task_id` | path | string(uuid) | yes |

### ai-forecast

#### `GET /api/v1/ai/forecast/beds`

**Beds**

- Permission: `ai.forecast.read`
- operationId: `beds_api_v1_ai_forecast_beds_get`
- Request body: -
- Response: `200 ForecastOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) \| null | no |
| `horizon` | query | integer | no |

#### `GET /api/v1/ai/forecast/inventory`

**Inventory**

- Permission: `ai.forecast.read`
- operationId: `inventory_api_v1_ai_forecast_inventory_get`
- Request body: -
- Response: `200 list[ForecastOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) \| null | no |
| `lead_time_days` | query | integer | no |
| `review_days` | query | integer | no |

#### `GET /api/v1/ai/forecast/model-runs`

**Model Runs**

- Permission: `ai.forecast.read`
- operationId: `model_runs_api_v1_ai_forecast_model_runs_get`
- Request body: -
- Response: `200 list[ModelRunOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `kind` | query | string \| null | no |
| `limit` | query | integer | no |

#### `GET /api/v1/ai/forecast/no-show`

**No Show**

- Permission: `ai.forecast.read`
- operationId: `no_show_api_v1_ai_forecast_no_show_get`
- Request body: -
- Response: `200 ForecastOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) \| null | no |
| `days_ahead` | query | integer | no |

#### `GET /api/v1/ai/forecast/opd`

**Opd**

- Permission: `ai.forecast.read`
- operationId: `opd_api_v1_ai_forecast_opd_get`
- Request body: -
- Response: `200 list[ForecastOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) \| null | no |
| `horizon` | query | integer | no |

#### `GET /api/v1/ai/forecast/pharmacy`

**Pharmacy**

- Permission: `ai.forecast.read`
- operationId: `pharmacy_api_v1_ai_forecast_pharmacy_get`
- Request body: -
- Response: `200 list[ForecastOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) \| null | no |
| `lead_time_days` | query | integer | no |
| `review_days` | query | integer | no |

### ai-governance

#### `GET /api/v1/ai/governance/usage`

**Usage Breakdown**

- Permission: `ai.audit.read`
- operationId: `usage_breakdown_api_v1_ai_governance_usage_get`
- Request body: -
- Response: `200 UsageBreakdownOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `period` | query | string \| null | no |

### ai-knowledge

#### `POST /api/v1/ai/knowledge/ask`

**Ask**

- Permission: `ai.knowledge.use`
- operationId: `ask_api_v1_ai_knowledge_ask_post`
- Request body: `KbAskIn`
- Response: `200 KbAnswerOut`

#### `GET /api/v1/ai/knowledge/documents`

**List Documents**

- Permission: `ai.knowledge.use`
- operationId: `list_documents_api_v1_ai_knowledge_documents_get`
- Request body: -
- Response: `200 list[KbDocumentOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string \| null | no |

#### `POST /api/v1/ai/knowledge/documents`

**Upload**

- Permission: `ai.knowledge.manage`
- operationId: `upload_api_v1_ai_knowledge_documents_post`
- Request body: `KbDocumentIn`
- Response: `201 KbDocumentOut`

#### `GET /api/v1/ai/knowledge/documents/{doc_id}`

**Get Document**

- Permission: `ai.knowledge.use`
- operationId: `get_document_api_v1_ai_knowledge_documents__doc_id__get`
- Request body: -
- Response: `200 KbDocumentDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `doc_id` | path | string(uuid) | yes |

#### `POST /api/v1/ai/knowledge/documents/{doc_id}/approve`

**Approve**

- Permission: `ai.knowledge.manage`
- operationId: `approve_api_v1_ai_knowledge_documents__doc_id__approve_post`
- Request body: -
- Response: `200 KbDocumentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `doc_id` | path | string(uuid) | yes |

#### `POST /api/v1/ai/knowledge/documents/{doc_id}/archive`

**Archive**

- Permission: `ai.knowledge.manage`
- operationId: `archive_api_v1_ai_knowledge_documents__doc_id__archive_post`
- Request body: -
- Response: `200 KbDocumentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `doc_id` | path | string(uuid) | yes |

#### `GET /api/v1/ai/knowledge/stats`

**Stats**

- Permission: `ai.knowledge.use`
- operationId: `stats_api_v1_ai_knowledge_stats_get`
- Request body: -
- Response: `200 object`

### ai-scribe

#### `GET /api/v1/ai/scribe/info`

**Info**

- Permission: `ai.scribe.use`
- operationId: `info_api_v1_ai_scribe_info_get`
- Request body: -
- Response: `200 object`

#### `GET /api/v1/ai/scribe/sessions`

**List Sessions**

- Permission: `ai.scribe.use`
- operationId: `list_sessions_api_v1_ai_scribe_sessions_get`
- Request body: -
- Response: `200 list[ScribeSessionOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `encounter_id` | query | string(uuid) | yes |

#### `POST /api/v1/ai/scribe/sessions`

**Start**

- Permission: `ai.scribe.use`
- operationId: `start_api_v1_ai_scribe_sessions_post`
- Request body: `ScribeSessionIn`
- Response: `201 ScribeSessionOut`

#### `GET /api/v1/ai/scribe/sessions/{sid}`

**Get Session**

- Permission: `ai.scribe.use`
- operationId: `get_session_api_v1_ai_scribe_sessions__sid__get`
- Request body: -
- Response: `200 ScribeSessionOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `sid` | path | string(uuid) | yes |

#### `POST /api/v1/ai/scribe/sessions/{sid}/accept`

**Accept**

- Permission: `ai.scribe.use`
- operationId: `accept_api_v1_ai_scribe_sessions__sid__accept_post`
- Request body: `ScribeAcceptIn`
- Response: `200 ScribeSessionOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `sid` | path | string(uuid) | yes |

#### `POST /api/v1/ai/scribe/sessions/{sid}/discard`

**Discard**

- Permission: `ai.scribe.use`
- operationId: `discard_api_v1_ai_scribe_sessions__sid__discard_post`
- Request body: -
- Response: `200 ScribeSessionOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `sid` | path | string(uuid) | yes |

#### `POST /api/v1/ai/scribe/sessions/{sid}/transcript`

**Transcript**

- Permission: `ai.scribe.use`
- operationId: `transcript_api_v1_ai_scribe_sessions__sid__transcript_post`
- Request body: `ScribeTranscriptIn`
- Response: `200 ScribeSessionOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `sid` | path | string(uuid) | yes |

### appointments

#### `GET /api/v1/appointments`

**List Appointments**

- Permission: `appointment.read`
- operationId: `list_appointments_api_v1_appointments_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `from_date` | query | string(date-time) \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `patient_id` | query | string(uuid) \| null | no |
| `status_filter` | query | string \| null | no |
| `to_date` | query | string(date-time) \| null | no |

#### `POST /api/v1/appointments`

**Create Appointment**

- Permission: `appointment.write`
- operationId: `create_appointment_api_v1_appointments_post`
- Request body: `AppointmentIn`
- Response: `201 AppointmentOut`

#### `GET /api/v1/appointments/slots`

**Suggest Slots**

- Permission: `appointment.read`
- operationId: `suggest_slots_api_v1_appointments_slots_get`
- Request body: -
- Response: `200 SlotsOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) | yes |
| `date` | query | string(date) | yes |
| `provider_user_id` | query | string(uuid) \| null | no |

#### `GET /api/v1/appointments/{appointment_id}`

**Get Appointment**

- Permission: `appointment.read`
- operationId: `get_appointment_api_v1_appointments__appointment_id__get`
- Request body: -
- Response: `200 AppointmentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `appointment_id` | path | string(uuid) | yes |

#### `PATCH /api/v1/appointments/{appointment_id}`

**Update Appointment**

- Permission: `appointment.write`
- operationId: `update_appointment_api_v1_appointments__appointment_id__patch`
- Request body: `AppointmentUpdateIn`
- Response: `200 AppointmentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `appointment_id` | path | string(uuid) | yes |

### audit

#### `GET /api/v1/audit-events`

**List Audit Events**

- Permission: `audit.read`
- operationId: `list_audit_events_api_v1_audit_events_get`
- Request body: -
- Response: `200 Page`

| Parameter | In | Type | Required |
|---|---|---|---|
| `action` | query | string \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |

### auth

#### `POST /api/v1/auth/invitations/accept`

**Accept Invitation** - Join an organization from an e-mailed invitation.

- Permission: public
- operationId: `accept_invitation_api_v1_auth_invitations_accept_post`
- Request body: `InvitationAcceptIn`
- Response: `200 AuthSessionOut | MfaChallengeOut`

#### `POST /api/v1/auth/login`

**Login**

- Permission: public
- operationId: `login_api_v1_auth_login_post`
- Request body: `LoginIn`
- Response: `200 AuthSessionOut | MfaChallengeOut`

#### `POST /api/v1/auth/logout`

**Logout**

- Permission: authenticated
- operationId: `logout_api_v1_auth_logout_post`
- Request body: -
- Response: `200 object`

#### `GET /api/v1/auth/me`

**Me**

- Permission: authenticated
- operationId: `me_api_v1_auth_me_get`
- Request body: -
- Response: `200 MeOut`

#### `PATCH /api/v1/auth/me`

**Update Me** - Self-service profile: display name and professional registration

- Permission: authenticated
- operationId: `update_me_api_v1_auth_me_patch`
- Request body: `ProfileUpdateIn`
- Response: `200 MeOut`

#### `POST /api/v1/auth/mfa/disable`

**Mfa Disable**

- Permission: authenticated
- operationId: `mfa_disable_api_v1_auth_mfa_disable_post`
- Request body: `MfaDisableIn`
- Response: `200 object`

#### `GET /api/v1/auth/mfa/status`

**Mfa Status**

- Permission: authenticated
- operationId: `mfa_status_api_v1_auth_mfa_status_get`
- Request body: -
- Response: `200 MfaStatusOut`

#### `POST /api/v1/auth/mfa/totp/enable`

**Totp Enable**

- Permission: authenticated
- operationId: `totp_enable_api_v1_auth_mfa_totp_enable_post`
- Request body: `TotpCodeIn`
- Response: `200 RecoveryCodesOut`

#### `POST /api/v1/auth/mfa/totp/setup`

**Totp Setup** - Start enrolment: a pending seed that becomes active only once a code

- Permission: authenticated
- operationId: `totp_setup_api_v1_auth_mfa_totp_setup_post`
- Request body: -
- Response: `200 TotpSetupOut`

#### `POST /api/v1/auth/mfa/verify`

**Mfa Verify** - Second login step: exchange an MFA challenge + code for a session.

- Permission: public
- operationId: `mfa_verify_api_v1_auth_mfa_verify_post`
- Request body: `MfaVerifyIn`
- Response: `200 AuthSessionOut`

#### `POST /api/v1/auth/password/change`

**Password Change**

- Permission: authenticated
- operationId: `password_change_api_v1_auth_password_change_post`
- Request body: `PasswordChangeIn`
- Response: `200 object`

#### `POST /api/v1/auth/password/forgot`

**Password Forgot** - Always 202, whether or not the e-mail is registered.

- Permission: public
- operationId: `password_forgot_api_v1_auth_password_forgot_post`
- Request body: `PasswordForgotIn`
- Response: `202 object`

#### `POST /api/v1/auth/password/reset`

**Password Reset**

- Permission: public
- operationId: `password_reset_api_v1_auth_password_reset_post`
- Request body: `PasswordResetIn`
- Response: `200 object`

#### `POST /api/v1/auth/refresh`

**Refresh** - Rotate the refresh token. Replaying an already-rotated token revokes

- Permission: public
- operationId: `refresh_api_v1_auth_refresh_post`
- Request body: `RefreshIn`
- Response: `200 TokenPair`

#### `POST /api/v1/auth/register`

**Register** - Onboard a new clinic/organization with its owner account.

- Permission: public
- operationId: `register_api_v1_auth_register_post`
- Request body: `RegisterIn`
- Response: `201 AuthSessionOut`

#### `GET /api/v1/auth/sessions`

**List Sessions**

- Permission: authenticated
- operationId: `list_sessions_api_v1_auth_sessions_get`
- Request body: -
- Response: `200 list[SessionOut]`

#### `POST /api/v1/auth/sessions/revoke-others`

**Revoke Other Sessions**

- Permission: authenticated
- operationId: `revoke_other_sessions_api_v1_auth_sessions_revoke_others_post`
- Request body: -
- Response: `200 object`

#### `POST /api/v1/auth/sessions/{session_id}/revoke`

**Revoke Session**

- Permission: authenticated
- operationId: `revoke_session_api_v1_auth_sessions__session_id__revoke_post`
- Request body: -
- Response: `200 object`

| Parameter | In | Type | Required |
|---|---|---|---|
| `session_id` | path | string(uuid) | yes |

### billing

#### `GET /api/v1/billing/invoices`

**List Invoices**

- Permission: `billing.read`
- operationId: `list_invoices_api_v1_billing_invoices_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_status` | query | string \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `patient_id` | query | string(uuid) \| null | no |

#### `POST /api/v1/billing/invoices`

**Create Invoice**

- Permission: `billing.invoice`
- operationId: `create_invoice_api_v1_billing_invoices_post`
- Idempotency-Key: supported
- Request body: `InvoiceIn`
- Response: `201 InvoiceDetailOut`

#### `GET /api/v1/billing/invoices/{invoice_id}`

**Get Invoice**

- Permission: `billing.read`
- operationId: `get_invoice_api_v1_billing_invoices__invoice_id__get`
- Request body: -
- Response: `200 InvoiceDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | string(uuid) | yes |

#### `POST /api/v1/billing/invoices/{invoice_id}/issue`

**Issue Invoice**

- Permission: `billing.invoice`
- operationId: `issue_invoice_api_v1_billing_invoices__invoice_id__issue_post`
- Request body: -
- Response: `200 InvoiceDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | string(uuid) | yes |

#### `GET /api/v1/billing/invoices/{invoice_id}/ledger`

**Invoice Ledger**

- Permission: `billing.read`
- operationId: `invoice_ledger_api_v1_billing_invoices__invoice_id__ledger_get`
- Request body: -
- Response: `200 list[LedgerEntryOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | string(uuid) | yes |

#### `POST /api/v1/billing/invoices/{invoice_id}/payments`

**Record Payment**

- Permission: `billing.payment`
- operationId: `record_payment_api_v1_billing_invoices__invoice_id__payments_post`
- Idempotency-Key: supported
- Request body: `PaymentIn`
- Response: `201 app__schemas__PaymentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | string(uuid) | yes |

#### `GET /api/v1/billing/invoices/{invoice_id}/receipt`

**Invoice Receipt** - Receipt payload for the printable A4/A5 view (trilingual in web).

- Permission: `billing.read`
- operationId: `invoice_receipt_api_v1_billing_invoices__invoice_id__receipt_get`
- Request body: -
- Response: `200 ReceiptOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | string(uuid) | yes |

#### `POST /api/v1/billing/invoices/{invoice_id}/void`

**Void Invoice**

- Permission: `billing.invoice`
- operationId: `void_invoice_api_v1_billing_invoices__invoice_id__void_post`
- Request body: -
- Response: `200 InvoiceDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | string(uuid) | yes |

#### `GET /api/v1/billing/ledger`

**Org Ledger**

- Permission: `billing.read`
- operationId: `org_ledger_api_v1_billing_ledger_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `offset` | query | integer | no |

#### `POST /api/v1/billing/payments/{payment_id}/confirm`

**Sandbox Confirm** - Sandbox gateway callback: confirm a pending payment (M7 spike).

- Permission: `billing.payment`
- operationId: `sandbox_confirm_api_v1_billing_payments__payment_id__confirm_post`
- Request body: -
- Response: `200 app__schemas__PaymentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `payment_id` | path | string(uuid) | yes |

#### `POST /api/v1/billing/payments/{payment_id}/fail`

**Sandbox Fail**

- Permission: `billing.payment`
- operationId: `sandbox_fail_api_v1_billing_payments__payment_id__fail_post`
- Request body: -
- Response: `200 app__schemas__PaymentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `payment_id` | path | string(uuid) | yes |

#### `POST /api/v1/billing/payments/{payment_id}/refund`

**Refund Payment**

- Permission: `billing.refund`
- operationId: `refund_payment_api_v1_billing_payments__payment_id__refund_post`
- Request body: `app__schemas__RefundIn`
- Response: `201 app__schemas__RefundOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `payment_id` | path | string(uuid) | yes |

### branches

#### `GET /api/v1/branches`

**List Branches**

- Permission: `branch.read`
- operationId: `list_branches_api_v1_branches_get`
- Request body: -
- Response: `200 list[BranchOut]`

#### `POST /api/v1/branches`

**Create Branch**

- Permission: `branch.manage`
- operationId: `create_branch_api_v1_branches_post`
- Request body: `BranchIn`
- Response: `201 BranchOut`

#### `GET /api/v1/branches/{branch_id}`

**Get Branch** - Identifier manipulation across tenants returns 404 (RLS hides the row).

- Permission: `branch.read`
- operationId: `get_branch_api_v1_branches__branch_id__get`
- Request body: -
- Response: `200 BranchOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | path | string(uuid) | yes |

#### `PATCH /api/v1/branches/{branch_id}`

**Update Branch**

- Permission: `branch.manage`
- operationId: `update_branch_api_v1_branches__branch_id__patch`
- Request body: `BranchUpdateIn`
- Response: `200 BranchOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | path | string(uuid) | yes |

### checkin

#### `POST /api/v1/checkin/appointments/{appointment_id}/token`

**Issue Token** - Create (or replace) the appointment's check-in QR token. The raw token

- Permission: `checkin.manage`
- operationId: `issue_token_api_v1_checkin_appointments__appointment_id__token_post`
- Request body: -
- Response: `201 CheckinIssueOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `appointment_id` | path | string(uuid) | yes |

#### `POST /api/v1/checkin/confirm`

**Confirm**

- Permission: `checkin.manage`
- operationId: `confirm_api_v1_checkin_confirm_post`
- Request body: `CheckinCodeIn`
- Response: `200 CheckinConfirmOut`

#### `POST /api/v1/checkin/kiosk`

**Kiosk** - Self check-in on a reception-owned kiosk: confirm and show ONLY the

- Permission: `checkin.manage`
- operationId: `kiosk_api_v1_checkin_kiosk_post`
- Request body: `CheckinCodeIn`
- Response: `200 KioskCheckinOut`

#### `POST /api/v1/checkin/verify`

**Verify** - Look a scanned code up WITHOUT checking in: minimal context so staff

- Permission: `checkin.manage`
- operationId: `verify_api_v1_checkin_verify_post`
- Request body: `CheckinCodeIn`
- Response: `200 CheckinVerifyOut`

### communications

#### `GET /api/v1/comms/delivery-log`

**Delivery Log**

- Permission: `comms.read`
- operationId: `delivery_log_api_v1_comms_delivery_log_get`
- Request body: -
- Response: `200 DeliveryPage`

| Parameter | In | Type | Required |
|---|---|---|---|
| `appointment_id` | query | string(uuid) \| null | no |
| `channel` | query | string \| null | no |
| `follow_up_id` | query | string(uuid) \| null | no |
| `from_date` | query | string(date-time) \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `patient_id` | query | string(uuid) \| null | no |
| `purpose` | query | string \| null | no |
| `status` | query | string \| null | no |
| `to_date` | query | string(date-time) \| null | no |

#### `GET /api/v1/comms/overview`

**Overview**

- Permission: `comms.read`
- operationId: `overview_api_v1_comms_overview_get`
- Request body: -
- Response: `200 CommsOverview`

#### `GET /api/v1/comms/patients/{patient_id}`

**Patient Comms**

- Permission: `patient.read`
- operationId: `patient_comms_api_v1_comms_patients__patient_id__get`
- Request body: -
- Response: `200 PatientCommsOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `patient_id` | path | string(uuid) | yes |

#### `PUT /api/v1/comms/patients/{patient_id}/consent`

**Put Consent**

- Permission: `comms.consent`
- operationId: `put_consent_api_v1_comms_patients__patient_id__consent_put`
- Request body: `ConsentIn`
- Response: `200 PatientCommsOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `patient_id` | path | string(uuid) | yes |

#### `POST /api/v1/comms/patients/{patient_id}/opt-out`

**Opt Out**

- Permission: `comms.consent`
- operationId: `opt_out_api_v1_comms_patients__patient_id__opt_out_post`
- Request body: `OptOutIn`
- Response: `200 PatientCommsOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `patient_id` | path | string(uuid) | yes |

#### `PUT /api/v1/comms/patients/{patient_id}/preferences`

**Put Preferences**

- Permission: `comms.consent`
- operationId: `put_preferences_api_v1_comms_patients__patient_id__preferences_put`
- Request body: `PreferencesIn`
- Response: `200 PatientCommsOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `patient_id` | path | string(uuid) | yes |

#### `GET /api/v1/comms/placeholders`

**Placeholders**

- Permission: `comms.read`
- operationId: `placeholders_api_v1_comms_placeholders_get`
- Request body: -
- Response: `200 PlaceholderCatalog`

#### `POST /api/v1/comms/reminders/run`

**Run Reminders**

- Permission: `comms.send`
- operationId: `run_reminders_api_v1_comms_reminders_run_post`
- Request body: `ReminderRunIn`
- Response: `200 ReminderRunOut`

#### `GET /api/v1/comms/settings`

**Get Comms Settings**

- Permission: `comms.read`
- operationId: `get_comms_settings_api_v1_comms_settings_get`
- Request body: -
- Response: `200 CommsSettingsOut`

#### `PUT /api/v1/comms/settings`

**Put Comms Settings**

- Permission: `comms.manage`
- operationId: `put_comms_settings_api_v1_comms_settings_put`
- Request body: `CommsSettingsIn`
- Response: `200 CommsSettingsOut`

#### `GET /api/v1/comms/templates`

**List Templates**

- Permission: `comms.read`
- operationId: `list_templates_api_v1_comms_templates_get`
- Request body: -
- Response: `200 list[TemplateOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `channel` | query | string \| null | no |
| `include_inactive` | query | boolean | no |
| `language` | query | string \| null | no |
| `purpose` | query | string \| null | no |

#### `POST /api/v1/comms/templates`

**Create Template**

- Permission: `comms.manage`
- operationId: `create_template_api_v1_comms_templates_post`
- Request body: `TemplateIn`
- Response: `201 TemplateOut`

#### `POST /api/v1/comms/templates/preview`

**Preview**

- Permission: `comms.read`
- operationId: `preview_api_v1_comms_templates_preview_post`
- Request body: `PreviewIn`
- Response: `200 PreviewOut`

#### `PATCH /api/v1/comms/templates/{template_id}`

**Update Template**

- Permission: `comms.manage`
- operationId: `update_template_api_v1_comms_templates__template_id__patch`
- Request body: `TemplateUpdateIn`
- Response: `200 TemplateOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `template_id` | path | string(uuid) | yes |

### dev

#### `GET /api/v1/dev/outbox`

**Outbox**

- Permission: public
- operationId: `outbox_api_v1_dev_outbox_get`
- Request body: -
- Response: `200 list[OutboxMessageOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |

### devices

#### `GET /api/v1/device-readings`

**List Readings**

- Permission: public
- operationId: `list_readings_api_v1_device_readings_get`
- Request body: -
- Response: `200 list[ReadingOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `encounter_id` | query | string(uuid) | yes |
| `status` | query | string | no |

#### `POST /api/v1/device-readings`

**Capture Reading**

- Permission: `device.capture`
- operationId: `capture_reading_api_v1_device_readings_post`
- Request body: `ReadingIn`
- Response: `201 ReadingOut`

#### `GET /api/v1/device-readings/{reading_id}`

**Get Reading**

- Permission: public
- operationId: `get_reading_api_v1_device_readings__reading_id__get`
- Request body: -
- Response: `200 ReadingOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `reading_id` | path | string(uuid) | yes |

#### `POST /api/v1/device-readings/{reading_id}/accept`

**Accept Reading** - The clinician confirms the reading belongs to this patient, now; it is

- Permission: `device.review`
- operationId: `accept_reading_api_v1_device_readings__reading_id__accept_post`
- Request body: `AcceptIn`
- Response: `200 ReadingOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `reading_id` | path | string(uuid) | yes |

#### `POST /api/v1/device-readings/{reading_id}/reject`

**Reject Reading**

- Permission: `device.review`
- operationId: `reject_reading_api_v1_device_readings__reading_id__reject_post`
- Request body: `RejectIn`
- Response: `200 ReadingOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `reading_id` | path | string(uuid) | yes |

#### `GET /api/v1/devices`

**List Devices**

- Permission: `device.read`
- operationId: `list_devices_api_v1_devices_get`
- Request body: -
- Response: `200 list[DeviceOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `include_retired` | query | boolean | no |

#### `POST /api/v1/devices`

**Register Device**

- Permission: `device.manage`
- operationId: `register_device_api_v1_devices_post`
- Request body: `DeviceIn`
- Response: `201 DeviceOut`

#### `POST /api/v1/devices/{device_id}/retire`

**Retire Device**

- Permission: `device.manage`
- operationId: `retire_device_api_v1_devices__device_id__retire_post`
- Request body: -
- Response: `200 DeviceOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `device_id` | path | string(uuid) | yes |

#### `POST /api/v1/devices/{device_id}/verify-address`

**Verify Address** - Pairing on a phone: is the device in hand the registered one? The

- Permission: `device.capture`
- operationId: `verify_address_api_v1_devices__device_id__verify_address_post`
- Request body: `AddressCheckIn`
- Response: `200 AddressCheckOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `device_id` | path | string(uuid) | yes |

### encounters

#### `GET /api/v1/encounters`

**List Encounters**

- Permission: `encounter.read`
- operationId: `list_encounters_api_v1_encounters_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `enc_status` | query | string \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `patient_id` | query | string(uuid) \| null | no |

#### `POST /api/v1/encounters`

**Start Encounter**

- Permission: `encounter.write`
- operationId: `start_encounter_api_v1_encounters_post`
- Request body: `EncounterIn`
- Response: `201 EncounterOut`

#### `GET /api/v1/encounters/{encounter_id}`

**Get Encounter**

- Permission: `encounter.read`
- operationId: `get_encounter_api_v1_encounters__encounter_id__get`
- Request body: -
- Response: `200 EncounterDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `encounter_id` | path | string(uuid) | yes |

#### `PATCH /api/v1/encounters/{encounter_id}`

**Update Encounter**

- Permission: `encounter.write`
- operationId: `update_encounter_api_v1_encounters__encounter_id__patch`
- Request body: `EncounterUpdateIn`
- Response: `200 EncounterOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `encounter_id` | path | string(uuid) | yes |

#### `POST /api/v1/encounters/{encounter_id}/complete`

**Complete Encounter**

- Permission: `encounter.write`
- operationId: `complete_encounter_api_v1_encounters__encounter_id__complete_post`
- Request body: -
- Response: `200 EncounterOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `encounter_id` | path | string(uuid) | yes |

#### `POST /api/v1/encounters/{encounter_id}/diagnoses`

**Add Diagnosis**

- Permission: `encounter.write`
- operationId: `add_diagnosis_api_v1_encounters__encounter_id__diagnoses_post`
- Request body: `DiagnosisIn`
- Response: `201 DiagnosisOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `encounter_id` | path | string(uuid) | yes |

#### `POST /api/v1/encounters/{encounter_id}/vitals`

**Record Vitals**

- Permission: `encounter.write`
- operationId: `record_vitals_api_v1_encounters__encounter_id__vitals_post`
- Request body: `VitalsIn`
- Response: `201 VitalsOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `encounter_id` | path | string(uuid) | yes |

### expenses

#### `GET /api/v1/expenses`

**List Expenses**

- Permission: `expense.read`
- operationId: `list_expenses_api_v1_expenses_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `category` | query | string \| null | no |
| `from` | query | string(date) \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `status` | query | string \| null | no |
| `to` | query | string(date) \| null | no |

#### `POST /api/v1/expenses`

**Record Expense**

- Permission: `expense.manage`
- operationId: `record_expense_api_v1_expenses_post`
- Idempotency-Key: supported
- Request body: `ExpenseIn`
- Response: `201 ExpenseOut`

#### `GET /api/v1/expenses/summary`

**Expense Summary** - Per-category totals for the period (recorded expenses only).

- Permission: `expense.read`
- operationId: `expense_summary_api_v1_expenses_summary_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `from` | query | string(date) \| null | no |
| `to` | query | string(date) \| null | no |

#### `POST /api/v1/expenses/{expense_id}/void`

**Void Expense**

- Permission: `expense.manage`
- operationId: `void_expense_api_v1_expenses__expense_id__void_post`
- Request body: `ExpenseVoidIn`
- Response: `200 ExpenseOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `expense_id` | path | string(uuid) | yes |

### follow-ups

#### `GET /api/v1/follow-ups`

**List Follow Ups**

- Permission: `followup.read`
- operationId: `list_follow_ups_api_v1_follow_ups_get`
- Request body: -
- Response: `200 list[FollowUpOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `bucket` | query | string \| null | no |
| `limit` | query | integer | no |
| `patient_id` | query | string(uuid) \| null | no |
| `status` | query | string \| null | no |

#### `POST /api/v1/follow-ups`

**Create Follow Up**

- Permission: `followup.create`
- operationId: `create_follow_up_api_v1_follow_ups_post`
- Request body: `FollowUpIn`
- Response: `201 FollowUpOut`

#### `GET /api/v1/follow-ups/missed-appointments`

**Missed**

- Permission: `followup.read`
- operationId: `missed_api_v1_follow_ups_missed_appointments_get`
- Request body: -
- Response: `200 list[MissedAppointmentOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `days` | query | integer | no |

#### `POST /api/v1/follow-ups/missed-appointments/{appointment_id}/notify`

**Notify Missed**

- Permission: `comms.send`
- operationId: `notify_missed_api_v1_follow_ups_missed_appointments__appointment_id__notify_post`
- Request body: `NotifyIn`
- Response: `200 SendResultOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `appointment_id` | path | string(uuid) | yes |

#### `GET /api/v1/follow-ups/summary`

**Summary**

- Permission: `followup.read`
- operationId: `summary_api_v1_follow_ups_summary_get`
- Request body: -
- Response: `200 dict[str, integer]`

#### `GET /api/v1/follow-ups/{follow_up_id}`

**Get Follow Up**

- Permission: `followup.read`
- operationId: `get_follow_up_api_v1_follow_ups__follow_up_id__get`
- Request body: -
- Response: `200 FollowUpOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `follow_up_id` | path | string(uuid) | yes |

#### `POST /api/v1/follow-ups/{follow_up_id}/book`

**Book**

- Permission: `followup.write`
- operationId: `book_api_v1_follow_ups__follow_up_id__book_post`
- Request body: `FollowUpBookIn`
- Response: `200 FollowUpOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `follow_up_id` | path | string(uuid) | yes |

#### `POST /api/v1/follow-ups/{follow_up_id}/cancel`

**Cancel**

- Permission: `followup.write`
- operationId: `cancel_api_v1_follow_ups__follow_up_id__cancel_post`
- Request body: `FollowUpActionIn`
- Response: `200 FollowUpOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `follow_up_id` | path | string(uuid) | yes |

#### `POST /api/v1/follow-ups/{follow_up_id}/complete`

**Complete**

- Permission: `followup.write`
- operationId: `complete_api_v1_follow_ups__follow_up_id__complete_post`
- Request body: `FollowUpActionIn`
- Response: `200 FollowUpOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `follow_up_id` | path | string(uuid) | yes |

#### `POST /api/v1/follow-ups/{follow_up_id}/missed`

**Mark Missed**

- Permission: `followup.write`
- operationId: `mark_missed_api_v1_follow_ups__follow_up_id__missed_post`
- Request body: `FollowUpActionIn`
- Response: `200 FollowUpOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `follow_up_id` | path | string(uuid) | yes |

#### `POST /api/v1/follow-ups/{follow_up_id}/remind`

**Remind**

- Permission: `comms.send`
- operationId: `remind_api_v1_follow_ups__follow_up_id__remind_post`
- Request body: `NotifyIn`
- Response: `200 SendResultOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `follow_up_id` | path | string(uuid) | yes |

### inventory

#### `GET /api/v1/inventory/alerts`

**Low Stock Alerts**

- Permission: `inventory.read`
- operationId: `low_stock_alerts_api_v1_inventory_alerts_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `offset` | query | integer | no |

#### `GET /api/v1/inventory/items`

**List Items**

- Permission: `inventory.read`
- operationId: `list_items_api_v1_inventory_items_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) \| null | no |
| `limit` | query | integer | no |
| `low_only` | query | boolean | no |
| `offset` | query | integer | no |
| `q` | query | string \| null | no |
| `status` | query | string \| null | no |

#### `POST /api/v1/inventory/items`

**Create Item**

- Permission: `inventory.manage`
- operationId: `create_item_api_v1_inventory_items_post`
- Request body: `InventoryItemIn`
- Response: `201 InventoryItemOut`

#### `PATCH /api/v1/inventory/items/{item_id}`

**Update Item**

- Permission: `inventory.manage`
- operationId: `update_item_api_v1_inventory_items__item_id__patch`
- Request body: `InventoryItemUpdateIn`
- Response: `200 InventoryItemOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `item_id` | path | string(uuid) | yes |

#### `POST /api/v1/inventory/items/{item_id}/movements`

**Post Movement**

- Permission: `inventory.manage`
- operationId: `post_movement_api_v1_inventory_items__item_id__movements_post`
- Idempotency-Key: supported
- Request body: `InventoryMovementIn`
- Response: `201 InventoryMovementOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `item_id` | path | string(uuid) | yes |

#### `GET /api/v1/inventory/movements`

**List Movements**

- Permission: `inventory.read`
- operationId: `list_movements_api_v1_inventory_movements_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `item_id` | query | string(uuid) \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |

### ipd

#### `GET /api/v1/ipd/admissions`

**List Admissions**

- Permission: `bed.read`
- operationId: `list_admissions_api_v1_ipd_admissions_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `status` | query | string \| null | no |
| `ward_id` | query | string(uuid) \| null | no |

#### `POST /api/v1/ipd/admissions`

**Admit Patient**

- Permission: `admission.manage`
- operationId: `admit_patient_api_v1_ipd_admissions_post`
- Idempotency-Key: supported
- Request body: `AdmissionIn`
- Response: `201 AdmissionOut`

#### `GET /api/v1/ipd/admissions/{admission_id}`

**Get Admission**

- Permission: `bed.read`
- operationId: `get_admission_api_v1_ipd_admissions__admission_id__get`
- Request body: -
- Response: `200 AdmissionOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `admission_id` | path | string(uuid) | yes |

#### `POST /api/v1/ipd/admissions/{admission_id}/discharge`

**Discharge Admission**

- Permission: `discharge`
- operationId: `discharge_admission_api_v1_ipd_admissions__admission_id__discharge_post`
- Request body: `DischargeIn`
- Response: `200 AdmissionOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `admission_id` | path | string(uuid) | yes |

#### `GET /api/v1/ipd/admissions/{admission_id}/nursing`

**List Nursing Records**

- Permission: `nursing.read`
- operationId: `list_nursing_records_api_v1_ipd_admissions__admission_id__nursing_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `admission_id` | path | string(uuid) | yes |
| `limit` | query | integer | no |
| `offset` | query | integer | no |

#### `POST /api/v1/ipd/admissions/{admission_id}/nursing`

**Add Nursing Record**

- Permission: `nursing.write`
- operationId: `add_nursing_record_api_v1_ipd_admissions__admission_id__nursing_post`
- Request body: `NursingRecordIn`
- Response: `201 NursingRecordOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `admission_id` | path | string(uuid) | yes |

#### `POST /api/v1/ipd/admissions/{admission_id}/transfer`

**Transfer Admission**

- Permission: `admission.manage`
- operationId: `transfer_admission_api_v1_ipd_admissions__admission_id__transfer_post`
- Request body: `TransferIn`
- Response: `200 AdmissionOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `admission_id` | path | string(uuid) | yes |

#### `GET /api/v1/ipd/beds`

**List Beds**

- Permission: `bed.read`
- operationId: `list_beds_api_v1_ipd_beds_get`
- Request body: -
- Response: `200 list[BedOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string \| null | no |
| `ward_id` | query | string(uuid) \| null | no |

#### `POST /api/v1/ipd/beds`

**Create Bed**

- Permission: `bed.manage`
- operationId: `create_bed_api_v1_ipd_beds_post`
- Request body: `BedIn`
- Response: `201 BedOut`

#### `PATCH /api/v1/ipd/beds/{bed_id}`

**Update Bed**

- Permission: `bed.manage`
- operationId: `update_bed_api_v1_ipd_beds__bed_id__patch`
- Request body: `BedUpdateIn`
- Response: `200 BedOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `bed_id` | path | string(uuid) | yes |

#### `GET /api/v1/ipd/wards`

**List Wards**

- Permission: `bed.read`
- operationId: `list_wards_api_v1_ipd_wards_get`
- Request body: -
- Response: `200 list[WardOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) \| null | no |

#### `POST /api/v1/ipd/wards`

**Create Ward**

- Permission: `bed.manage`
- operationId: `create_ward_api_v1_ipd_wards_post`
- Request body: `WardIn`
- Response: `201 WardOut`

### lab

#### `GET /api/v1/lab/orders`

**List Lab Orders**

- Permission: `lab.read`
- operationId: `list_lab_orders_api_v1_lab_orders_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `patient_id` | query | string(uuid) \| null | no |
| `status` | query | string \| null | no |

#### `POST /api/v1/lab/orders`

**Post Lab Order**

- Permission: `lab.order`
- operationId: `post_lab_order_api_v1_lab_orders_post`
- Request body: `LabOrderIn`
- Response: `201 LabOrderDetailOut`

#### `GET /api/v1/lab/orders/{order_id}`

**Get Lab Order**

- Permission: `lab.read`
- operationId: `get_lab_order_api_v1_lab_orders__order_id__get`
- Request body: -
- Response: `200 LabOrderDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `order_id` | path | string(uuid) | yes |

#### `POST /api/v1/lab/orders/{order_id}/cancel`

**Post Cancel Order**

- Permission: `lab.order`
- operationId: `post_cancel_order_api_v1_lab_orders__order_id__cancel_post`
- Request body: `CancelLabOrderIn`
- Response: `200 LabOrderDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `order_id` | path | string(uuid) | yes |

#### `POST /api/v1/lab/orders/{order_id}/results`

**Post Import Results**

- Permission: `lab.import`
- operationId: `post_import_results_api_v1_lab_orders__order_id__results_post`
- Request body: `ImportResultsIn`
- Response: `201 LabOrderDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `order_id` | path | string(uuid) | yes |

#### `POST /api/v1/lab/orders/{order_id}/specimens`

**Post Collect Specimen**

- Permission: `lab.order`
- operationId: `post_collect_specimen_api_v1_lab_orders__order_id__specimens_post`
- Request body: `CollectSpecimenIn`
- Response: `201 LabSpecimenOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `order_id` | path | string(uuid) | yes |

#### `POST /api/v1/lab/results/{result_id}/amend`

**Post Amend Result** - Supersede a released result with a NEW audited version (four-eyes:

- Permission: `lab.import`
- operationId: `post_amend_result_api_v1_lab_results__result_id__amend_post`
- Request body: `AmendResultIn`
- Response: `201 LabResultOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `result_id` | path | string(uuid) | yes |

#### `POST /api/v1/lab/results/{result_id}/release`

**Post Release Result**

- Permission: `lab.release`
- operationId: `post_release_result_api_v1_lab_results__result_id__release_post`
- Request body: -
- Response: `200 LabResultOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `result_id` | path | string(uuid) | yes |

#### `POST /api/v1/lab/results/{result_id}/verify`

**Post Verify Result**

- Permission: `lab.verify`
- operationId: `post_verify_result_api_v1_lab_results__result_id__verify_post`
- Request body: -
- Response: `200 LabResultOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `result_id` | path | string(uuid) | yes |

#### `POST /api/v1/lab/specimens/{specimen_id}/reject`

**Post Reject Specimen**

- Permission: `lab.order`
- operationId: `post_reject_specimen_api_v1_lab_specimens__specimen_id__reject_post`
- Request body: `RejectSpecimenIn`
- Response: `200 LabSpecimenOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `specimen_id` | path | string(uuid) | yes |

#### `GET /api/v1/lab/tests`

**List Lab Tests**

- Permission: `lab.read`
- operationId: `list_lab_tests_api_v1_lab_tests_get`
- Request body: -
- Response: `200 list[LabTestOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `q` | query | string \| null | no |

### members

#### `GET /api/v1/members`

**List Members**

- Permission: `member.read`
- operationId: `list_members_api_v1_members_get`
- Request body: -
- Response: `200 list[MemberOut]`

#### `POST /api/v1/members`

**Create Member**

- Permission: `member.manage`
- operationId: `create_member_api_v1_members_post`
- Request body: `MemberCreateIn`
- Response: `201 MemberOut`

#### `GET /api/v1/members/invitations`

**List Invitations**

- Permission: `member.manage`
- operationId: `list_invitations_api_v1_members_invitations_get`
- Request body: -
- Response: `200 list[InvitationOut]`

#### `POST /api/v1/members/invitations`

**Create Invitation**

- Permission: `member.manage`
- operationId: `create_invitation_api_v1_members_invitations_post`
- Request body: `InvitationCreateIn`
- Response: `201 InvitationOut`

#### `POST /api/v1/members/invitations/{invitation_id}/revoke`

**Revoke Invitation**

- Permission: `member.manage`
- operationId: `revoke_invitation_api_v1_members_invitations__invitation_id__revoke_post`
- Request body: -
- Response: `200 InvitationOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `invitation_id` | path | string(uuid) | yes |

#### `PATCH /api/v1/members/{membership_id}`

**Update Member**

- Permission: `member.manage`
- operationId: `update_member_api_v1_members__membership_id__patch`
- Request body: `MemberUpdateIn`
- Response: `200 MemberOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `membership_id` | path | string(uuid) | yes |

#### `POST /api/v1/members/{membership_id}/sessions/revoke`

**Revoke Member Sessions**

- Permission: `member.manage`
- operationId: `revoke_member_sessions_api_v1_members__membership_id__sessions_revoke_post`
- Request body: -
- Response: `200 object`

| Parameter | In | Type | Required |
|---|---|---|---|
| `membership_id` | path | string(uuid) | yes |

### opd-queue

#### `GET /api/v1/opd/queue`

**Queue Board**

- Permission: `queue.read`
- operationId: `queue_board_api_v1_opd_queue_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `service_date` | query | string(date) \| null | no |
| `status_filter` | query | string \| null | no |

#### `POST /api/v1/opd/queue`

**Join Queue**

- Permission: `queue.manage`
- operationId: `join_queue_api_v1_opd_queue_post`
- Idempotency-Key: supported
- Request body: `QueueJoinIn`
- Response: `201 QueueEntryOut`

#### `POST /api/v1/opd/queue/{entry_id}/call`

**Call Patient**

- Permission: `queue.manage`
- operationId: `call_patient_api_v1_opd_queue__entry_id__call_post`
- Request body: `QueueStatusIn`
- Response: `200 QueueEntryOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `entry_id` | path | string(uuid) | yes |

#### `POST /api/v1/opd/queue/{entry_id}/complete`

**Complete Consultation**

- Permission: `queue.manage`
- operationId: `complete_consultation_api_v1_opd_queue__entry_id__complete_post`
- Request body: -
- Response: `200 QueueEntryOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `entry_id` | path | string(uuid) | yes |

#### `POST /api/v1/opd/queue/{entry_id}/skip`

**Skip Patient**

- Permission: `queue.manage`
- operationId: `skip_patient_api_v1_opd_queue__entry_id__skip_post`
- Request body: -
- Response: `200 QueueEntryOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `entry_id` | path | string(uuid) | yes |

#### `POST /api/v1/opd/queue/{entry_id}/start`

**Start Consultation**

- Permission: `queue.manage`
- operationId: `start_consultation_api_v1_opd_queue__entry_id__start_post`
- Request body: `QueueStatusIn`
- Response: `200 QueueEntryOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `entry_id` | path | string(uuid) | yes |

### organization

#### `GET /api/v1/organization`

**Get Organization**

- Permission: `org.read`
- operationId: `get_organization_api_v1_organization_get`
- Request body: -
- Response: `200 OrganizationProfileOut`

#### `PATCH /api/v1/organization`

**Update Organization**

- Permission: `org.manage`
- operationId: `update_organization_api_v1_organization_patch`
- Request body: `OrganizationProfileIn`
- Response: `200 OrganizationProfileOut`

#### `POST /api/v1/organization/export`

**Export Organization** - Every tenant table as JSON in one zip (data portability / offboarding).

- Permission: `org.offboard`
- operationId: `export_organization_api_v1_organization_export_post`
- Request body: -
- Response: `200 (no body)`

#### `POST /api/v1/organization/offboarding`

**Request Offboarding** - Record the owner's closure request. Nothing is deleted here: the vendor

- Permission: `org.offboard`
- operationId: `request_offboarding_api_v1_organization_offboarding_post`
- Request body: `OffboardingIn`
- Response: `200 OrganizationProfileOut`

#### `DELETE /api/v1/organization/offboarding`

**Cancel Offboarding**

- Permission: `org.offboard`
- operationId: `cancel_offboarding_api_v1_organization_offboarding_delete`
- Request body: -
- Response: `200 OrganizationProfileOut`

#### `GET /api/v1/organization/onboarding`

**Onboarding**

- Permission: `org.read`
- operationId: `onboarding_api_v1_organization_onboarding_get`
- Request body: -
- Response: `200 OnboardingOut`

### patients

#### `GET /api/v1/patients`

**Search Patients**

- Permission: `patient.read`
- operationId: `search_patients_api_v1_patients_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `q` | query | string \| null | no |

#### `POST /api/v1/patients`

**Register Patient**

- Permission: `patient.write`
- operationId: `register_patient_api_v1_patients_post`
- Idempotency-Key: supported
- Request body: `PatientIn`
- Response: `201 PatientOut`

#### `GET /api/v1/patients/{patient_id}`

**Get Patient**

- Permission: `patient.read`
- operationId: `get_patient_api_v1_patients__patient_id__get`
- Request body: -
- Response: `200 PatientOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `patient_id` | path | string(uuid) | yes |

#### `PATCH /api/v1/patients/{patient_id}`

**Update Patient**

- Permission: `patient.write`
- operationId: `update_patient_api_v1_patients__patient_id__patch`
- Request body: `PatientUpdateIn`
- Response: `200 PatientOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `patient_id` | path | string(uuid) | yes |

#### `POST /api/v1/patients/{patient_id}/merge`

**Merge Patient** - Supervised duplicate resolution: source record is retired into target.

- Permission: `patient.merge`
- operationId: `merge_patient_api_v1_patients__patient_id__merge_post`
- Request body: `PatientMergeIn`
- Response: `200 PatientOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `patient_id` | path | string(uuid) | yes |

### pharmacy

#### `GET /api/v1/pharmacy/dispenses`

**List Dispenses**

- Permission: `pharmacy.read`
- operationId: `list_dispenses_api_v1_pharmacy_dispenses_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `offset` | query | integer | no |

#### `POST /api/v1/pharmacy/dispenses`

**Post Dispense**

- Permission: `pharmacy.dispense`
- operationId: `post_dispense_api_v1_pharmacy_dispenses_post`
- Idempotency-Key: supported
- Request body: `DispenseIn`
- Response: `201 DispenseOut`

#### `GET /api/v1/pharmacy/stock/alerts`

**Stock Alerts**

- Permission: `pharmacy.read`
- operationId: `stock_alerts_api_v1_pharmacy_stock_alerts_get`
- Request body: -
- Response: `200 StockAlertOut`

#### `GET /api/v1/pharmacy/stock/batches`

**List Stock Batches**

- Permission: `pharmacy.read`
- operationId: `list_stock_batches_api_v1_pharmacy_stock_batches_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | query | string(uuid) \| null | no |
| `drug_id` | query | string(uuid) \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `status` | query | string \| null | no |

#### `POST /api/v1/pharmacy/stock/batches`

**Post Receive Stock**

- Permission: `pharmacy.manage`
- operationId: `post_receive_stock_api_v1_pharmacy_stock_batches_post`
- Idempotency-Key: supported
- Request body: `ReceiveStockIn`
- Response: `201 StockBatchOut`

#### `POST /api/v1/pharmacy/stock/batches/{batch_id}/adjust`

**Post Adjust Stock**

- Permission: `pharmacy.manage`
- operationId: `post_adjust_stock_api_v1_pharmacy_stock_batches__batch_id__adjust_post`
- Request body: `AdjustStockIn`
- Response: `201 StockMovementOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `batch_id` | path | string(uuid) | yes |

#### `GET /api/v1/pharmacy/stock/movements`

**List Stock Movements**

- Permission: `pharmacy.read`
- operationId: `list_stock_movements_api_v1_pharmacy_stock_movements_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `batch_id` | query | string(uuid) \| null | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |

### platform

#### `GET /api/v1/platform/billing/credit-packs`

**Platform Packs**

- Permission: -
- operationId: `platform_packs_api_v1_platform_billing_credit_packs_get`
- Request body: -
- Response: `200 list[CatalogPack]`

#### `PUT /api/v1/platform/billing/credit-packs/{code}`

**Platform Put Pack**

- Permission: -
- operationId: `platform_put_pack_api_v1_platform_billing_credit_packs__code__put`
- Request body: `CreditPackIn`
- Response: `200 CatalogPack`

| Parameter | In | Type | Required |
|---|---|---|---|
| `code` | path | string | yes |

#### `POST /api/v1/platform/billing/lifecycle`

**Platform Lifecycle**

- Permission: -
- operationId: `platform_lifecycle_api_v1_platform_billing_lifecycle_post`
- Request body: -
- Response: `200 LifecycleOut`

#### `GET /api/v1/platform/billing/orders`

**Platform Orders**

- Permission: -
- operationId: `platform_orders_api_v1_platform_billing_orders_get`
- Request body: -
- Response: `200 list[OrderOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `organization_id` | query | string(uuid) \| null | no |
| `status` | query | string \| null | no |

#### `GET /api/v1/platform/billing/reconciliation`

**Platform Reconciliation**

- Permission: -
- operationId: `platform_reconciliation_api_v1_platform_billing_reconciliation_get`
- Request body: -
- Response: `200 ReconciliationOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `check_provider` | query | boolean | no |

#### `GET /api/v1/platform/billing/refunds`

**Platform Refunds**

- Permission: -
- operationId: `platform_refunds_api_v1_platform_billing_refunds_get`
- Request body: -
- Response: `200 list[app__schemas_billing__RefundOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string \| null | no |

#### `POST /api/v1/platform/billing/refunds/{refund_id}/decide`

**Platform Decide Refund**

- Permission: -
- operationId: `platform_decide_refund_api_v1_platform_billing_refunds__refund_id__decide_post`
- Request body: `RefundDecisionIn`
- Response: `200 app__schemas_billing__RefundOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `refund_id` | path | string(uuid) | yes |

#### `POST /api/v1/platform/billing/refunds/{refund_id}/resume`

**Platform Resume Refund** - Re-check an approved refund whose provider outcome is not yet known

- Permission: -
- operationId: `platform_resume_refund_api_v1_platform_billing_refunds__refund_id__resume_post`
- Request body: -
- Response: `200 app__schemas_billing__RefundOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `refund_id` | path | string(uuid) | yes |

#### `GET /api/v1/platform/catalog`

**Catalog**

- Permission: public
- operationId: `catalog_api_v1_platform_catalog_get`
- Request body: -
- Response: `200 CatalogOut`

#### `GET /api/v1/platform/overview`

**Overview**

- Permission: public
- operationId: `overview_api_v1_platform_overview_get`
- Request body: -
- Response: `200 PlatformOverviewOut`

#### `GET /api/v1/platform/plans`

**List Plans**

- Permission: public
- operationId: `list_plans_api_v1_platform_plans_get`
- Request body: -
- Response: `200 list[PlanOut]`

#### `PATCH /api/v1/platform/plans/{code}`

**Update Plan**

- Permission: public
- operationId: `update_plan_api_v1_platform_plans__code__patch`
- Request body: `PlanUpdateIn`
- Response: `200 PlanOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `code` | path | string | yes |

#### `PUT /api/v1/platform/plans/{code}/features`

**Set Plan Features**

- Permission: public
- operationId: `set_plan_features_api_v1_platform_plans__code__features_put`
- Request body: `PlanFeaturesIn`
- Response: `200 PlanOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `code` | path | string | yes |

#### `PUT /api/v1/platform/plans/{code}/limits`

**Set Plan Limits**

- Permission: public
- operationId: `set_plan_limits_api_v1_platform_plans__code__limits_put`
- Request body: `PlanLimitsIn`
- Response: `200 PlanOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `code` | path | string | yes |

#### `GET /api/v1/platform/support/tickets`

**Support Queue**

- Permission: public
- operationId: `support_queue_api_v1_platform_support_tickets_get`
- Request body: -
- Response: `200 list[SupportTicketOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string \| null | no |

#### `GET /api/v1/platform/support/tickets/{ticket_id}`

**Support Ticket**

- Permission: public
- operationId: `support_ticket_api_v1_platform_support_tickets__ticket_id__get`
- Request body: -
- Response: `200 SupportTicketDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `ticket_id` | path | string(uuid) | yes |

#### `PATCH /api/v1/platform/support/tickets/{ticket_id}`

**Support Update**

- Permission: public
- operationId: `support_update_api_v1_platform_support_tickets__ticket_id__patch`
- Request body: `PlatformTicketUpdateIn`
- Response: `200 SupportTicketOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `ticket_id` | path | string(uuid) | yes |

#### `POST /api/v1/platform/support/tickets/{ticket_id}/messages`

**Support Reply**

- Permission: public
- operationId: `support_reply_api_v1_platform_support_tickets__ticket_id__messages_post`
- Request body: `PlatformSupportMessageIn`
- Response: `200 SupportTicketDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `ticket_id` | path | string(uuid) | yes |

#### `GET /api/v1/platform/tenants`

**List Tenants**

- Permission: public
- operationId: `list_tenants_api_v1_platform_tenants_get`
- Request body: -
- Response: `200 list[PlatformTenantOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `q` | query | string \| null | no |
| `status` | query | string \| null | no |

#### `GET /api/v1/platform/tenants/{org_id}`

**Tenant Detail**

- Permission: public
- operationId: `tenant_detail_api_v1_platform_tenants__org_id__get`
- Request body: -
- Response: `200 PlatformTenantDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `org_id` | path | string(uuid) | yes |

#### `PATCH /api/v1/platform/tenants/{org_id}`

**Update Tenant**

- Permission: public
- operationId: `update_tenant_api_v1_platform_tenants__org_id__patch`
- Request body: `PlatformTenantUpdateIn`
- Response: `200 PlatformTenantOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `org_id` | path | string(uuid) | yes |

#### `PUT /api/v1/platform/tenants/{org_id}/subscription`

**Set Subscription**

- Permission: public
- operationId: `set_subscription_api_v1_platform_tenants__org_id__subscription_put`
- Request body: `PlatformSubscriptionIn`
- Response: `200 PlatformTenantDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `org_id` | path | string(uuid) | yes |

### prescriptions

#### `GET /api/v1/prescriptions`

**List Prescriptions**

- Permission: `prescription.read`
- operationId: `list_prescriptions_api_v1_prescriptions_get`
- Request body: -
- Response: `200 PageOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `offset` | query | integer | no |
| `patient_id` | query | string(uuid) \| null | no |
| `rx_status` | query | string \| null | no |

#### `POST /api/v1/prescriptions`

**Create Draft**

- Permission: `prescription.sign`
- operationId: `create_draft_api_v1_prescriptions_post`
- Idempotency-Key: supported
- Request body: `PrescriptionIn`
- Response: `201 PrescriptionDetailOut`

#### `GET /api/v1/prescriptions/drugs`

**List Drugs**

- Permission: `prescription.read`
- operationId: `list_drugs_api_v1_prescriptions_drugs_get`
- Request body: -
- Response: `200 list[DrugOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |
| `q` | query | string \| null | no |

#### `GET /api/v1/prescriptions/{rx_id}`

**Get Prescription**

- Permission: `prescription.read`
- operationId: `get_prescription_api_v1_prescriptions__rx_id__get`
- Request body: -
- Response: `200 PrescriptionDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `rx_id` | path | string(uuid) | yes |

#### `POST /api/v1/prescriptions/{rx_id}/amend`

**Amend Prescription** - Create version N+1. The old row is flipped to 'superseded' — the only

- Permission: `prescription.sign`
- operationId: `amend_prescription_api_v1_prescriptions__rx_id__amend_post`
- Request body: `AmendRxIn`
- Response: `201 PrescriptionDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `rx_id` | path | string(uuid) | yes |

#### `POST /api/v1/prescriptions/{rx_id}/sign`

**Sign Prescription**

- Permission: `prescription.sign`
- operationId: `sign_prescription_api_v1_prescriptions__rx_id__sign_post`
- Request body: `SignRxIn`
- Response: `200 PrescriptionDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `rx_id` | path | string(uuid) | yes |

#### `POST /api/v1/prescriptions/{rx_id}/warnings`

**Check Warnings** - Pre-flight safety check (allergy + duplicate) without signing.

- Permission: `prescription.sign`
- operationId: `check_warnings_api_v1_prescriptions__rx_id__warnings_post`
- Request body: -
- Response: `200 RxWarningsOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `rx_id` | path | string(uuid) | yes |

### printers

#### `GET /api/v1/setup/printers`

**List Profiles**

- Permission: `setup.read`
- operationId: `list_profiles_api_v1_setup_printers_get`
- Request body: -
- Response: `200 list[PrinterProfileOut]`

#### `POST /api/v1/setup/printers`

**Create Profile**

- Permission: `setup.manage`
- operationId: `create_profile_api_v1_setup_printers_post`
- Request body: `PrinterProfileIn`
- Response: `201 PrinterProfileOut`

#### `GET /api/v1/setup/printers/defaults`

**Defaults**

- Permission: `setup.read`
- operationId: `defaults_api_v1_setup_printers_defaults_get`
- Request body: -
- Response: `200 PrinterDefaultsOut`

#### `GET /api/v1/setup/printers/{profile_id}`

**Get Profile**

- Permission: `setup.read`
- operationId: `get_profile_api_v1_setup_printers__profile_id__get`
- Request body: -
- Response: `200 PrinterProfileOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `profile_id` | path | string(uuid) | yes |

#### `PATCH /api/v1/setup/printers/{profile_id}`

**Update Profile**

- Permission: `setup.manage`
- operationId: `update_profile_api_v1_setup_printers__profile_id__patch`
- Request body: `PrinterProfileUpdateIn`
- Response: `200 PrinterProfileOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `profile_id` | path | string(uuid) | yes |

#### `DELETE /api/v1/setup/printers/{profile_id}`

**Delete Profile**

- Permission: `setup.manage`
- operationId: `delete_profile_api_v1_setup_printers__profile_id__delete`
- Request body: -
- Response: `204 (no body)`

| Parameter | In | Type | Required |
|---|---|---|---|
| `profile_id` | path | string(uuid) | yes |

### reports

#### `GET /api/v1/reports/summary`

**Report Summary**

- Permission: `report.read`
- operationId: `report_summary_api_v1_reports_summary_get`
- Request body: -
- Response: `200 ReportSummaryOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `from` | query | string(date) \| null | no |
| `to` | query | string(date) \| null | no |

### saas-billing

#### `GET /api/v1/saas/catalog`

**Catalog**

- Permission: -
- operationId: `catalog_api_v1_saas_catalog_get`
- Request body: -
- Response: `200 BillingCatalog`

#### `GET /api/v1/saas/credits`

**Ai Credits**

- Permission: -
- operationId: `ai_credits_api_v1_saas_credits_get`
- Request body: -
- Response: `200 CreditsOut`

#### `GET /api/v1/saas/invoices`

**List Invoices**

- Permission: -
- operationId: `list_invoices_api_v1_saas_invoices_get`
- Request body: -
- Response: `200 list[app__schemas_billing__InvoiceOut]`

#### `GET /api/v1/saas/invoices/{invoice_id}`

**Get Invoice**

- Permission: -
- operationId: `get_invoice_api_v1_saas_invoices__invoice_id__get`
- Request body: -
- Response: `200 app__schemas_billing__InvoiceOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | string(uuid) | yes |

#### `GET /api/v1/saas/orders`

**List Orders**

- Permission: -
- operationId: `list_orders_api_v1_saas_orders_get`
- Request body: -
- Response: `200 list[OrderOut]`

| Parameter | In | Type | Required |
|---|---|---|---|
| `limit` | query | integer | no |

#### `POST /api/v1/saas/orders`

**Create Order**

- Permission: -
- operationId: `create_order_api_v1_saas_orders_post`
- Idempotency-Key: supported
- Request body: `OrderIn`
- Response: `201 OrderCreated`

#### `POST /api/v1/saas/orders/{order_id}/retry`

**Retry Order** - Failed-payment recovery: a fresh order for the same item at today's price.

- Permission: -
- operationId: `retry_order_api_v1_saas_orders__order_id__retry_post`
- Idempotency-Key: supported
- Request body: -
- Response: `201 OrderCreated`

| Parameter | In | Type | Required |
|---|---|---|---|
| `order_id` | path | string(uuid) | yes |

#### `POST /api/v1/saas/orders/{order_id}/simulate`

**Simulate Payment** - Development demo only: plays the hosted checkout AND the provider's

- Permission: -
- operationId: `simulate_payment_api_v1_saas_orders__order_id__simulate_post`
- Request body: `SimulateIn`
- Response: `200 PaymentResult`

| Parameter | In | Type | Required |
|---|---|---|---|
| `order_id` | path | string(uuid) | yes |

#### `POST /api/v1/saas/orders/{order_id}/verify`

**Verify Payment** - Browser callback after the hosted checkout. The signature is checked

- Permission: -
- operationId: `verify_payment_api_v1_saas_orders__order_id__verify_post`
- Request body: `VerifyIn`
- Response: `200 PaymentResult`

| Parameter | In | Type | Required |
|---|---|---|---|
| `order_id` | path | string(uuid) | yes |

#### `GET /api/v1/saas/payments`

**List Payments**

- Permission: -
- operationId: `list_payments_api_v1_saas_payments_get`
- Request body: -
- Response: `200 list[app__schemas_billing__PaymentOut]`

#### `GET /api/v1/saas/refunds`

**List Refunds**

- Permission: -
- operationId: `list_refunds_api_v1_saas_refunds_get`
- Request body: -
- Response: `200 list[app__schemas_billing__RefundOut]`

#### `POST /api/v1/saas/refunds`

**Request Refund**

- Permission: -
- operationId: `request_refund_api_v1_saas_refunds_post`
- Request body: `app__schemas_billing__RefundIn`
- Response: `201 app__schemas_billing__RefundOut`

#### `POST /api/v1/saas/webhooks/razorpay`

**Razorpay Webhook**

- Permission: -
- operationId: `razorpay_webhook_api_v1_saas_webhooks_razorpay_post`
- Request body: -
- Response: `200 (no body)`

### setup

#### `GET /api/v1/setup/branches/{branch_id}/working-hours`

**Get Working Hours**

- Permission: `setup.read`
- operationId: `get_working_hours_api_v1_setup_branches__branch_id__working_hours_get`
- Request body: -
- Response: `200 WorkingHoursOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | path | string(uuid) | yes |

#### `PUT /api/v1/setup/branches/{branch_id}/working-hours`

**Put Working Hours** - Replace the branch's whole week (validated: ranges, breaks, overlaps).

- Permission: `setup.manage`
- operationId: `put_working_hours_api_v1_setup_branches__branch_id__working_hours_put`
- Request body: `WorkingHoursIn`
- Response: `200 WorkingHoursOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `branch_id` | path | string(uuid) | yes |

#### `GET /api/v1/setup/fees`

**List Fees**

- Permission: `setup.read`
- operationId: `list_fees_api_v1_setup_fees_get`
- Request body: -
- Response: `200 FeesOut`

#### `PUT /api/v1/setup/fees/default`

**Put Default Fee**

- Permission: `setup.manage`
- operationId: `put_default_fee_api_v1_setup_fees_default_put`
- Request body: `FeeIn`
- Response: `200 FeeOut`

#### `GET /api/v1/setup/fees/effective`

**Effective Fee** - The fee to pre-fill on a consultation invoice: the doctor's own fee,

- Permission: `setup.read`
- operationId: `effective_fee_api_v1_setup_fees_effective_get`
- Request body: -
- Response: `200 EffectiveFeeOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `provider_user_id` | query | string(uuid) \| null | no |

#### `PUT /api/v1/setup/fees/providers/{user_id}`

**Put Provider Fee**

- Permission: `setup.manage`
- operationId: `put_provider_fee_api_v1_setup_fees_providers__user_id__put`
- Request body: `FeeIn`
- Response: `200 FeeOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `user_id` | path | string(uuid) | yes |

#### `DELETE /api/v1/setup/fees/providers/{user_id}`

**Delete Provider Fee**

- Permission: `setup.manage`
- operationId: `delete_provider_fee_api_v1_setup_fees_providers__user_id__delete`
- Request body: -
- Response: `204 (no body)`

| Parameter | In | Type | Required |
|---|---|---|---|
| `user_id` | path | string(uuid) | yes |

#### `GET /api/v1/setup/settings`

**Get Settings Doc**

- Permission: `setup.read`
- operationId: `get_settings_doc_api_v1_setup_settings_get`
- Request body: -
- Response: `200 OrgSettingsOut`

#### `PATCH /api/v1/setup/settings`

**Patch Settings Doc**

- Permission: `setup.manage`
- operationId: `patch_settings_doc_api_v1_setup_settings_patch`
- Request body: `OrgSettingsPatch`
- Response: `200 OrgSettingsOut`

#### `GET /api/v1/setup/wizard`

**Get Wizard**

- Permission: `setup.read`
- operationId: `get_wizard_api_v1_setup_wizard_get`
- Request body: -
- Response: `200 WizardOut`

#### `PATCH /api/v1/setup/wizard`

**Patch Wizard**

- Permission: `setup.manage`
- operationId: `patch_wizard_api_v1_setup_wizard_patch`
- Request body: `WizardPatchIn`
- Response: `200 WizardOut`

#### `POST /api/v1/setup/wizard/steps/{step_key}`

**Mark Step**

- Permission: `setup.manage`
- operationId: `mark_step_api_v1_setup_wizard_steps__step_key__post`
- Request body: `WizardStepIn`
- Response: `200 WizardOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `step_key` | path | string (identity, branch, staff, language, working_hours, fees, prescription, billing, printer, schedule, edition) | yes |

### subscription

#### `GET /api/v1/plans`

**List Public Plans** - Public catalogue (no auth). A null price means "not configured yet".

- Permission: public
- operationId: `list_public_plans_api_v1_plans_get`
- Request body: -
- Response: `200 list[PlanOut]`

#### `GET /api/v1/subscription`

**Get Subscription**

- Permission: `subscription.read`
- operationId: `get_subscription_api_v1_subscription_get`
- Request body: -
- Response: `200 SubscriptionOut`

#### `POST /api/v1/subscription/change-request`

**Request Plan Change**

- Permission: `subscription.manage`
- operationId: `request_plan_change_api_v1_subscription_change_request_post`
- Request body: `ChangeRequestIn`
- Response: `201 SupportTicketOut`

### support

#### `GET /api/v1/support/tickets`

**List Tickets**

- Permission: `support.read`
- operationId: `list_tickets_api_v1_support_tickets_get`
- Request body: -
- Response: `200 list[SupportTicketOut]`

#### `POST /api/v1/support/tickets`

**Create Ticket**

- Permission: `support.write`
- operationId: `create_ticket_api_v1_support_tickets_post`
- Request body: `SupportTicketIn`
- Response: `201 SupportTicketOut`

#### `GET /api/v1/support/tickets/{ticket_id}`

**Get Ticket**

- Permission: `support.read`
- operationId: `get_ticket_api_v1_support_tickets__ticket_id__get`
- Request body: -
- Response: `200 SupportTicketDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `ticket_id` | path | string(uuid) | yes |

#### `POST /api/v1/support/tickets/{ticket_id}/close`

**Close**

- Permission: `support.write`
- operationId: `close_api_v1_support_tickets__ticket_id__close_post`
- Request body: -
- Response: `200 SupportTicketOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `ticket_id` | path | string(uuid) | yes |

#### `POST /api/v1/support/tickets/{ticket_id}/messages`

**Reply**

- Permission: `support.write`
- operationId: `reply_api_v1_support_tickets__ticket_id__messages_post`
- Request body: `SupportMessageIn`
- Response: `200 SupportTicketDetailOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `ticket_id` | path | string(uuid) | yes |

### system

#### `GET /api/v1/health`

**Health**

- Permission: public
- operationId: `health_api_v1_health_get`
- Request body: -
- Response: `200 HealthOut`

#### `GET /api/v1/health/ready`

**Ready**

- Permission: public
- operationId: `ready_api_v1_health_ready_get`
- Request body: -
- Response: `200 (no body)`

## Schemas

Field lists of the request/response schemas referenced above (`*` = required).

### AcceptIn

| Field | Type |
|---|---|
| `surface`* | string (web, android) |
| `note` | string |
| `confirm_patient`* | boolean |

### AddressCheckIn

| Field | Type |
|---|---|
| `ble_address`* | string |

### AddressCheckOut

| Field | Type |
|---|---|
| `match`* | boolean |
| `active`* | boolean |

### AdjustStockIn

| Field | Type |
|---|---|
| `quantity` | integer |
| `reason`* | string |
| `write_off` | boolean |

### AdmissionIn

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `ward_id`* | string(uuid) |
| `bed_id`* | string(uuid) |
| `reason`* | string |
| `attending_user_id` | string(uuid) \| null |

### AdmissionOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `ward_id`* | string(uuid) |
| `bed_id`* | string(uuid) |
| `reason`* | string |
| `attending_user_id`* | string(uuid) \| null |
| `status`* | string |
| `admitted_at`* | string(date-time) |
| `discharge_outcome`* | string \| null |
| `discharge_summary`* | string |
| `discharged_at`* | string(date-time) \| null |
| `patient_uhid` | string |
| `patient_full_name` | string |

### AgentRunIn

| Field | Type |
|---|---|
| `agent`* | string (appointment_followups, inventory_monitor, billing_reconciliation, ops_daily_report) |
| `branch_id` | string(uuid) \| null |
| `older_than_days` | integer |

### AgentRunOut

| Field | Type |
|---|---|
| `agent`* | string |
| `created`* | list[ProposalOut] |
| `skipped_duplicates`* | integer |
| `inference` | string |
| `note`* | string |

### AiRequestOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `feature`* | string |
| `task`* | string |
| `provider`* | string |
| `model`* | string |
| `inference`* | string |
| `data_class`* | string |
| `status`* | string |
| `credits`* | integer |
| `latency_ms`* | integer \| null |
| `created_at`* | string(date-time) |

### AiSettingsIn

| Field | Type |
|---|---|
| `enabled_features`* | list[string] |

### AiSettingsOut

| Field | Type |
|---|---|
| `enabled_features`* | list[string] |
| `entitled_features`* | list[string] |
| `live_inference`* | boolean |
| `copilot_provider`* | string |
| `copilot_provider_region`* | string |

### AiUsageOut

| Field | Type |
|---|---|
| `period`* | string |
| `used_credits`* | integer |
| `limit_credits`* | integer \| null |
| `purchased_balance` | integer |

### AmendResultIn

| Field | Type |
|---|---|
| `value_text` | string |
| `value_numeric` | number \| null |
| `flag` | string |
| `reason`* | string |

### AmendRxIn

| Field | Type |
|---|---|
| `reason`* | string |
| `diagnosis_text` | string |
| `advice` | string |
| `follow_up` | string |
| `items`* | list[RxItemIn] |
| `acknowledge_allergies` | boolean |

### AppointmentIn

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `provider_user_id` | string(uuid) \| null |
| `starts_at`* | string(date-time) |
| `ends_at`* | string(date-time) |
| `reason` | string |
| `notes` | string |

### AppointmentOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `provider_user_id`* | string(uuid) \| null |
| `starts_at`* | string(date-time) |
| `ends_at`* | string(date-time) |
| `reason`* | string |
| `status`* | string |
| `notes`* | string |
| `created_at`* | string(date-time) |

### AppointmentUpdateIn

| Field | Type |
|---|---|
| `starts_at` | string(date-time) \| null |
| `ends_at` | string(date-time) \| null |
| `provider_user_id` | string(uuid) \| null |
| `reason` | string \| null |
| `notes` | string \| null |
| `status` | string \| null |

### AudioMetaIn

| Field | Type |
|---|---|
| `duration_s`* | number |
| `mime`* | string |

### AuthSessionOut

| Field | Type |
|---|---|
| `user`* | UserOut |
| `organization`* | OrganizationOut |
| `role`* | string |
| `permissions`* | list[string] |
| `tokens`* | TokenPair |

### BedIn

| Field | Type |
|---|---|
| `ward_id`* | string(uuid) |
| `label`* | string |

### BedOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `ward_id`* | string(uuid) |
| `label`* | string |
| `status`* | string |
| `admission_id` | string(uuid) \| null |
| `patient_id` | string(uuid) \| null |
| `admitted_at` | string(date-time) \| null |

### BedUpdateIn

| Field | Type |
|---|---|
| `status`* | string |

### BillingCatalog

| Field | Type |
|---|---|
| `provider`* | string |
| `mode`* | string |
| `gst_rate_bp`* | integer |
| `currency` | string |
| `plans`* | list[CatalogPlan] |
| `credit_packs`* | list[CatalogPack] |
| `notice`* | string |

### BillingSettings

| Field | Type |
|---|---|
| `invoice_prefix` | string |
| `show_gstin` | boolean |
| `default_payment_methods` | list[string] |
| `receipt_footer` | string |

### BranchIn

| Field | Type |
|---|---|
| `name`* | string |
| `code`* | string |
| `address` | string \| null |
| `phone` | string \| null |
| `gstin` | string \| null |

### BranchOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `name`* | string |
| `code`* | string |
| `status`* | string |
| `address` | string \| null |
| `phone` | string \| null |
| `gstin` | string \| null |
| `created_at`* | string(date-time) |

### BranchUpdateIn

| Field | Type |
|---|---|
| `name` | string \| null |
| `address` | string \| null |
| `phone` | string \| null |
| `gstin` | string \| null |
| `status` | string \| null |

### CancelLabOrderIn

| Field | Type |
|---|---|
| `reason`* | string |

### CatalogEntryOut

| Field | Type |
|---|---|
| `key`* | string |
| `label`* | string |

### CatalogOut

| Field | Type |
|---|---|
| `features`* | list[CatalogEntryOut] |
| `limits`* | list[CatalogEntryOut] |

### CatalogPack

| Field | Type |
|---|---|
| `code`* | string |
| `name`* | string |
| `credits`* | integer |
| `price_paise`* | integer \| null |
| `purchasable`* | boolean |

### CatalogPlan

| Field | Type |
|---|---|
| `code`* | string |
| `name`* | string |
| `tier`* | integer |
| `price_monthly_paise`* | integer \| null |
| `price_annual_paise`* | integer \| null |
| `purchasable`* | boolean |

### ChangeRequestIn

| Field | Type |
|---|---|
| `plan_code`* | string |
| `billing_cycle`* | string (monthly, annual) |
| `note` | string |

### ChannelUsage

| Field | Type |
|---|---|
| `channel`* | string |
| `entitled`* | boolean |
| `provider`* | string |
| `mock`* | boolean |
| `live`* | boolean |
| `used`* | integer |
| `limit`* | integer \| null |
| `cost_paise`* | integer |
| `cost_per_message_paise`* | integer |

### CheckinCodeIn

| Field | Type |
|---|---|
| `code`* | string |

### CheckinConfirmOut

| Field | Type |
|---|---|
| `status`* | string (checked_in, already_checked_in) |
| `appointment_id`* | string(uuid) |
| `queue_entry`* | CheckinQueueOut |

### CheckinIssueOut

| Field | Type |
|---|---|
| `appointment_id`* | string(uuid) |
| `token`* | string |
| `expires_at`* | string(date-time) |

### CheckinQueueOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `token_number`* | integer |
| `status`* | string |
| `service_date`* | string(date) |

### CheckinVerifyOut

| Field | Type |
|---|---|
| `status`* | string (ready, already_checked_in) |
| `appointment_id`* | string(uuid) |
| `patient_display_name`* | string |
| `appointment_starts_at`* | string(date-time) |
| `branch_name`* | string |
| `queue_token_number`* | integer \| null |

### CheckoutParams

| Field | Type |
|---|---|
| `provider`* | string |
| `mode`* | string |
| `key_id`* | string |
| `provider_order_id`* | string |
| `amount`* | integer |
| `currency`* | string |

### CollectSpecimenIn

| Field | Type |
|---|---|
| `specimen_type`* | string |

### CommsOverview

| Field | Type |
|---|---|
| `period`* | string |
| `live_enabled`* | boolean |
| `mock_notice`* | string |
| `channels`* | list[ChannelUsage] |
| `spend_paise`* | integer |
| `spend_cap_paise`* | integer \| null |
| `consent`* | list[ConsentStats] |
| `active_patients`* | integer |
| `settings`* | CommsSettingsOut |
| `in_quiet_hours`* | boolean |

### CommsSettingsIn

| Field | Type |
|---|---|
| `monthly_spend_cap_paise` | integer \| null |
| `quiet_start_hour` | integer |
| `quiet_end_hour` | integer |
| `reminder_hours_ahead` | integer |
| `reminder_channels` | list[string] |

### CommsSettingsOut

| Field | Type |
|---|---|
| `monthly_spend_cap_paise`* | integer \| null |
| `quiet_start_hour`* | integer |
| `quiet_end_hour`* | integer |
| `reminder_hours_ahead`* | integer |
| `reminder_channels`* | list[string] |
| `updated_at`* | string(date-time) |

### ConsentEventOut

| Field | Type |
|---|---|
| `channel`* | string |
| `status`* | string |
| `source`* | string |
| `recorded_at`* | string(date-time) |
| `actor_name`* | string \| null |

### ConsentIn

| Field | Type |
|---|---|
| `channel`* | string (email, sms, whatsapp) |
| `status`* | string (opted_in, opted_out) |
| `source`* | string (registration_form, patient_request, patient_reply, staff_update) |

### ConsentOut

| Field | Type |
|---|---|
| `channel`* | string |
| `status`* | string \| null |
| `source`* | string \| null |
| `recorded_at`* | string(date-time) \| null |
| `actor_name`* | string \| null |

### ConsentStats

| Field | Type |
|---|---|
| `channel`* | string |
| `opted_in`* | integer |
| `opted_out`* | integer |
| `unknown`* | integer |

### CopilotAnswerOut

| Field | Type |
|---|---|
| `request_id`* | string(uuid) |
| `answered`* | boolean |
| `language`* | string |
| `answer`* | string |
| `figures`* | object |
| `rows`* | list[object] |
| `computed_with`* | CopilotComputedWith \| null |
| `inference`* | string |
| `provider`* | string |
| `model`* | string |
| `credits_charged`* | integer |
| `note` | string \| null |

### CopilotAskIn

| Field | Type |
|---|---|
| `question`* | string |
| `language` | string \| null |

### CopilotCatalogEntry

| Field | Type |
|---|---|
| `function`* | string |
| `label`* | string |
| `args`* | list[string] |

### CopilotComputedWith

| Field | Type |
|---|---|
| `function`* | string |
| `args`* | object |
| `method`* | string |

### CreditPackIn

| Field | Type |
|---|---|
| `name`* | string |
| `credits`* | integer |
| `price_paise` | integer \| null |
| `is_active` | boolean |

### CreditsOut

| Field | Type |
|---|---|
| `period`* | string |
| `plan_allowance`* | integer \| null |
| `allowance_used`* | integer |
| `purchased`* | integer |
| `purchased_total`* | integer |
| `used`* | integer |
| `remaining`* | integer \| null |
| `purchased_expire` | boolean |

### DecisionOut

| Field | Type |
|---|---|
| `decision`* | string |
| `reason`* | string |
| `surface`* | string |
| `vitals_id`* | string(uuid) \| null |
| `decided_by`* | string(uuid) \| null |
| `decided_at`* | string(date-time) |

### DeliveryOut

| Field | Type |
|---|---|
| `id`* | integer |
| `channel`* | string |
| `purpose`* | string |
| `language`* | string \| null |
| `template_id`* | string(uuid) \| null |
| `patient_id`* | string(uuid) \| null |
| `appointment_id`* | string(uuid) \| null |
| `follow_up_id`* | string(uuid) \| null |
| `recipient_masked`* | string \| null |
| `provider`* | string |
| `status`* | string |
| `cost_paise`* | integer |
| `trigger`* | string |
| `error`* | string \| null |
| `created_at`* | string(date-time) |

### DeliveryPage

| Field | Type |
|---|---|
| `items`* | list[DeliveryOut] |
| `total`* | integer |
| `limit`* | integer |
| `offset`* | integer |

### DeviceIn

| Field | Type |
|---|---|
| `kind`* | string (bp_monitor, pulse_oximeter) |
| `label`* | string |
| `ble_address`* | string |
| `manufacturer` | string |
| `model` | string |
| `serial` | string |
| `firmware` | string |
| `branch_id` | string(uuid) \| null |
| `is_simulator` | boolean |

### DeviceOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `kind`* | string |
| `label`* | string |
| `manufacturer`* | string |
| `model`* | string |
| `serial`* | string |
| `firmware`* | string |
| `branch_id`* | string(uuid) \| null |
| `is_simulator`* | boolean |
| `status`* | string |
| `created_at`* | string(date-time) |
| `retired_at`* | string(date-time) \| null |
| `hardware_validated` | boolean |

### DiagnosisIn

| Field | Type |
|---|---|
| `code`* | string |
| `label`* | string |
| `kind` | string |
| `status` | string |

### DiagnosisOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `encounter_id`* | string(uuid) |
| `code`* | string |
| `label`* | string |
| `kind`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |

### DischargeIn

| Field | Type |
|---|---|
| `outcome`* | string |
| `summary`* | string |

### DispenseIn

| Field | Type |
|---|---|
| `prescription_id` | string(uuid) \| null |
| `patient_id` | string(uuid) \| null |
| `branch_id` | string(uuid) \| null |
| `notes` | string |
| `items`* | list[DispenseItemIn] |

### DispenseItemIn

| Field | Type |
|---|---|
| `drug_id`* | string(uuid) |
| `quantity`* | integer |

### DispenseItemOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `batch_id`* | string(uuid) |
| `drug_id`* | string(uuid) |
| `quantity`* | integer |
| `unit_price`* | number |

### DispenseOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `prescription_id`* | string(uuid) \| null |
| `patient_id`* | string(uuid) \| null |
| `notes`* | string |
| `created_at`* | string(date-time) |
| `items` | list[DispenseItemOut] |

### DrugOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `generic_name`* | string |
| `brand_hint`* | string |
| `drug_class`* | string |

### EditionRef

| Field | Type |
|---|---|
| `code`* | string |
| `name`* | string |

### EffectiveFeeOut

| Field | Type |
|---|---|
| `provider_user_id`* | string(uuid) \| null |
| `source`* | string (provider, default, none) |
| `consultation_fee`* | string \| null |
| `follow_up_fee`* | string \| null |
| `follow_up_valid_days`* | integer \| null |

### EncounterDetailOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `appointment_id`* | string(uuid) \| null |
| `queue_entry_id`* | string(uuid) \| null |
| `provider_user_id`* | string(uuid) \| null |
| `chief_complaint`* | string |
| `history`* | string |
| `examination`* | string |
| `assessment`* | string |
| `plan`* | string |
| `status`* | string |
| `started_at`* | string(date-time) |
| `ended_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |
| `vitals` | list[VitalsOut] |
| `diagnoses` | list[DiagnosisOut] |
| `prescription_ids` | list[string(uuid)] |

### EncounterIn

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `appointment_id` | string(uuid) \| null |
| `queue_entry_id` | string(uuid) \| null |
| `provider_user_id` | string(uuid) \| null |
| `chief_complaint` | string |
| `history` | string |
| `examination` | string |

### EncounterOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `appointment_id`* | string(uuid) \| null |
| `queue_entry_id`* | string(uuid) \| null |
| `provider_user_id`* | string(uuid) \| null |
| `chief_complaint`* | string |
| `history`* | string |
| `examination`* | string |
| `assessment`* | string |
| `plan`* | string |
| `status`* | string |
| `started_at`* | string(date-time) |
| `ended_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |

### EncounterUpdateIn

| Field | Type |
|---|---|
| `chief_complaint` | string \| null |
| `history` | string \| null |
| `examination` | string \| null |
| `assessment` | string \| null |
| `plan` | string \| null |
| `provider_user_id` | string(uuid) \| null |

### ExpenseIn

| Field | Type |
|---|---|
| `category`* | string |
| `amount`* | number |
| `expense_date`* | string(date) |
| `description` | string |
| `reference` | string |
| `branch_id` | string(uuid) \| null |

### ExpenseOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `branch_id`* | string(uuid) \| null |
| `category`* | string |
| `amount`* | number |
| `expense_date`* | string(date) |
| `description`* | string |
| `reference`* | string |
| `status`* | string |
| `void_reason`* | string |
| `created_at`* | string(date-time) |

### ExpenseVoidIn

| Field | Type |
|---|---|
| `reason`* | string |

### FeeIn

| Field | Type |
|---|---|
| `consultation_fee`* | number \| string |
| `follow_up_fee` | number \| string \| null |
| `follow_up_valid_days` | integer \| null |

### FeeOut

| Field | Type |
|---|---|
| `provider_user_id`* | string(uuid) \| null |
| `consultation_fee`* | string |
| `follow_up_fee`* | string \| null |
| `follow_up_valid_days`* | integer \| null |
| `updated_at`* | string(date-time) |

### FeesOut

| Field | Type |
|---|---|
| `default`* | FeeOut \| null |
| `providers`* | list[FeeOut] |

### FinanceCategoryRow

| Field | Type |
|---|---|
| `category`* | string |
| `total`* | number |

### FinanceReport

| Field | Type |
|---|---|
| `revenue` | number |
| `refunds` | number |
| `expenses` | number |
| `net` | number |
| `by_category` | list[FinanceCategoryRow] |

### FollowUpActionIn

| Field | Type |
|---|---|
| `note` | string |

### FollowUpBookIn

| Field | Type |
|---|---|
| `appointment_id`* | string(uuid) |
| `note` | string |

### FollowUpIn

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `due_date`* | string(date) |
| `reason`* | string |
| `branch_id` | string(uuid) \| null |
| `assigned_user_id` | string(uuid) \| null |

### FollowUpOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `patient_name`* | string |
| `patient_uhid`* | string |
| `branch_id`* | string(uuid) \| null |
| `due_date`* | string(date) |
| `reason`* | string |
| `status`* | string |
| `bucket`* | string |
| `assigned_user_id`* | string(uuid) \| null |
| `assigned_name`* | string \| null |
| `created_by_name`* | string \| null |
| `appointment_id`* | string(uuid) \| null |
| `appointment_starts_at`* | string(date-time) \| null |
| `status_note`* | string |
| `reminded_at`* | string(date-time) \| null |
| `closed_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |

### ForecastOut

| Field | Type |
|---|---|
| `status`* | string (ok, insufficient_data) |
| `kind`* | string |
| `label`* | string |
| `inference`* | string |

### HTTPValidationError

| Field | Type |
|---|---|
| `detail` | list[ValidationError] |

### HealthOut

| Field | Type |
|---|---|
| `status`* | string |
| `service`* | string |
| `version`* | string |
| `environment`* | string |

### ImportResultsIn

| Field | Type |
|---|---|
| `specimen_id` | string(uuid) \| null |
| `results`* | list[LabResultValueIn] |

### InventoryItemIn

| Field | Type |
|---|---|
| `branch_id`* | string(uuid) |
| `name`* | string |
| `sku` | string |
| `unit` | string |
| `reorder_level` | integer |
| `unit_cost` | number |

### InventoryItemOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `name`* | string |
| `sku`* | string |
| `unit`* | string |
| `quantity_on_hand`* | integer |
| `reorder_level`* | integer |
| `unit_cost`* | number |
| `status`* | string |
| `created_at`* | string(date-time) |
| `low_stock` | boolean |

### InventoryItemUpdateIn

| Field | Type |
|---|---|
| `unit` | string \| null |
| `reorder_level` | integer \| null |
| `unit_cost` | number \| null |
| `status` | string \| null |

### InventoryMovementIn

| Field | Type |
|---|---|
| `movement_type`* | string |
| `quantity`* | integer |
| `reason`* | string |
| `write_off` | boolean |

### InventoryMovementOut

| Field | Type |
|---|---|
| `id`* | integer |
| `item_id`* | string(uuid) |
| `movement_type`* | string |
| `direction`* | string |
| `quantity`* | integer |
| `reason`* | string |
| `created_at`* | string(date-time) |

### InventoryReport

| Field | Type |
|---|---|
| `items_active` | integer |
| `low_stock` | list[object] |

### InvitationAcceptIn

| Field | Type |
|---|---|
| `token`* | string |
| `password`* | string |
| `full_name` | string \| null |

### InvitationCreateIn

| Field | Type |
|---|---|
| `email`* | string(email) |
| `role_key`* | string |
| `branch_id` | string(uuid) \| null |

### InvitationOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `email`* | string |
| `role_key`* | string |
| `branch_id`* | string(uuid) \| null |
| `status`* | string |
| `expires_at`* | string(date-time) |
| `created_at`* | string(date-time) |

### InvoiceDetailOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `encounter_id`* | string(uuid) \| null |
| `invoice_number`* | string |
| `status`* | string |
| `subtotal`* | number |
| `discount`* | number |
| `tax_total`* | number |
| `total`* | number |
| `amount_paid`* | number |
| `notes`* | string |
| `issued_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |
| `items` | list[InvoiceItemOut] |
| `payments` | list[app__schemas__PaymentOut] |

### InvoiceIn

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `encounter_id` | string(uuid) \| null |
| `discount` | number |
| `notes` | string |
| `items`* | list[InvoiceItemIn] |

### InvoiceItemIn

| Field | Type |
|---|---|
| `item_type`* | string |
| `description`* | string |
| `quantity` | integer |
| `unit_price`* | number |
| `tax_rate` | number |

### InvoiceItemOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `invoice_id`* | string(uuid) |
| `item_type`* | string |
| `description`* | string |
| `quantity`* | integer |
| `unit_price`* | number |
| `tax_rate`* | number |
| `line_total`* | number |
| `seq`* | integer |

### IpdReport

| Field | Type |
|---|---|
| `currently_admitted` | integer |
| `admissions_in_period` | integer |
| `discharges_in_period` | integer |
| `deaths_in_period` | integer |
| `beds_total` | integer |
| `beds_occupied` | integer |
| `beds_maintenance` | integer |

### KbAnswerOut

| Field | Type |
|---|---|
| `request_id`* | string(uuid) \| null |
| `answered`* | boolean |
| `language`* | string |
| `answer`* | list[KbSentence] |
| `refusal`* | string \| null |
| `retrieved`* | list[KbCitation] |
| `inference`* | string |
| `provider`* | string |
| `model`* | string |
| `method`* | string |
| `grounded`* | boolean |
| `note` | string \| null |

### KbAskIn

| Field | Type |
|---|---|
| `question`* | string |
| `language` | string \| null |

### KbCitation

| Field | Type |
|---|---|
| `chunk_id`* | string(uuid) |
| `document_id`* | string(uuid) |
| `document_title`* | string |
| `section`* | string |
| `version`* | integer |
| `score`* | number |

### KbDocumentDetailOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `title`* | string |
| `doc_type`* | string |
| `language`* | string |
| `version`* | integer |
| `status`* | string |
| `visibility_roles`* | list[string] |
| `injection_flags`* | integer |
| `chunk_count`* | integer |
| `uploaded_by`* | string(uuid) \| null |
| `approved_by`* | string(uuid) \| null |
| `approved_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |
| `body`* | string |

### KbDocumentIn

| Field | Type |
|---|---|
| `title`* | string |
| `doc_type` | string (sop, manual, policy, training, other) |
| `language` | string \| null |
| `text`* | string |
| `visibility_roles` | list[string] |
| `contains_patient_data`* | boolean |
| `file_name` | string \| null |

### KbDocumentOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `title`* | string |
| `doc_type`* | string |
| `language`* | string |
| `version`* | integer |
| `status`* | string |
| `visibility_roles`* | list[string] |
| `injection_flags`* | integer |
| `chunk_count`* | integer |
| `uploaded_by`* | string(uuid) \| null |
| `approved_by`* | string(uuid) \| null |
| `approved_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |

### KbSentence

| Field | Type |
|---|---|
| `text`* | string |
| `citation`* | KbCitation |

### KioskCheckinOut

| Field | Type |
|---|---|
| `status`* | string (checked_in, already_checked_in) |
| `token_number`* | integer |

### LabOrderDetailOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `encounter_id`* | string(uuid) \| null |
| `branch_id`* | string(uuid) |
| `status`* | string |
| `priority`* | string |
| `clinical_notes`* | string |
| `cancel_reason`* | string |
| `created_at`* | string(date-time) |
| `items` | list[LabOrderItemOut] |
| `specimens` | list[LabSpecimenOut] |
| `results` | list[LabResultOut] |

### LabOrderIn

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `encounter_id` | string(uuid) \| null |
| `priority` | string |
| `clinical_notes` | string |
| `test_ids`* | list[string(uuid)] |

### LabOrderItemOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `test_id`* | string(uuid) |
| `test_code`* | string |
| `test_name`* | string |
| `status`* | string |

### LabResultOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `order_id`* | string(uuid) |
| `test_id`* | string(uuid) |
| `specimen_id`* | string(uuid) \| null |
| `value_text`* | string |
| `value_numeric`* | number \| null |
| `unit`* | string |
| `reference_range`* | string |
| `flag`* | string |
| `status`* | string |
| `superseded_by_id`* | string(uuid) \| null |
| `amendment_reason`* | string |
| `verified_at`* | string(date-time) \| null |
| `released_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |

### LabResultValueIn

| Field | Type |
|---|---|
| `test_id`* | string(uuid) |
| `value_text` | string |
| `value_numeric` | number \| null |
| `flag` | string |

### LabSpecimenOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `order_id`* | string(uuid) |
| `barcode`* | string |
| `specimen_type`* | string |
| `status`* | string |
| `rejection_reason`* | string |
| `collected_at`* | string(date-time) |

### LabTestOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `code`* | string |
| `name`* | string |
| `specimen_type`* | string |
| `unit`* | string |
| `reference_range`* | string |

### LedgerEntryOut

| Field | Type |
|---|---|
| `id`* | integer |
| `invoice_id`* | string(uuid) |
| `payment_id`* | string(uuid) \| null |
| `refund_id`* | string(uuid) \| null |
| `entry_type`* | string |
| `direction`* | string |
| `amount`* | number |
| `description`* | string |
| `created_at`* | string(date-time) |

### LifecycleOut

| Field | Type |
|---|---|
| `past_due`* | integer |
| `read_only`* | integer |
| `orders_expired`* | integer |

### LoginIn

| Field | Type |
|---|---|
| `email`* | string(email) |
| `password`* | string |
| `organization_slug` | string \| null |

### MeOut

| Field | Type |
|---|---|
| `user`* | UserOut |
| `organization`* | OrganizationOut |
| `membership_id`* | string(uuid) |
| `branch_id`* | string(uuid) \| null |
| `role`* | string |
| `permissions`* | list[string] |
| `edition` | EditionRef \| null |
| `subscription_status` | string |
| `features` | list[string] |
| `mfa_enrollment_required` | boolean |
| `is_platform_admin` | boolean |

### MemberCreateIn

| Field | Type |
|---|---|
| `email`* | string(email) |
| `full_name`* | string |
| `password`* | string |
| `role_key`* | string |
| `branch_id` | string(uuid) \| null |

### MemberOut

| Field | Type |
|---|---|
| `membership_id`* | string(uuid) |
| `user_id`* | string(uuid) |
| `email`* | string(email) |
| `full_name`* | string |
| `registration_number` | string \| null |
| `role_key`* | string |
| `branch_id`* | string(uuid) \| null |
| `status`* | string |
| `created_at`* | string(date-time) |

### MemberUpdateIn

| Field | Type |
|---|---|
| `registration_number` | string \| null |
| `role_key` | string \| null |
| `status` | string \| null |
| `branch_id` | string(uuid) \| null |

### MfaChallengeOut

| Field | Type |
|---|---|
| `mfa_required` | boolean |
| `mfa_token`* | string |
| `methods`* | list[string] |
| `expires_in`* | integer |

### MfaDisableIn

| Field | Type |
|---|---|
| `password`* | string |
| `code`* | string |

### MfaStatusOut

| Field | Type |
|---|---|
| `totp_enabled`* | boolean |
| `recovery_codes_remaining`* | integer |

### MfaVerifyIn

| Field | Type |
|---|---|
| `mfa_token`* | string |
| `code`* | string |

### MissedAppointmentOut

| Field | Type |
|---|---|
| `appointment_id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `patient_name`* | string |
| `patient_uhid`* | string |
| `starts_at`* | string(date-time) |
| `status`* | string |
| `provider_name`* | string \| null |
| `notified`* | boolean |
| `open_follow_up_id`* | string(uuid) \| null |

### ModelRunOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `kind`* | string |
| `scope`* | string |
| `engine_version`* | string |
| `method`* | string |
| `status`* | string |
| `params`* | object |
| `metrics`* | object |
| `baseline_metrics`* | object |
| `data_start`* | string(date) \| null |
| `data_end`* | string(date) \| null |
| `n_obs`* | integer |
| `trained_at`* | string(date-time) |

### NotifyIn

| Field | Type |
|---|---|
| `channels` | list[string] \| null |

### NursingRecordIn

| Field | Type |
|---|---|
| `note_type` | string |
| `note` | string |
| `bp_systolic` | integer \| null |
| `bp_diastolic` | integer \| null |
| `pulse` | integer \| null |
| `respiratory_rate` | integer \| null |
| `temperature_c` | number \| null |
| `spo2` | integer \| null |

### NursingRecordOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `admission_id`* | string(uuid) |
| `note_type`* | string |
| `note`* | string |
| `bp_systolic`* | integer \| null |
| `bp_diastolic`* | integer \| null |
| `pulse`* | integer \| null |
| `respiratory_rate`* | integer \| null |
| `temperature_c`* | number \| null |
| `spo2`* | integer \| null |
| `recorded_at`* | string(date-time) |
| `recorded_by`* | string(uuid) \| null |

### OffboardingIn

| Field | Type |
|---|---|
| `password`* | string |
| `reason`* | string |

### OnboardingOut

| Field | Type |
|---|---|
| `completed`* | boolean |
| `steps`* | list[OnboardingStepOut] |

### OnboardingStepOut

| Field | Type |
|---|---|
| `key`* | string |
| `done`* | boolean |

### OptOutIn

| Field | Type |
|---|---|
| `channels` | list[string] \| null |
| `source` | string (registration_form, patient_request, patient_reply, staff_update) |

### OrderCreated

| Field | Type |
|---|---|
| `order`* | OrderOut |
| `checkout`* | CheckoutParams |

### OrderIn

| Field | Type |
|---|---|
| `kind`* | string (subscription, ai_credits) |
| `plan_code` | string \| null |
| `billing_cycle` | string \| null |
| `pack_code` | string \| null |

### OrderOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `kind`* | string |
| `description`* | string |
| `billing_cycle`* | string \| null |
| `credits`* | integer \| null |
| `amount_paise`* | integer |
| `tax_paise`* | integer |
| `total_paise`* | integer |
| `currency`* | string |
| `provider`* | string |
| `provider_order_id`* | string |
| `status`* | string |
| `failure_reason`* | string \| null |
| `created_at`* | string(date-time) |
| `paid_at`* | string(date-time) \| null |

### OrgSettings

| Field | Type |
|---|---|
| `version` | integer |
| `prescription` | PrescriptionSettings |
| `billing` | BillingSettings |
| `schedule` | ScheduleSettings |

### OrgSettingsOut

| Field | Type |
|---|---|
| `schema_version`* | integer |
| `settings`* | OrgSettings |
| `updated_at`* | string(date-time) \| null |

### OrgSettingsPatch

| Field | Type |
|---|---|
| `prescription` | PrescriptionSettings \| null |
| `billing` | BillingSettings \| null |
| `schedule` | ScheduleSettings \| null |

### OrganizationOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `name`* | string |
| `slug`* | string |
| `status`* | string |

### OrganizationProfileIn

| Field | Type |
|---|---|
| `name` | string \| null |
| `legal_name` | string \| null |
| `address_line1` | string \| null |
| `address_line2` | string \| null |
| `city` | string \| null |
| `state` | string \| null |
| `pincode` | string \| null |
| `phone` | string \| null |
| `email` | string(email) \| null |
| `gstin` | string \| null |
| `registration_number` | string \| null |
| `letterhead_note` | string \| null |
| `default_language` | string \| null |
| `timezone` | string \| null |
| `mfa_required_roles` | list[string] \| null |

### OrganizationProfileOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `name`* | string |
| `slug`* | string |
| `status`* | string |
| `legal_name`* | string \| null |
| `address_line1`* | string \| null |
| `address_line2`* | string \| null |
| `city`* | string \| null |
| `state`* | string \| null |
| `pincode`* | string \| null |
| `phone`* | string \| null |
| `email`* | string \| null |
| `gstin`* | string \| null |
| `registration_number`* | string \| null |
| `letterhead_note`* | string \| null |
| `default_language`* | string |
| `timezone`* | string |
| `mfa_required_roles`* | list[string] |
| `offboarding_requested_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |

### OutboxMessageOut

| Field | Type |
|---|---|
| `id`* | integer |
| `channel`* | string |
| `to`* | string |
| `subject`* | string |
| `body`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |

### Page

| Field | Type |
|---|---|
| `items`* | list[-] |
| `total`* | integer |
| `limit`* | integer |
| `offset`* | integer |

### PageOut

| Field | Type |
|---|---|
| `items`* | list[-] |
| `total`* | integer |
| `limit`* | integer |
| `offset`* | integer |

### PasswordChangeIn

| Field | Type |
|---|---|
| `current_password`* | string |
| `new_password`* | string |

### PasswordForgotIn

| Field | Type |
|---|---|
| `email`* | string(email) |

### PasswordResetIn

| Field | Type |
|---|---|
| `token`* | string |
| `new_password`* | string |

### PatientCommsOut

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `preferred_language`* | string \| null |
| `email`* | string \| null |
| `phone_masked`* | string \| null |
| `consents`* | list[ConsentOut] |
| `history`* | list[ConsentEventOut] |

### PatientIn

| Field | Type |
|---|---|
| `full_name`* | string |
| `gender`* | string |
| `date_of_birth` | string(date-time) \| null |
| `dob_estimated` | boolean |
| `phone` | string \| null |
| `address` | string |
| `blood_group` | string \| null |
| `allergies` | string |
| `allow_duplicates` | boolean |

### PatientMergeIn

| Field | Type |
|---|---|
| `target_patient_id`* | string(uuid) |

### PatientOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `uhid`* | string |
| `full_name`* | string |
| `gender`* | string |
| `date_of_birth`* | string(date-time) \| null |
| `dob_estimated`* | boolean |
| `phone`* | string \| null |
| `address`* | string |
| `blood_group`* | string \| null |
| `allergies`* | string |
| `status`* | string |
| `merged_into_id`* | string(uuid) \| null |
| `created_at`* | string(date-time) |

### PatientUpdateIn

| Field | Type |
|---|---|
| `full_name` | string \| null |
| `gender` | string \| null |
| `date_of_birth` | string(date-time) \| null |
| `dob_estimated` | boolean \| null |
| `phone` | string \| null |
| `address` | string \| null |
| `blood_group` | string \| null |
| `allergies` | string \| null |
| `status` | string \| null |

### PaymentIn

| Field | Type |
|---|---|
| `amount`* | number |
| `method` | string |
| `gateway` | string |

### PaymentResult

| Field | Type |
|---|---|
| `outcome`* | string |
| `order`* | OrderOut |

### PlaceholderCatalog

| Field | Type |
|---|---|
| `allowed`* | dict[str, string] |
| `disallowed`* | list[string] |
| `sample_values`* | dict[str, string] |
| `rule`* | string |

### PlanFeaturesIn

| Field | Type |
|---|---|
| `features`* | list[string] |

### PlanLimitsIn

| Field | Type |
|---|---|
| `limits`* | dict[str, integer \| null] |

### PlanOut

| Field | Type |
|---|---|
| `code`* | string |
| `name`* | string |
| `description`* | string |
| `tier`* | integer |
| `price_monthly_paise`* | integer \| null |
| `price_annual_paise`* | integer \| null |
| `currency`* | string |
| `trial_days`* | integer |
| `features`* | list[string] |
| `limits`* | dict[str, integer \| null] |
| `is_active` | boolean \| null |
| `is_public` | boolean \| null |

### PlanUpdateIn

| Field | Type |
|---|---|
| `name` | string \| null |
| `description` | string \| null |
| `price_monthly_paise` | integer \| null |
| `price_annual_paise` | integer \| null |
| `trial_days` | integer \| null |
| `is_active` | boolean \| null |
| `is_public` | boolean \| null |

### PlatformOverviewOut

| Field | Type |
|---|---|
| `tenants_by_status`* | dict[str, integer] |
| `tenants_by_plan`* | dict[str, integer] |
| `trials_expiring_7d`* | integer |
| `open_tickets`* | integer |
| `mrr_paise`* | integer |
| `unpriced_active_subscriptions`* | integer |

### PlatformSubscriptionIn

| Field | Type |
|---|---|
| `plan_code`* | string |
| `status`* | string (trialing, active, past_due, read_only, suspended, cancelled) |
| `billing_cycle` | string (monthly, annual) |
| `trial_ends_at` | string(date-time) \| null |
| `current_period_end` | string(date-time) \| null |
| `limit_overrides` | dict[str, integer \| null] \| null |
| `feature_overrides` | dict[str, boolean] \| null |
| `reason`* | string |

### PlatformSupportMessageIn

| Field | Type |
|---|---|
| `body`* | string |
| `internal` | boolean |

### PlatformTenantDetailOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `name`* | string |
| `slug`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |
| `plan_code`* | string \| null |
| `subscription_status`* | string \| null |
| `effective_status`* | string \| null |
| `trial_ends_at`* | string(date-time) \| null |
| `users`* | integer |
| `branches`* | integer |
| `beds`* | integer |
| `patients`* | integer |
| `offboarding_requested_at`* | string(date-time) \| null |
| `subscription`* | SubscriptionOut \| null |
| `limit_overrides` | dict[str, integer \| null] |
| `feature_overrides` | dict[str, boolean] |
| `events`* | list[SubscriptionEventOut] |

### PlatformTenantOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `name`* | string |
| `slug`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |
| `plan_code`* | string \| null |
| `subscription_status`* | string \| null |
| `effective_status`* | string \| null |
| `trial_ends_at`* | string(date-time) \| null |
| `users`* | integer |
| `branches`* | integer |
| `beds`* | integer |
| `patients`* | integer |
| `offboarding_requested_at`* | string(date-time) \| null |

### PlatformTenantUpdateIn

| Field | Type |
|---|---|
| `status`* | string (active, suspended) |
| `reason`* | string |

### PlatformTicketUpdateIn

| Field | Type |
|---|---|
| `status` | string \| null |
| `priority` | string \| null |

### PreferencesIn

| Field | Type |
|---|---|
| `preferred_language` | string \| null |
| `email` | string(email) \| null |

### PrescriberOut

| Field | Type |
|---|---|
| `user_id`* | string(uuid) |
| `full_name`* | string |
| `registration_number` | string \| null |

### PrescriptionDetailOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `encounter_id`* | string(uuid) \| null |
| `patient_id`* | string(uuid) |
| `prescriber_user_id`* | string(uuid) \| null |
| `status`* | string |
| `version`* | integer |
| `supersedes_id`* | string(uuid) \| null |
| `diagnosis_text`* | string |
| `advice`* | string |
| `follow_up`* | string |
| `allergy_acknowledged`* | boolean |
| `signed_at`* | string(date-time) \| null |
| `amendment_reason`* | string |
| `created_at`* | string(date-time) |
| `items` | list[RxItemOut] |
| `prescriber` | PrescriberOut \| null |

### PrescriptionIn

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `encounter_id` | string(uuid) \| null |
| `diagnosis_text` | string |
| `advice` | string |
| `follow_up` | string |
| `items`* | list[RxItemIn] |

### PrescriptionSettings

| Field | Type |
|---|---|
| `header_text` | string |
| `footer_text` | string |
| `show_registration_number` | boolean |
| `paper_size` | string (A4, A5) |
| `language` | string (en, mr, hi, trilingual) |

### PreviewIn

| Field | Type |
|---|---|
| `channel` | string (email, sms, whatsapp) |
| `body`* | string |
| `subject` | string |

### PreviewOut

| Field | Type |
|---|---|
| `body`* | string |
| `subject`* | string |
| `errors`* | list[string] |
| `characters`* | integer |
| `sms_segments`* | integer |
| `sample_values`* | dict[str, string] |

### PrinterDefaultsOut

| Field | Type |
|---|---|
| `prescription`* | PrinterProfileOut \| null |
| `receipt`* | PrinterProfileOut \| null |
| `lab_report`* | PrinterProfileOut \| null |

### PrinterProfileIn

| Field | Type |
|---|---|
| `name`* | string |
| `kind`* | string (a4, a5, thermal_80mm, thermal_58mm) |
| `default_for` | list[string] |
| `margin_top_mm` | number \| string |
| `margin_right_mm` | number \| string |
| `margin_bottom_mm` | number \| string |
| `margin_left_mm` | number \| string |
| `font_scale` | number \| string |
| `notes` | string |

### PrinterProfileOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `name`* | string |
| `kind`* | string |
| `default_for`* | list[string] |
| `margin_top_mm`* | string |
| `margin_right_mm`* | string |
| `margin_bottom_mm`* | string |
| `margin_left_mm`* | string |
| `font_scale`* | string |
| `notes`* | string |
| `created_at`* | string(date-time) |
| `updated_at`* | string(date-time) |

### PrinterProfileUpdateIn

| Field | Type |
|---|---|
| `name` | string \| null |
| `kind` | string \| null |
| `default_for` | list[string] \| null |
| `margin_top_mm` | number \| string \| null |
| `margin_right_mm` | number \| string \| null |
| `margin_bottom_mm` | number \| string \| null |
| `margin_left_mm` | number \| string \| null |
| `font_scale` | number \| string \| null |
| `notes` | string \| null |

### ProfileUpdateIn

| Field | Type |
|---|---|
| `full_name` | string \| null |
| `registration_number` | string \| null |

### ProposalDecisionIn

| Field | Type |
|---|---|
| `note` | string |

### ProposalOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `agent`* | string |
| `kind`* | string |
| `status`* | string |
| `branch_id`* | string(uuid) \| null |
| `title`* | string |
| `payload`* | object |
| `rationale`* | string |
| `evidence`* | list[-] |
| `args_sha256`* | string |
| `created_by`* | string(uuid) \| null |
| `created_at`* | string(date-time) |
| `expires_at`* | string(date-time) |
| `decided_by`* | string(uuid) \| null |
| `decided_at`* | string(date-time) \| null |
| `decision_note`* | string |
| `executed_at`* | string(date-time) \| null |
| `result`* | object \| null |
| `approve_requires` | list[string] |
| `executable` | boolean |

### QueueEntryOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `appointment_id`* | string(uuid) \| null |
| `service_date`* | string(date-time) |
| `token_number`* | integer |
| `status`* | string |
| `priority`* | string |
| `doctor_user_id`* | string(uuid) \| null |
| `called_at`* | string(date-time) \| null |
| `started_at`* | string(date-time) \| null |
| `completed_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |

### QueueJoinIn

| Field | Type |
|---|---|
| `patient_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `appointment_id` | string(uuid) \| null |
| `priority` | string |

### QueueStatusIn

| Field | Type |
|---|---|
| `doctor_user_id` | string(uuid) \| null |

### ReadingIn

| Field | Type |
|---|---|
| `capture_id`* | string(uuid) |
| `device_id`* | string(uuid) |
| `ble_address`* | string |
| `encounter_id`* | string(uuid) |
| `characteristic`* | string (2a35, 2a5e, 2a5f) |
| `raw_hex`* | string |
| `source`* | string (ble, simulator) |
| `captured_at`* | string(date-time) |
| `app_version` | string |
| `client_parsed` | object \| null |

### ReadingOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `device_id`* | string(uuid) |
| `device_label`* | string |
| `device_is_simulator`* | boolean |
| `patient_id`* | string(uuid) |
| `encounter_id`* | string(uuid) |
| `capture_id`* | string(uuid) |
| `kind`* | string |
| `characteristic`* | string |
| `values`* | object |
| `exact`* | object |
| `unit`* | string |
| `flags`* | list[string] |
| `raw_hex`* | string |
| `raw_sha256`* | string |
| `source`* | string |
| `device_time`* | string(date-time) \| null |
| `captured_at`* | string(date-time) |
| `received_at`* | string(date-time) |
| `clock_skew`* | boolean |
| `captured_by`* | string(uuid) \| null |
| `app_version`* | string |
| `status`* | string (pending_review, accepted, rejected) |
| `decision`* | DecisionOut \| null |

### ReceiptOut

| Field | Type |
|---|---|
| `invoice`* | app__schemas__InvoiceOut |
| `items` | list[InvoiceItemOut] |
| `payments` | list[app__schemas__PaymentOut] |
| `refunds` | list[app__schemas__RefundOut] |
| `ledger` | list[LedgerEntryOut] |
| `balance_due`* | number |
| `org_name`* | string |
| `branch_name`* | string |
| `patient_name`* | string |
| `patient_uhid`* | string |

### ReceiveStockIn

| Field | Type |
|---|---|
| `branch_id`* | string(uuid) |
| `drug_id`* | string(uuid) |
| `batch_number`* | string |
| `expiry_date`* | string(date) |
| `quantity`* | integer |
| `unit_cost` | number |
| `supplier` | string |

### ReconciliationOut

| Field | Type |
|---|---|
| `checked_at`* | string(date-time) |
| `issues`* | list[object] |

### RecoveryCodesOut

| Field | Type |
|---|---|
| `recovery_codes`* | list[string] |

### RefreshIn

| Field | Type |
|---|---|
| `refresh_token`* | string |

### RefundDecisionIn

| Field | Type |
|---|---|
| `approve`* | boolean |
| `note` | string |

### RegisterIn

| Field | Type |
|---|---|
| `organization_name`* | string |
| `organization_slug`* | string |
| `full_name`* | string |
| `email`* | string(email) |
| `password`* | string |
| `plan_code` | string \| null |

### RejectIn

| Field | Type |
|---|---|
| `surface`* | string (web, android) |
| `reason`* | string |

### RejectSpecimenIn

| Field | Type |
|---|---|
| `reason`* | string |

### ReminderRunIn

| Field | Type |
|---|---|
| `hours_ahead` | integer \| null |
| `include_follow_ups` | boolean |

### ReminderRunOut

| Field | Type |
|---|---|
| `window_start`* | string(date-time) |
| `window_end`* | string(date-time) |
| `channels`* | list[string] |
| `quiet_hours`* | boolean |
| `appointments`* | integer |
| `follow_ups`* | integer |
| `sent`* | integer |
| `by_status`* | dict[str, integer] |
| `mock_notice`* | string |

### ReorderDraftOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `proposal_id`* | string(uuid) \| null |
| `lines`* | list[-] |
| `status`* | string |
| `created_at`* | string(date-time) |

### ReportSummaryOut

| Field | Type |
|---|---|
| `from_date`* | string(date) |
| `to_date`* | string(date) |
| `ipd`* | IpdReport |
| `finance`* | FinanceReport |
| `inventory`* | InventoryReport |

### RxItemIn

| Field | Type |
|---|---|
| `drug_id`* | string(uuid) |
| `dose`* | string |
| `route` | string |
| `frequency`* | string |
| `duration_days`* | integer |
| `quantity` | string |
| `instructions` | string |
| `dispense_quantity` | integer \| null |

### RxItemOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `prescription_id`* | string(uuid) |
| `drug_id`* | string(uuid) |
| `dose`* | string |
| `route`* | string |
| `frequency`* | string |
| `duration_days`* | integer |
| `quantity`* | string |
| `instructions`* | string |
| `seq`* | integer |
| `dispense_quantity` | integer \| null |
| `drug_name` | string |
| `generic_name` | string |
| `strength` | string |

### RxWarning

| Field | Type |
|---|---|
| `kind`* | string |
| `message`* | string |
| `drug_ids` | list[string(uuid)] |

### RxWarningsOut

| Field | Type |
|---|---|
| `warnings` | list[RxWarning] |
| `blocking` | boolean |

### ScheduleSettings

| Field | Type |
|---|---|
| `slot_minutes` | integer |
| `max_per_slot` | integer |
| `online_booking_enabled` | boolean |

### ScribeAcceptIn

| Field | Type |
|---|---|
| `chief_complaint` | string |
| `history` | string |
| `examination` | string |
| `assessment` | string |
| `plan` | string |
| `reviewed`* | boolean |

### ScribeConsentIn

| Field | Type |
|---|---|
| `patient_verbal_consent`* | boolean |
| `notice_language` | string (en, mr, hi) |

### ScribeSessionIn

| Field | Type |
|---|---|
| `encounter_id`* | string(uuid) |
| `consent`* | ScribeConsentIn |

### ScribeSessionOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `encounter_id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `clinician_id`* | string(uuid) |
| `consent_id`* | string(uuid) |
| `consent_given_at`* | string(date-time) |
| `consent_obtained_by`* | string(uuid) |
| `status`* | string |
| `transcriber`* | string |
| `transcriber_label`* | string |
| `segments` | list[object] |
| `draft` | object \| null |
| `draft_valid` | boolean \| null |
| `validation_problems` | list[string] |
| `prefill` | object \| null |
| `inference`* | string |
| `provider`* | string |
| `model`* | string |
| `audio_stored`* | boolean |
| `audio_retention`* | string |
| `accepted_by` | string(uuid) \| null |
| `accepted_at` | string(date-time) \| null |
| `accepted_fields` | list[string] |
| `disclaimer`* | string |

### ScribeTranscriptIn

| Field | Type |
|---|---|
| `transcript` | string \| null |
| `audio` | AudioMetaIn \| null |

### SendResultOut

| Field | Type |
|---|---|
| `results`* | list[dict[str, string \| integer \| null]] |
| `mock_notice`* | string |

### SessionOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `created_at`* | string(date-time) |
| `expires_at`* | string(date-time) |
| `user_agent`* | string \| null |
| `ip_address`* | string \| null |
| `current`* | boolean |

### SignRxIn

| Field | Type |
|---|---|
| `acknowledge_allergies` | boolean |

### SimulateIn

| Field | Type |
|---|---|
| `outcome` | string (success, failure) |

### SlotOut

| Field | Type |
|---|---|
| `starts_at`* | string(date-time) |
| `ends_at`* | string(date-time) |
| `booked`* | integer |
| `available`* | boolean |

### SlotsOut

| Field | Type |
|---|---|
| `branch_id`* | string(uuid) |
| `date`* | string(date) |
| `provider_user_id`* | string(uuid) \| null |
| `configured`* | boolean |
| `slot_minutes`* | integer |
| `max_per_slot`* | integer |
| `slots`* | list[SlotOut] |

### StaffTaskOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `branch_id`* | string(uuid) \| null |
| `proposal_id`* | string(uuid) \| null |
| `kind`* | string |
| `title`* | string |
| `subject_type`* | string \| null |
| `subject_id`* | string(uuid) \| null |
| `due_date`* | string(date) \| null |
| `priority`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |

### StockAlertOut

| Field | Type |
|---|---|
| `expiring_soon` | list[StockBatchOut] |
| `expired` | list[StockBatchOut] |
| `low_stock` | list[object] |

### StockBatchOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `drug_id`* | string(uuid) |
| `generic_name` | string |
| `batch_number`* | string |
| `expiry_date`* | string(date) |
| `quantity_received`* | integer |
| `quantity_on_hand`* | integer |
| `unit_cost`* | number |
| `supplier`* | string |
| `status`* | string |
| `received_at`* | string(date-time) |

### StockMovementOut

| Field | Type |
|---|---|
| `id`* | integer |
| `batch_id`* | string(uuid) |
| `movement_type`* | string |
| `direction`* | string |
| `quantity`* | integer |
| `dispense_id`* | string(uuid) \| null |
| `reason`* | string |
| `created_at`* | string(date-time) |

### SubscriptionEventOut

| Field | Type |
|---|---|
| `id`* | integer |
| `from_plan`* | string \| null |
| `to_plan`* | string \| null |
| `from_status`* | string \| null |
| `to_status`* | string \| null |
| `reason`* | string |
| `actor_name`* | string \| null |
| `created_at`* | string(date-time) |

### SubscriptionOut

| Field | Type |
|---|---|
| `plan`* | PlanOut |
| `status`* | string |
| `effective_status`* | string |
| `billing_cycle`* | string |
| `trial_ends_at`* | string(date-time) \| null |
| `current_period_end`* | string(date-time) \| null |
| `read_only_reason`* | string \| null |
| `features`* | list[string] |
| `usage`* | dict[str, UsageOut] |

### SupportMessageIn

| Field | Type |
|---|---|
| `body`* | string |

### SupportMessageOut

| Field | Type |
|---|---|
| `id`* | integer |
| `author_name`* | string \| null |
| `author_side`* | string |
| `body`* | string |
| `internal` | boolean |
| `created_at`* | string(date-time) |

### SupportTicketDetailOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `number`* | string |
| `subject`* | string |
| `category`* | string |
| `priority`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |
| `updated_at`* | string(date-time) |
| `created_by_name` | string \| null |
| `organization_name` | string \| null |
| `messages`* | list[SupportMessageOut] |

### SupportTicketIn

| Field | Type |
|---|---|
| `subject`* | string |
| `category`* | string (technical, billing, account, feature_request, data_request, other) |
| `priority` | string (low, normal, high, urgent) |
| `body`* | string |

### SupportTicketOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `number`* | string |
| `subject`* | string |
| `category`* | string |
| `priority`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |
| `updated_at`* | string(date-time) |
| `created_by_name` | string \| null |
| `organization_name` | string \| null |

### TemplateIn

| Field | Type |
|---|---|
| `channel`* | string (email, sms, whatsapp) |
| `purpose`* | string (appointment_reminder, follow_up, missed_appointment, generic) |
| `language`* | string (en, mr, hi) |
| `name`* | string |
| `subject` | string |
| `body`* | string |
| `dlt_template_id` | string \| null |
| `whatsapp_template_name` | string \| null |
| `is_active` | boolean |

### TemplateOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `channel`* | string |
| `purpose`* | string |
| `language`* | string |
| `name`* | string |
| `subject`* | string |
| `body`* | string |
| `dlt_template_id`* | string \| null |
| `whatsapp_template_name`* | string \| null |
| `is_active`* | boolean |
| `is_default`* | boolean |
| `placeholders` | list[string] |
| `updated_at`* | string(date-time) |

### TemplateUpdateIn

| Field | Type |
|---|---|
| `name` | string \| null |
| `subject` | string \| null |
| `body` | string \| null |
| `dlt_template_id` | string \| null |
| `whatsapp_template_name` | string \| null |
| `is_active` | boolean \| null |

### TokenPair

| Field | Type |
|---|---|
| `access_token`* | string |
| `refresh_token`* | string |
| `token_type` | string |
| `expires_in`* | integer |

### TotpCodeIn

| Field | Type |
|---|---|
| `code`* | string |

### TotpSetupOut

| Field | Type |
|---|---|
| `secret`* | string |
| `otpauth_uri`* | string |

### TransferIn

| Field | Type |
|---|---|
| `to_bed_id`* | string(uuid) |
| `reason`* | string |

### UsageBreakdownOut

| Field | Type |
|---|---|
| `period`* | string |
| `used_credits`* | integer |
| `limit_credits`* | integer \| null |
| `purchased_balance` | integer |
| `rows`* | list[UsageBreakdownRow] |
| `features`* | object |

### UsageBreakdownRow

| Field | Type |
|---|---|
| `feature`* | string |
| `task`* | string |
| `inference`* | string |
| `requests`* | integer |
| `ok`* | integer |
| `credits`* | integer |

### UsageOut

| Field | Type |
|---|---|
| `limit`* | integer \| null |
| `used`* | integer |

### UserOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `email`* | string(email) |
| `full_name`* | string |
| `status`* | string |
| `registration_number` | string \| null |

### ValidationError

| Field | Type |
|---|---|
| `loc`* | list[string \| integer] |
| `msg`* | string |
| `type`* | string |
| `input` | any |
| `ctx` | object |

### VerifyIn

| Field | Type |
|---|---|
| `provider_payment_id`* | string |
| `signature`* | string |

### VitalsIn

| Field | Type |
|---|---|
| `bp_systolic` | integer \| null |
| `bp_diastolic` | integer \| null |
| `pulse` | integer \| null |
| `temperature_c` | number \| null |
| `spo2` | integer \| null |
| `respiratory_rate` | integer \| null |
| `weight_kg` | number \| null |
| `height_cm` | number \| null |
| `notes` | string |

### VitalsOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `encounter_id`* | string(uuid) |
| `bp_systolic`* | integer \| null |
| `bp_diastolic`* | integer \| null |
| `pulse`* | integer \| null |
| `temperature_c`* | number \| null |
| `spo2`* | integer \| null |
| `respiratory_rate`* | integer \| null |
| `weight_kg`* | number \| null |
| `height_cm`* | number \| null |
| `notes`* | string |
| `recorded_at`* | string(date-time) |
| `device_reading_id` | string(uuid) \| null |

### WardIn

| Field | Type |
|---|---|
| `branch_id`* | string(uuid) |
| `name`* | string |
| `code`* | string |
| `ward_type` | string |

### WardOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `name`* | string |
| `code`* | string |
| `ward_type`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |
| `bed_count` | integer |
| `occupied_count` | integer |
| `available_count` | integer |

### WizardOut

| Field | Type |
|---|---|
| `steps`* | list[WizardStepOut] |
| `current_step`* | string |
| `finished`* | boolean |
| `finished_at`* | string(date-time) \| null |
| `should_show`* | boolean |
| `progress_percent`* | integer |

### WizardPatchIn

| Field | Type |
|---|---|
| `current_step` | string \| null |
| `finished` | boolean \| null |

### WizardStepIn

| Field | Type |
|---|---|
| `status`* | string (done, skipped, todo) |

### WizardStepOut

| Field | Type |
|---|---|
| `key`* | string |
| `status`* | string (done, skipped, todo) |
| `data_ready`* | boolean |

### WorkingHoursIn

| Field | Type |
|---|---|
| `sessions`* | list[WorkingSessionIn] |

### WorkingHoursOut

| Field | Type |
|---|---|
| `branch_id`* | string(uuid) |
| `sessions`* | list[WorkingSessionOut] |

### WorkingSessionIn

| Field | Type |
|---|---|
| `weekday`* | integer |
| `opens_at`* | string(time) |
| `closes_at`* | string(time) |
| `break_starts_at` | string(time) \| null |
| `break_ends_at` | string(time) \| null |

### WorkingSessionOut

| Field | Type |
|---|---|
| `weekday`* | integer |
| `opens_at`* | string(time) |
| `closes_at`* | string(time) |
| `break_starts_at`* | string(time) \| null |
| `break_ends_at`* | string(time) \| null |

### app__schemas__InvoiceOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `branch_id`* | string(uuid) |
| `patient_id`* | string(uuid) |
| `encounter_id`* | string(uuid) \| null |
| `invoice_number`* | string |
| `status`* | string |
| `subtotal`* | number |
| `discount`* | number |
| `tax_total`* | number |
| `total`* | number |
| `amount_paid`* | number |
| `notes`* | string |
| `issued_at`* | string(date-time) \| null |
| `created_at`* | string(date-time) |

### app__schemas__PaymentOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `invoice_id`* | string(uuid) |
| `amount`* | number |
| `method`* | string |
| `gateway`* | string |
| `status`* | string |
| `gateway_ref`* | string |
| `failure_reason`* | string |
| `created_at`* | string(date-time) |

### app__schemas__RefundIn

| Field | Type |
|---|---|
| `amount`* | number |
| `reason`* | string |

### app__schemas__RefundOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `payment_id`* | string(uuid) |
| `amount`* | number |
| `reason`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |

### app__schemas_billing__InvoiceOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `number`* | string |
| `kind`* | string |
| `order_id`* | string(uuid) |
| `related_invoice_id`* | string(uuid) \| null |
| `issued_at`* | string(date-time) |
| `period_start`* | string(date-time) \| null |
| `period_end`* | string(date-time) \| null |
| `seller`* | object |
| `buyer`* | object |
| `lines`* | list[-] |
| `subtotal_paise`* | integer |
| `tax_breakdown`* | object |
| `tax_paise`* | integer |
| `total_paise`* | integer |
| `currency`* | string |

### app__schemas_billing__PaymentOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `order_id`* | string(uuid) |
| `provider`* | string |
| `provider_payment_id`* | string |
| `amount_paise`* | integer |
| `currency`* | string |
| `status`* | string |
| `method`* | string \| null |
| `source`* | string |
| `error`* | string \| null |
| `created_at`* | string(date-time) |

### app__schemas_billing__RefundIn

| Field | Type |
|---|---|
| `payment_id`* | string(uuid) |
| `amount_paise`* | integer |
| `reason`* | string |

### app__schemas_billing__RefundOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `payment_id`* | string(uuid) |
| `amount_paise`* | integer |
| `reason`* | string |
| `status`* | string |
| `requested_by`* | string(uuid) \| null |
| `decided_by`* | string(uuid) \| null |
| `decided_at`* | string(date-time) \| null |
| `decision_note`* | string \| null |
| `provider_refund_id`* | string \| null |
| `error`* | string \| null |
| `created_at`* | string(date-time) |
