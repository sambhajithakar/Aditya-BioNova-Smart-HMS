"""Communications v2 (tenant side): templates, consent, delivery log, quotas,
appointment reminders.

Nothing here contacts a real recipient by default: the providers are
``mock`` unless ``COMMS_LIVE_ENABLED`` and vendor credentials are configured,
and every response that reports sending says so ("mock outbox — not sent").
Channel availability follows the edition (``comms_email`` / ``comms_sms`` /
``comms_whatsapp``); quotas follow the plan limits ``sms_monthly`` /
``whatsapp_monthly`` (e-mail has no plan limit, only the clinic spend cap).
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auditing import record_event
from ..comms import engine
from ..comms import templates as tpl
from ..config import get_settings
from ..db import get_db
from ..deps import Principal, get_client_ip, get_correlation_id, require_permission
from ..models import Patient, User
from ..models_comms import (
    CommsConsent,
    CommsConsentEvent,
    CommsDelivery,
    CommsPatientPreference,
    CommsTemplate,
)
from ..schemas_comms import (
    TEMPLATE_RULE,
    ChannelUsage,
    CommsOverview,
    CommsSettingsIn,
    CommsSettingsOut,
    ConsentEventOut,
    ConsentIn,
    ConsentOut,
    ConsentStats,
    DeliveryOut,
    DeliveryPage,
    OptOutIn,
    PatientCommsOut,
    PlaceholderCatalog,
    PreferencesIn,
    PreviewIn,
    PreviewOut,
    ReminderRunIn,
    ReminderRunOut,
    TemplateIn,
    TemplateOut,
    TemplateUpdateIn,
)

router = APIRouter(prefix="/comms", tags=["communications"])


def mock_notice() -> str:
    s = get_settings()
    providers = {s.comms_email_provider, s.comms_sms_provider, s.comms_whatsapp_provider}
    if not s.comms_live_enabled or providers == {"mock"}:
        return "mock outbox — not sent: messages are recorded locally and no patient is contacted"
    return "live delivery enabled for configured providers"


def _audit(db: Session, principal: Principal, request: Request, action: str,
           resource_type: str, resource_id: str | None, metadata: dict | None = None) -> None:
    record_event(db, action=action, organization_id=str(principal.organization_id),
                 actor_user_id=str(principal.user_id), resource_type=resource_type,
                 resource_id=resource_id, metadata=metadata or {},
                 correlation_id=get_correlation_id(request), ip_address=get_client_ip(request))


def _tpl_out(t: CommsTemplate) -> TemplateOut:
    out = TemplateOut.model_validate(t)
    out.placeholders = sorted(set(tpl.placeholders_in(t.body) + tpl.placeholders_in(t.subject)))
    return out


def _check_template(channel: str, body: str, subject: str) -> None:
    errors = tpl.validate_template(channel, body, subject)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))


def _require_channel(ctx: engine.TenantCtx, channel: str) -> None:
    if not engine.channel_entitled(ctx.ent, channel):
        raise HTTPException(status_code=403,
                            detail=f"Feature not included in your plan: comms_{channel}")


# --------------------------------------------------------------------- catalogue / preview
@router.get("/placeholders", response_model=PlaceholderCatalog)
def placeholders(
    principal: Principal = Depends(require_permission("comms.read")),
) -> PlaceholderCatalog:
    return PlaceholderCatalog(allowed=tpl.ALLOWED_PLACEHOLDERS,
                              disallowed=list(tpl.DISALLOWED_PLACEHOLDERS),
                              sample_values=tpl.SAMPLE_VALUES, rule=TEMPLATE_RULE)


@router.post("/templates/preview", response_model=PreviewOut)
def preview(
    payload: PreviewIn,
    principal: Principal = Depends(require_permission("comms.read")),
) -> PreviewOut:
    body = tpl.render(payload.body, tpl.SAMPLE_VALUES)
    errors = tpl.validate_template(payload.channel, payload.body, payload.subject)
    # GSM-7 160 / UCS-2 70 per segment (Devanagari needs UCS-2)
    per = 160 if all(ord(c) < 128 for c in body) else 70
    return PreviewOut(body=body, subject=tpl.render(payload.subject, tpl.SAMPLE_VALUES),
                      errors=errors, characters=len(body),
                      sms_segments=max(1, math.ceil(len(body) / per)) if body else 0,
                      sample_values=tpl.SAMPLE_VALUES)


# --------------------------------------------------------------------- templates
@router.get("/templates", response_model=list[TemplateOut])
def list_templates(
    channel: str | None = None,
    purpose: str | None = None,
    language: str | None = None,
    include_inactive: bool = False,
    principal: Principal = Depends(require_permission("comms.read")),
    db: Session = Depends(get_db, scope="function"),
) -> list[TemplateOut]:
    engine.ensure_tenant(db, principal.organization_id, principal.user_id)
    stmt = select(CommsTemplate).where(CommsTemplate.organization_id == principal.organization_id)
    if channel:
        stmt = stmt.where(CommsTemplate.channel == channel)
    if purpose:
        stmt = stmt.where(CommsTemplate.purpose == purpose)
    if language:
        stmt = stmt.where(CommsTemplate.language == language)
    if not include_inactive:
        stmt = stmt.where(CommsTemplate.is_active.is_(True))
    rows = db.scalars(stmt.order_by(CommsTemplate.channel, CommsTemplate.purpose,
                                    CommsTemplate.language, CommsTemplate.created_at)).all()
    return [_tpl_out(t) for t in rows]


def _deactivate_peers(db: Session, t: CommsTemplate) -> None:
    for other in db.scalars(select(CommsTemplate).where(
            CommsTemplate.organization_id == t.organization_id,
            CommsTemplate.channel == t.channel, CommsTemplate.purpose == t.purpose,
            CommsTemplate.language == t.language, CommsTemplate.is_active.is_(True),
            CommsTemplate.id != t.id)).all():
        other.is_active = False
    db.flush()


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> TemplateOut:
    ctx = engine.load_ctx(db, principal.organization_id, principal.user_id)
    _require_channel(ctx, payload.channel)
    _check_template(payload.channel, payload.body, payload.subject)
    t = CommsTemplate(organization_id=principal.organization_id,
                      created_by=principal.user_id, updated_by=principal.user_id,
                      **payload.model_dump(exclude={"is_active"}), is_active=False)
    db.add(t)
    db.flush()
    if payload.is_active:
        # the new template replaces the active one for this channel/purpose/language
        _deactivate_peers(db, t)
        t.is_active = True
        db.flush()
    db.refresh(t)
    _audit(db, principal, request, "comms.template_created", "comms_template", str(t.id),
           {"channel": t.channel, "purpose": t.purpose, "language": t.language})
    return _tpl_out(t)


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdateIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> TemplateOut:
    t = db.get(CommsTemplate, template_id)
    if t is None or t.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Template not found")
    changes = payload.model_dump(exclude_unset=True)
    body = changes.get("body", t.body)
    subject = changes.get("subject", t.subject)
    _check_template(t.channel, body, subject)
    activate = changes.pop("is_active", None)
    for k, v in changes.items():
        setattr(t, k, v)
    if activate is True and not t.is_active:
        _deactivate_peers(db, t)
        t.is_active = True
    elif activate is False:
        t.is_active = False
    t.is_default = False if changes else t.is_default
    t.updated_by, t.updated_at = principal.user_id, engine.utcnow()
    db.flush()
    db.refresh(t)
    _audit(db, principal, request, "comms.template_updated", "comms_template", str(t.id),
           {"fields": sorted(changes) + (["is_active"] if activate is not None else [])})
    return _tpl_out(t)


# --------------------------------------------------------------------- settings / overview
@router.get("/settings", response_model=CommsSettingsOut)
def get_comms_settings(
    principal: Principal = Depends(require_permission("comms.read")),
    db: Session = Depends(get_db, scope="function"),
) -> CommsSettingsOut:
    return CommsSettingsOut.model_validate(
        engine.ensure_tenant(db, principal.organization_id, principal.user_id))


@router.put("/settings", response_model=CommsSettingsOut)
def put_comms_settings(
    payload: CommsSettingsIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.manage")),
    db: Session = Depends(get_db, scope="function"),
) -> CommsSettingsOut:
    s = engine.ensure_tenant(db, principal.organization_id, principal.user_id)
    for k, v in payload.model_dump().items():
        setattr(s, k, sorted(set(v)) if k == "reminder_channels" else v)
    s.updated_by, s.updated_at = principal.user_id, engine.utcnow()
    db.flush()
    db.refresh(s)
    _audit(db, principal, request, "comms.settings_updated", "comms_settings",
           str(principal.organization_id), payload.model_dump())
    return CommsSettingsOut.model_validate(s)


@router.get("/overview", response_model=CommsOverview)
def overview(
    principal: Principal = Depends(require_permission("comms.read")),
    db: Session = Depends(get_db, scope="function"),
) -> CommsOverview:
    org_id = principal.organization_id
    ctx = engine.load_ctx(db, org_id, principal.user_id)
    now = engine.utcnow()
    period = engine.period_of(now, ctx.tz)
    used = engine.usage(db, org_id, period)
    s = get_settings()
    providers = {"email": s.comms_email_provider, "sms": s.comms_sms_provider,
                 "whatsapp": s.comms_whatsapp_provider}
    channels = []
    for c in tpl.CHANNELS:
        mock = providers[c] == "mock"
        channels.append(ChannelUsage(
            channel=c, entitled=engine.channel_entitled(ctx.ent, c), provider=providers[c],
            mock=mock, live=(not mock) and s.comms_live_enabled, used=used[c]["used"],
            limit=engine.channel_limit(ctx.ent, c), cost_paise=used[c]["cost_paise"],
            cost_per_message_paise=ctx.costs.for_channel(c)))
    active = db.scalar(select(func.count()).select_from(Patient).where(
        Patient.organization_id == org_id, Patient.status == "active")) or 0
    counts: dict[tuple[str, str], int] = {
        (c, st): n for c, st, n in db.execute(
            select(CommsConsent.channel, CommsConsent.status, func.count())
            .where(CommsConsent.organization_id == org_id)
            .group_by(CommsConsent.channel, CommsConsent.status)).all()}
    consent = []
    for c in tpl.CHANNELS:
        oi, oo = counts.get((c, "opted_in"), 0), counts.get((c, "opted_out"), 0)
        consent.append(ConsentStats(channel=c, opted_in=oi, opted_out=oo,
                                    unknown=max(0, active - oi - oo)))
    return CommsOverview(
        period=period, live_enabled=s.comms_live_enabled, mock_notice=mock_notice(),
        channels=channels, spend_paise=sum(v["cost_paise"] for v in used.values()),
        spend_cap_paise=ctx.settings.monthly_spend_cap_paise, consent=consent,
        active_patients=active, settings=CommsSettingsOut.model_validate(ctx.settings),
        in_quiet_hours=engine.in_quiet_hours(now.astimezone(ctx.tz),
                                             ctx.settings.quiet_start_hour,
                                             ctx.settings.quiet_end_hour))


# --------------------------------------------------------------------- delivery log
@router.get("/delivery-log", response_model=DeliveryPage)
def delivery_log(
    channel: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    purpose: str | None = None,
    patient_id: uuid.UUID | None = None,
    appointment_id: uuid.UUID | None = None,
    follow_up_id: uuid.UUID | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("comms.read")),
    db: Session = Depends(get_db, scope="function"),
) -> DeliveryPage:
    conds = [CommsDelivery.organization_id == principal.organization_id]
    for col, val in ((CommsDelivery.channel, channel), (CommsDelivery.status, status_filter),
                     (CommsDelivery.purpose, purpose), (CommsDelivery.patient_id, patient_id),
                     (CommsDelivery.appointment_id, appointment_id),
                     (CommsDelivery.follow_up_id, follow_up_id)):
        if val is not None and val != "":
            conds.append(col == val)
    if from_date:
        conds.append(CommsDelivery.created_at >= from_date)
    if to_date:
        conds.append(CommsDelivery.created_at < to_date)
    total = db.scalar(select(func.count()).select_from(CommsDelivery).where(*conds)) or 0
    rows = db.scalars(select(CommsDelivery).where(*conds)
                      .order_by(CommsDelivery.id.desc()).limit(limit).offset(offset)).all()
    return DeliveryPage(items=[DeliveryOut.model_validate(r) for r in rows], total=total,
                        limit=limit, offset=offset)


# --------------------------------------------------------------------- reminders
@router.post("/reminders/run", response_model=ReminderRunOut)
def run_reminders(
    payload: ReminderRunIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.send")),
    db: Session = Depends(get_db, scope="function"),
) -> ReminderRunOut:
    summary = engine.run_reminders(
        db, principal.organization_id, hours_ahead=payload.hours_ahead,
        include_follow_ups=payload.include_follow_ups, actor_user_id=principal.user_id,
        correlation_id=get_correlation_id(request))
    _audit(db, principal, request, "comms.reminders_run", "comms_reminders", None,
           {"appointments": summary["appointments"], "follow_ups": summary["follow_ups"],
            "by_status": summary["by_status"]})
    return ReminderRunOut(**summary, mock_notice=mock_notice())


# --------------------------------------------------------------------- patient consent
def _load_patient(db: Session, principal: Principal, patient_id: uuid.UUID) -> Patient:
    p = db.scalar(select(Patient).where(Patient.id == patient_id,
                                        Patient.organization_id == principal.organization_id))
    if p is None or p.status == "merged":
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())


def _patient_comms(db: Session, principal: Principal, patient: Patient) -> PatientCommsOut:
    org_id = principal.organization_id
    pref = db.get(CommsPatientPreference, (org_id, patient.id))
    rows = {c.channel: c for c in db.scalars(select(CommsConsent).where(
        CommsConsent.organization_id == org_id, CommsConsent.patient_id == patient.id)).all()}
    history = db.scalars(select(CommsConsentEvent).where(
        CommsConsentEvent.organization_id == org_id,
        CommsConsentEvent.patient_id == patient.id)
        .order_by(CommsConsentEvent.id.desc()).limit(20)).all()
    names = _names(db, {r.actor_user_id for r in rows.values()} |
                   {h.actor_user_id for h in history})
    return PatientCommsOut(
        patient_id=patient.id,
        preferred_language=pref.preferred_language if pref else None,
        email=pref.email if pref else None,
        phone_masked=engine.mask_recipient("sms", patient.phone),
        consents=[ConsentOut(channel=c, status=rows[c].status if c in rows else None,
                             source=rows[c].source if c in rows else None,
                             recorded_at=rows[c].recorded_at if c in rows else None,
                             actor_name=names.get(rows[c].actor_user_id) if c in rows else None)
                  for c in tpl.CHANNELS],
        history=[ConsentEventOut(channel=h.channel, status=h.status, source=h.source,
                                 recorded_at=h.recorded_at,
                                 actor_name=names.get(h.actor_user_id)) for h in history],
    )


@router.get("/patients/{patient_id}", response_model=PatientCommsOut)
def patient_comms(
    patient_id: uuid.UUID,
    principal: Principal = Depends(require_permission("patient.read")),
    db: Session = Depends(get_db, scope="function"),
) -> PatientCommsOut:
    return _patient_comms(db, principal, _load_patient(db, principal, patient_id))


@router.put("/patients/{patient_id}/consent", response_model=PatientCommsOut)
def put_consent(
    patient_id: uuid.UUID,
    payload: ConsentIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.consent")),
    db: Session = Depends(get_db, scope="function"),
) -> PatientCommsOut:
    patient = _load_patient(db, principal, patient_id)
    try:
        engine.set_consent(db, principal.organization_id, patient.id, payload.channel,
                           payload.status, payload.source, principal.user_id)
    except engine.ConsentError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(db, principal, request, f"comms.consent_{payload.status}", "patient",
           str(patient.id), {"channel": payload.channel, "source": payload.source})
    return _patient_comms(db, principal, patient)


@router.post("/patients/{patient_id}/opt-out", response_model=PatientCommsOut)
def opt_out(
    patient_id: uuid.UUID,
    payload: OptOutIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.consent")),
    db: Session = Depends(get_db, scope="function"),
) -> PatientCommsOut:
    patient = _load_patient(db, principal, patient_id)
    channels = sorted(set(payload.channels or tpl.CHANNELS))
    for c in channels:
        engine.set_consent(db, principal.organization_id, patient.id, c, "opted_out",
                           payload.source, principal.user_id)
    _audit(db, principal, request, "comms.consent_opted_out", "patient", str(patient.id),
           {"channels": channels, "source": payload.source})
    return _patient_comms(db, principal, patient)


@router.put("/patients/{patient_id}/preferences", response_model=PatientCommsOut)
def put_preferences(
    patient_id: uuid.UUID,
    payload: PreferencesIn,
    request: Request,
    principal: Principal = Depends(require_permission("comms.consent")),
    db: Session = Depends(get_db, scope="function"),
) -> PatientCommsOut:
    patient = _load_patient(db, principal, patient_id)
    pref = db.get(CommsPatientPreference, (principal.organization_id, patient.id))
    if pref is None:
        pref = CommsPatientPreference(organization_id=principal.organization_id,
                                      patient_id=patient.id)
        db.add(pref)
    pref.preferred_language = payload.preferred_language
    pref.email = str(payload.email).lower() if payload.email else None
    pref.updated_by, pref.updated_at = principal.user_id, engine.utcnow()
    db.flush()
    _audit(db, principal, request, "comms.preferences_updated", "patient", str(patient.id),
           {"preferred_language": payload.preferred_language,
            "email_set": payload.email is not None})
    return _patient_comms(db, principal, patient)
