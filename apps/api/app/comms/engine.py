"""Communications v2 engine: consent, quiet hours, quotas, delivery log,
appointment reminders and follow-up / missed-visit messages.

Every patient message goes through :func:`deliver`, which — in this order —
resolves the active template, refuses duplicates (dedupe key), checks
consent (explicit opt-in, opt-out always wins), the recipient, the clinic's
quiet hours, the plan quota (``sms_monthly`` / ``whatsapp_monthly``) and the
clinic's monthly spend cap, and only then hands the rendered message to the
provider-agnostic :func:`app.comms.send`. With the default ``mock``
providers nothing leaves the server: the message lands in the dev outbox and
the attempt is logged as ``sent_mock`` ("mock outbox — not sent").

Each attempt (also the skipped ones) is one append-only row in
``comms_delivery_log``. Attempts for one clinic are serialized by a
transaction-scoped advisory lock so quotas and dedupe hold under concurrency
(the partial unique index on ``dedupe_key`` is the database backstop).

Scheduling: :func:`run_reminders` is a plain function. ``POST
/comms/reminders/run`` calls it on demand, and ``python -m
app.comms.reminder_job`` runs it for one or all clinics — schedule that
command with the host's existing cron / systemd timer / Kubernetes CronJob
(e.g. hourly between 08:00 and 21:00 IST). No new infrastructure is needed;
the run is idempotent, so overlapping or repeated runs never double-send.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..entitlements import Entitlements, load_entitlements
from ..models import Appointment, Branch, Organization, Patient, User
from ..models_comms import (
    CommsConsent,
    CommsConsentEvent,
    CommsDelivery,
    CommsPatientPreference,
    CommsTemplate,
    CommsTenantSettings,
    FollowUp,
)
from ..timeutil import clinic_tz
from . import templates as tpl
from .base import Message, send

# statuses that consumed quota (a message was handed to a provider)
QUOTA_STATUSES = ("queued", "sent", "sent_mock")
# statuses that block a repeat for the same dedupe key
DELIVERED_STATUSES = QUOTA_STATUSES + ("suppressed",)
SKIP_STATUSES = ("skipped_no_consent", "skipped_quota", "skipped_quiet_hours",
                 "skipped_no_recipient", "skipped_no_template")
LIMIT_KEYS = {"sms": "sms_monthly", "whatsapp": "whatsapp_monthly", "email": None}

CONSENT_SOURCES = ("registration_form", "patient_request", "patient_reply", "staff_update")
OPT_IN_SOURCES = ("registration_form", "patient_request")


class CommsCostSettings(BaseSettings):
    """Per-message cost ESTIMATES in paise (env ``COMMS_COST_PAISE_SMS`` …).

    Defaults are 0 because the default providers are mock; set them to the
    contracted vendor rates before enabling live delivery so the spend cap
    and the delivery log reflect real money."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore")
    comms_cost_paise_email: int = 0
    comms_cost_paise_sms: int = 0
    comms_cost_paise_whatsapp: int = 0

    def for_channel(self, channel: str) -> int:
        return max(0, int(getattr(self, f"comms_cost_paise_{channel}", 0)))


def cost_settings() -> CommsCostSettings:
    return CommsCostSettings()


def utcnow() -> datetime:
    """Clock seam (tests pin it to exercise quiet hours deterministically)."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------- helpers
def org_tz(org: Organization | None) -> tzinfo:
    name = getattr(org, "timezone", None)
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return clinic_tz()


def period_of(moment: datetime, tz: tzinfo) -> str:
    return moment.astimezone(tz).strftime("%Y-%m")


def in_quiet_hours(local: datetime, start: int, end: int) -> bool:
    """Quiet window [start, end) in clinic-local hours; wraps midnight."""
    if start == end:
        return False
    h = local.hour
    return (h >= start or h < end) if start > end else (start <= h < end)


def mask_recipient(channel: str, to: str | None) -> str | None:
    if not to:
        return None
    if channel == "email":
        local, _, domain = to.partition("@")
        return f"{local[:1]}***@{domain}" if domain else "***"
    digits = "".join(c for c in to if c.isdigit())
    return f"******{digits[-4:]}" if len(digits) >= 4 else "****"


def first_name(full_name: str) -> str:
    words = (full_name or "").split()
    parts = [p for p in words if p.rstrip(".").lower() not in
             ("mr", "mrs", "ms", "miss", "shri", "smt", "kum", "dr")]
    return (parts or words or [""])[0]


def _fmt_date(d: date | datetime, lang: str) -> str:
    return d.strftime("%d %b %Y") if lang == "en" else d.strftime("%d/%m/%Y")


def _fmt_time(dt: datetime, lang: str) -> str:
    return dt.strftime("%I:%M %p").lstrip("0") if lang == "en" else dt.strftime("%H:%M")


def _lock(db: Session, org_id: uuid.UUID) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
               {"k": f"comms:{org_id}"})


# --------------------------------------------------------------------- tenant setup
def ensure_tenant(db: Session, org_id: uuid.UUID,
                  actor_user_id: uuid.UUID | None = None) -> CommsTenantSettings:
    """Create the clinic's comms settings row and, the first time only, the
    default EN / मराठी / हिंदी templates (lazy seeding)."""
    inserted = db.execute(
        pg_insert(CommsTenantSettings).values(organization_id=org_id)
        .on_conflict_do_nothing(index_elements=["organization_id"])
        .returning(CommsTenantSettings.organization_id)
    ).first()
    if inserted is not None:
        for channel, d, body in tpl.default_templates():
            db.add(CommsTemplate(
                organization_id=org_id, channel=channel, purpose=d.purpose,
                language=d.language, name=f"Default {d.purpose.replace('_', ' ')} "
                f"({channel}, {d.language})", subject=d.subject if channel == "email" else "",
                body=body, is_active=True, is_default=True, created_by=actor_user_id))
        db.flush()
    return db.get(CommsTenantSettings, org_id, populate_existing=True)


# --------------------------------------------------------------------- consent
def consent_status(db: Session, org_id: uuid.UUID, patient_id: uuid.UUID,
                   channel: str) -> str | None:
    row = db.get(CommsConsent, (org_id, patient_id, channel))
    return row.status if row else None


class ConsentError(ValueError):
    pass


def set_consent(db: Session, org_id: uuid.UUID, patient_id: uuid.UUID, channel: str,
                status: str, source: str, actor_user_id: uuid.UUID | None) -> CommsConsent:
    """Record a consent change. Opt-out always wins: once a patient opted out,
    only the patient's own request can opt them back in, and staff updates /
    replies can only ever opt OUT."""
    if channel not in tpl.CHANNELS:
        raise ConsentError("unknown channel")
    if source not in CONSENT_SOURCES:
        raise ConsentError("unknown consent source")
    current = db.get(CommsConsent, (org_id, patient_id, channel), with_for_update=True)
    if status == "opted_in":
        if source not in OPT_IN_SOURCES:
            raise ConsentError("an opt-in must come from the patient (registration form "
                               "or the patient's own request)")
        if current is not None and current.status == "opted_out" and source != "patient_request":
            raise ConsentError("patient has opted out; only the patient's own request can "
                               "opt them back in")
    now = utcnow()
    if current is None:
        current = CommsConsent(organization_id=org_id, patient_id=patient_id, channel=channel,
                               status=status, source=source, actor_user_id=actor_user_id,
                               recorded_at=now)
        db.add(current)
    else:
        current.status, current.source = status, source
        current.actor_user_id, current.recorded_at = actor_user_id, now
    db.add(CommsConsentEvent(organization_id=org_id, patient_id=patient_id, channel=channel,
                             status=status, source=source, actor_user_id=actor_user_id,
                             recorded_at=now))
    db.flush()
    return current


# --------------------------------------------------------------------- usage
def usage(db: Session, org_id: uuid.UUID, period: str) -> dict[str, dict[str, int]]:
    rows = db.execute(
        select(CommsDelivery.channel, func.count(), func.coalesce(func.sum(
            CommsDelivery.cost_paise), 0))
        .where(CommsDelivery.organization_id == org_id, CommsDelivery.period == period,
               CommsDelivery.status.in_(QUOTA_STATUSES))
        .group_by(CommsDelivery.channel)).all()
    out = {c: {"used": 0, "cost_paise": 0} for c in tpl.CHANNELS}
    for channel, n, cost in rows:
        out[channel] = {"used": int(n), "cost_paise": int(cost)}
    return out


def channel_limit(ent: Entitlements, channel: str) -> int | None:
    key = LIMIT_KEYS.get(channel)
    return ent.limits.get(key) if key else None


def channel_entitled(ent: Entitlements, channel: str) -> bool:
    return f"comms_{channel}" in ent.features


# --------------------------------------------------------------------- delivery
@dataclass
class TenantCtx:
    org: Organization
    settings: CommsTenantSettings
    ent: Entitlements
    tz: tzinfo
    costs: CommsCostSettings = field(default_factory=cost_settings)

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id


def load_ctx(db: Session, org_id: uuid.UUID,
             actor_user_id: uuid.UUID | None = None) -> TenantCtx:
    settings = ensure_tenant(db, org_id, actor_user_id)
    org = db.get(Organization, org_id)
    return TenantCtx(org=org, settings=settings, ent=load_entitlements(db, org_id),
                     tz=org_tz(org))


def resolve_template(db: Session, ctx: TenantCtx, channel: str, purpose: str,
                     language: str) -> CommsTemplate | None:
    for lang in dict.fromkeys((language, ctx.org.default_language, "en")):
        row = db.scalar(select(CommsTemplate).where(
            CommsTemplate.organization_id == ctx.org_id, CommsTemplate.channel == channel,
            CommsTemplate.purpose == purpose, CommsTemplate.language == lang,
            CommsTemplate.is_active.is_(True)))
        if row is not None:
            return row
    return None


def patient_language(db: Session, ctx: TenantCtx, patient_id: uuid.UUID) -> str:
    pref = db.get(CommsPatientPreference, (ctx.org_id, patient_id))
    return (pref.preferred_language if pref and pref.preferred_language
            else ctx.org.default_language or "en")


def recipient_for(db: Session, ctx: TenantCtx, patient: Patient, channel: str) -> str | None:
    if channel == "email":
        pref = db.get(CommsPatientPreference, (ctx.org_id, patient.id))
        return pref.email if pref and pref.email else None
    return patient.phone or None


def message_values(db: Session, ctx: TenantCtx, patient: Patient, language: str, *,
                   appointment: Appointment | None = None,
                   follow_up: FollowUp | None = None) -> dict[str, str]:
    branch = None
    branch_id = (appointment.branch_id if appointment else
                 follow_up.branch_id if follow_up else None)
    if branch_id:
        branch = db.get(Branch, branch_id)
    doctor_id = (appointment.provider_user_id if appointment else
                 follow_up.assigned_user_id if follow_up else None)
    doctor = db.get(User, doctor_id) if doctor_id else None
    values = {
        "patient_first_name": first_name(patient.full_name),
        "clinic_name": ctx.org.name,
        "clinic_phone": (getattr(branch, "phone", None) or ctx.org.phone
                         or tpl.FALLBACKS["clinic_phone"][language]),
        "branch_name": branch.name if branch else ctx.org.name,
        "doctor_name": doctor.full_name if doctor else tpl.FALLBACKS["doctor_name"][language],
        "appointment_date": "",
        "appointment_time": "",
        "follow_up_date": "",
    }
    if appointment is not None:
        local = appointment.starts_at.astimezone(ctx.tz)
        values["appointment_date"] = _fmt_date(local, language)
        values["appointment_time"] = _fmt_time(local, language)
    if follow_up is not None:
        values["follow_up_date"] = _fmt_date(follow_up.due_date, language)
    return values


@dataclass
class Outcome:
    status: str                       # delivery status, or "duplicate"
    channel: str
    log_id: int | None = None


def deliver(db: Session, ctx: TenantCtx, *, patient: Patient, channel: str, purpose: str,
            appointment: Appointment | None = None, follow_up: FollowUp | None = None,
            dedupe_scope: str | None = None, trigger: str = "manual",
            actor_user_id: uuid.UUID | None = None, correlation_id: str | None = None,
            now: datetime | None = None) -> Outcome:
    now = now or utcnow()
    _lock(db, ctx.org_id)
    period = period_of(now, ctx.tz)
    language = patient_language(db, ctx, patient.id)
    template = resolve_template(db, ctx, channel, purpose, language)
    dedupe_key = None
    if dedupe_scope:
        # One message per occasion, channel and purpose. The template is NOT
        # part of the key: replacing or re-activating a template, or a change
        # of the patient's language, must never re-send a reminder (M8.1).
        dedupe_key = f"{dedupe_scope}|{channel}|{purpose}"[:200]
        if db.scalar(select(func.count()).select_from(CommsDelivery).where(
                CommsDelivery.organization_id == ctx.org_id,
                CommsDelivery.channel == channel,
                or_(CommsDelivery.dedupe_key == dedupe_key,
                    # keys written before M8.1: "<scope>|tpl:<template id>"
                    CommsDelivery.dedupe_key.startswith(f"{dedupe_scope}|tpl:",
                                                        autoescape=True)),
                CommsDelivery.status.in_(DELIVERED_STATUSES))):
            return Outcome("duplicate", channel)

    to = recipient_for(db, ctx, patient, channel)
    provider_name = {"email": "comms_email_provider", "sms": "comms_sms_provider",
                     "whatsapp": "comms_whatsapp_provider"}[channel]
    from ..config import get_settings

    provider = getattr(get_settings(), provider_name)
    cost = ctx.costs.for_channel(channel)

    def log(status: str, *, error: str | None = None, cost_paise: int = 0) -> Outcome:
        if status in SKIP_STATUSES and dedupe_key and db.scalar(
                select(func.count()).select_from(CommsDelivery).where(
                    CommsDelivery.organization_id == ctx.org_id,
                    CommsDelivery.dedupe_key == dedupe_key,
                    CommsDelivery.status == status)):
            # same skip already on record for this message: keep the log readable
            return Outcome(status, channel)
        row = CommsDelivery(
            organization_id=ctx.org_id, channel=channel, purpose=purpose,
            language=template.language if template else language,
            template_id=template.id if template else None, patient_id=patient.id,
            appointment_id=appointment.id if appointment else None,
            follow_up_id=follow_up.id if follow_up else None,
            recipient_masked=mask_recipient(channel, to), provider=provider, status=status,
            cost_paise=cost_paise, period=period, dedupe_key=dedupe_key, trigger=trigger,
            error=(error or "")[:300] or None, actor_user_id=actor_user_id,
            correlation_id=correlation_id, created_at=now)
        db.add(row)
        db.flush()
        return Outcome(status, channel, row.id)

    if template is None:
        return log("skipped_no_template")
    if consent_status(db, ctx.org_id, patient.id, channel) != "opted_in":
        return log("skipped_no_consent")
    if not to:
        return log("skipped_no_recipient")
    s = ctx.settings
    if in_quiet_hours(now.astimezone(ctx.tz), s.quiet_start_hour, s.quiet_end_hour):
        return log("skipped_quiet_hours")
    used = usage(db, ctx.org_id, period)
    limit = channel_limit(ctx.ent, channel)
    if limit is not None and used[channel]["used"] + 1 > limit:
        return log("skipped_quota", error=f"plan limit {LIMIT_KEYS[channel]} ({limit}) reached")
    if s.monthly_spend_cap_paise is not None:
        spent = sum(v["cost_paise"] for v in used.values())
        if spent + cost > s.monthly_spend_cap_paise:
            return log("skipped_quota", error="monthly spend cap reached")

    values = message_values(db, ctx, patient, template.language, appointment=appointment,
                            follow_up=follow_up)
    body = tpl.render(template.body, values)
    subject = tpl.render(template.subject, values)
    ref = template.dlt_template_id if channel == "sms" else (
        template.whatsapp_template_name if channel == "whatsapp" else None)
    result = send(Message(channel=channel, to=to, body=body, subject=subject, template=ref,
                          variables=tpl.ordered_variables(template.body, values)))
    status = {"recorded": "sent_mock", "sent": "sent", "suppressed": "suppressed",
              "failed": "failed"}[result.status]
    return log(status, error=result.error,
               cost_paise=cost if status in QUOTA_STATUSES else 0)


def channels_for(ctx: TenantCtx, requested: list[str] | None = None) -> list[str]:
    wanted = requested or list(ctx.settings.reminder_channels or [])
    return [c for c in tpl.CHANNELS if c in wanted and channel_entitled(ctx.ent, c)]


# --------------------------------------------------------------------- reminders
def _bump(summary: dict, outcome: Outcome) -> None:
    summary["by_status"][outcome.status] = summary["by_status"].get(outcome.status, 0) + 1


def run_reminders(db: Session, org_id: uuid.UUID, *, hours_ahead: int | None = None,
                  include_follow_ups: bool = True, trigger: str = "reminder_run",
                  actor_user_id: uuid.UUID | None = None, correlation_id: str | None = None,
                  now: datetime | None = None) -> dict:
    """Queue reminders for scheduled appointments starting within the next
    ``hours_ahead`` hours (and planned follow-ups falling due in that window).
    Idempotent per appointment + template + start time."""
    now = now or utcnow()
    ctx = load_ctx(db, org_id, actor_user_id)
    hours = hours_ahead or ctx.settings.reminder_hours_ahead
    channels = channels_for(ctx)
    local = now.astimezone(ctx.tz)
    summary: dict = {
        "window_start": now, "window_end": now + timedelta(hours=hours),
        "channels": channels, "quiet_hours": in_quiet_hours(
            local, ctx.settings.quiet_start_hour, ctx.settings.quiet_end_hour),
        "appointments": 0, "follow_ups": 0, "by_status": {},
    }
    appts = db.scalars(select(Appointment).where(
        Appointment.organization_id == org_id, Appointment.status == "scheduled",
        Appointment.starts_at > now, Appointment.starts_at <= now + timedelta(hours=hours))
        .order_by(Appointment.starts_at)).all()
    for appt in appts:
        patient = db.get(Patient, appt.patient_id)
        if patient is None or patient.status != "active":
            continue
        summary["appointments"] += 1
        for channel in channels:
            _bump(summary, deliver(
                db, ctx, patient=patient, channel=channel, purpose="appointment_reminder",
                appointment=appt, trigger=trigger, actor_user_id=actor_user_id,
                correlation_id=correlation_id, now=now,
                dedupe_scope=f"appt:{appt.id}:{int(appt.starts_at.timestamp())}"))
    if include_follow_ups:
        last_day = local.date() + timedelta(days=max(1, math.ceil(hours / 24)))
        fus = db.scalars(select(FollowUp).where(
            FollowUp.organization_id == org_id, FollowUp.status == "planned",
            FollowUp.due_date >= local.date(), FollowUp.due_date <= last_day)).all()
        for fu in fus:
            patient = db.get(Patient, fu.patient_id)
            if patient is None or patient.status != "active":
                continue
            summary["follow_ups"] += 1
            sent = False
            for channel in channels:
                outcome = deliver(db, ctx, patient=patient, channel=channel, purpose="follow_up",
                                  follow_up=fu, trigger=trigger, actor_user_id=actor_user_id,
                                  correlation_id=correlation_id, now=now,
                                  dedupe_scope=f"fu:{fu.id}:{fu.due_date.isoformat()}")
                _bump(summary, outcome)
                sent = sent or outcome.status in DELIVERED_STATUSES
            if sent:
                fu.status, fu.reminded_at, fu.updated_at = "reminded", now, now
        db.flush()
    summary["sent"] = sum(summary["by_status"].get(s, 0) for s in QUOTA_STATUSES)
    return summary


def missed_appointments(db: Session, org_id: uuid.UUID, *, days: int = 7,
                        grace_minutes: int = 30, now: datetime | None = None
                        ) -> list[Appointment]:
    """Appointments whose start passed (plus grace) but that were never
    checked in: still ``scheduled`` or marked ``no_show``."""
    now = now or utcnow()
    return list(db.scalars(select(Appointment).where(
        Appointment.organization_id == org_id,
        Appointment.status.in_(("scheduled", "no_show")),
        Appointment.starts_at < now - timedelta(minutes=grace_minutes),
        Appointment.starts_at >= now - timedelta(days=days))
        .order_by(Appointment.starts_at.desc())).all())
