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

Spec: **Aditya BioNova Smart HMS API** version `0.1.0-m1`, OpenAPI 3.1.0. 114 operations in 18 tags.

### Summary

| Tag | Method | Path | Permission | Idempotency-Key |
|---|---|---|---|---|
| appointments | GET | `/api/v1/appointments` | `appointment.read` |  |
| appointments | POST | `/api/v1/appointments` | `appointment.write` |  |
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
| dev | GET | `/api/v1/dev/outbox` | public |  |
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
| prescriptions | GET | `/api/v1/prescriptions` | `prescription.read` |  |
| prescriptions | POST | `/api/v1/prescriptions` | `prescription.sign` | yes |
| prescriptions | GET | `/api/v1/prescriptions/drugs` | `prescription.read` |  |
| prescriptions | GET | `/api/v1/prescriptions/{rx_id}` | `prescription.read` |  |
| prescriptions | POST | `/api/v1/prescriptions/{rx_id}/amend` | `prescription.sign` |  |
| prescriptions | POST | `/api/v1/prescriptions/{rx_id}/sign` | `prescription.sign` |  |
| prescriptions | POST | `/api/v1/prescriptions/{rx_id}/warnings` | `prescription.sign` |  |
| reports | GET | `/api/v1/reports/summary` | `report.read` |  |
| system | GET | `/api/v1/health` | public |  |
| system | GET | `/api/v1/health/ready` | public |  |

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
- Response: `201 PaymentOut`

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
- Response: `200 PaymentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `payment_id` | path | string(uuid) | yes |

#### `POST /api/v1/billing/payments/{payment_id}/fail`

**Sandbox Fail**

- Permission: `billing.payment`
- operationId: `sandbox_fail_api_v1_billing_payments__payment_id__fail_post`
- Request body: -
- Response: `200 PaymentOut`

| Parameter | In | Type | Required |
|---|---|---|---|
| `payment_id` | path | string(uuid) | yes |

#### `POST /api/v1/billing/payments/{payment_id}/refund`

**Refund Payment**

- Permission: `billing.refund`
- operationId: `refund_payment_api_v1_billing_payments__payment_id__refund_post`
- Request body: `RefundIn`
- Response: `201 RefundOut`

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

### BranchIn

| Field | Type |
|---|---|
| `name`* | string |
| `code`* | string |

### BranchOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `organization_id`* | string(uuid) |
| `name`* | string |
| `code`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |

### CancelLabOrderIn

| Field | Type |
|---|---|
| `reason`* | string |

### CollectSpecimenIn

| Field | Type |
|---|---|
| `specimen_type`* | string |

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
| `payments` | list[PaymentOut] |

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

### InvoiceOut

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

### OrganizationOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `name`* | string |
| `slug`* | string |
| `status`* | string |

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

### PaymentOut

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

### ProfileUpdateIn

| Field | Type |
|---|---|
| `full_name` | string \| null |
| `registration_number` | string \| null |

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

### ReceiptOut

| Field | Type |
|---|---|
| `invoice`* | InvoiceOut |
| `items` | list[InvoiceItemOut] |
| `payments` | list[PaymentOut] |
| `refunds` | list[RefundOut] |
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

### RecoveryCodesOut

| Field | Type |
|---|---|
| `recovery_codes`* | list[string] |

### RefreshIn

| Field | Type |
|---|---|
| `refresh_token`* | string |

### RefundIn

| Field | Type |
|---|---|
| `amount`* | number |
| `reason`* | string |

### RefundOut

| Field | Type |
|---|---|
| `id`* | string(uuid) |
| `payment_id`* | string(uuid) |
| `amount`* | number |
| `reason`* | string |
| `status`* | string |
| `created_at`* | string(date-time) |

### RegisterIn

| Field | Type |
|---|---|
| `organization_name`* | string |
| `organization_slug`* | string |
| `full_name`* | string |
| `email`* | string(email) |
| `password`* | string |

### RejectSpecimenIn

| Field | Type |
|---|---|
| `reason`* | string |

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
