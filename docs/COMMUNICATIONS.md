# Patient communications v2 and follow-up CRM

Status: implemented with **mock delivery only**. No SMS, WhatsApp or e-mail reaches a
patient unless `COMMS_LIVE_ENABLED=true` and vendor credentials are configured (see
`apps/api/app/comms/base.py`). Every API response that reports sending includes
`mock_notice` ("mock outbox — not sent"), and the web UI shows a banner.

## Message content rule (no clinical details)

Messages travel over third-party networks, show up on lock screens and are often read by
family members. They therefore carry **logistics only**: patient first name, clinic /
branch / phone, date and time, and doctor name.

* Allowed placeholders: `{patient_first_name}` `{clinic_name}` `{clinic_phone}`
  `{branch_name}` `{doctor_name}` `{appointment_date}` `{appointment_time}`
  `{follow_up_date}`.
* Any other placeholder is rejected (422). Clinical / identifying ones (`{diagnosis}`,
  `{medicines}`, `{lab_result}`, `{reason}`, `{notes}`, `{uhid}`, `{allergies}`, …, see
  `DISALLOWED_PLACEHOLDERS` in `app/comms/templates.py`) get an explicit
  "clinical or identifying" error.
* Values are filled server-side from tenant data; callers cannot inject text into a body.
* Free-text clinical wording typed by staff is a policy violation; template changes are
  audited (`comms.template_created` / `comms.template_updated`).
* Follow-up `reason` is a short administrative label for the worklist and is never placed
  into a message.

## Sending pipeline (`app/comms/engine.py::deliver`)

1. Active template for channel / purpose / patient language (fallback: clinic default, EN).
2. Dedupe key (appointment + start time + template, follow-up + due date + template,
   missed appointment + template) — a delivered key is never sent again.
3. Consent: an explicit, current **opt-in** for the channel is required. Opt-out always
   wins: after an opt-out only the patient's own request (`patient_request`) can opt back
   in; staff updates and replies can only opt out.
4. Recipient (phone for SMS/WhatsApp, the optional preference e-mail for e-mail).
5. Quiet hours (clinic-local, default 21:00–08:00) → `skipped_quiet_hours`, retried by the
   next run.
6. Plan quota `sms_monthly` / `whatsapp_monthly` (e-mail has no plan limit — no new LIMITS
   key was added) and the clinic's monthly spend cap → `skipped_quota`. Never silent.
7. Provider-agnostic `app.comms.send` → `sent_mock` / `suppressed` / `failed` / `sent`.

Each attempt is one append-only row in `comms_delivery_log` (masked recipient, provider,
cost estimate in paise from `COMMS_COST_PAISE_{EMAIL,SMS,WHATSAPP}`, default 0, and the
appointment / follow-up it belongs to).

## Scheduling reminders

`POST /api/v1/comms/reminders/run` runs on demand ("Run reminders now"). For automation use
the host's existing scheduler — no new infrastructure:

```
# crontab: hourly at :07, every active clinic
7 * * * * cd /srv/hms/apps/api && python -m app.comms.reminder_job --all-active
```

or a Kubernetes CronJob with the same command. Runs are idempotent and quiet-hours aware,
so hourly (or accidental double) runs never double-send.

## Known gaps

* No inbound STOP webhook / tokenised unsubscribe link yet: staff record a patient's reply
  with source `patient_reply` via `POST /comms/patients/{id}/opt-out`.
* Sending is synchronous inside the request/job (status `queued` is reserved for a future
  async worker).
* `entitlements.current_usage()` still reports `sms_monthly` / `whatsapp_monthly` as 0 on
  the subscription page; `/comms/overview` shows the real counts (integration follow-up:
  return `engine.usage(...)` there).
