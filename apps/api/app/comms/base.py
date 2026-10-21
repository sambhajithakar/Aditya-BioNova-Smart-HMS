"""Message model, provider registry and dispatch."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol

from sqlalchemy import text

from ..config import Settings, get_settings

logger = logging.getLogger("hms.comms")

Channel = Literal["email", "sms", "whatsapp"]


@dataclass
class Message:
    channel: Channel
    to: str
    body: str
    subject: str = ""
    # Pre-approved template id (DLT for SMS, Meta template for WhatsApp) and
    # its ordered variables; e-mail ignores these.
    template: str | None = None
    variables: list[str] = field(default_factory=list)
    # Marks bodies carrying single-use secrets (reset/invite links) so they
    # are never persisted outside development/test.
    sensitive: bool = False


@dataclass
class SendResult:
    provider: str
    status: Literal["sent", "recorded", "suppressed", "failed"]
    provider_message_id: str | None = None
    error: str | None = None


class Provider(Protocol):
    name: str

    def configured(self, settings: Settings) -> bool: ...

    def send(self, message: Message, settings: Settings) -> SendResult: ...


_INSERT = text(
    """
    INSERT INTO comms_messages (channel, provider, recipient, subject, body, status, error)
    VALUES (:channel, :provider, :recipient, :subject, :body, :status, :error)
    """
)


def _record(message: Message, result: SendResult, settings: Settings) -> None:
    """Persist an outbox row in its own transaction (never blocks the caller)."""
    from ..db import SessionLocal

    body = message.body
    if message.sensitive and not settings.is_dev:
        body = "[redacted: contains a single-use link]"
    db = SessionLocal()
    try:
        db.execute(
            _INSERT,
            {
                "channel": message.channel,
                "provider": result.provider,
                "recipient": message.to[:320],
                "subject": message.subject[:300],
                "body": body[:4000],
                "status": result.status,
                "error": (result.error or "")[:500] or None,
            },
        )
        db.commit()
    except Exception:  # pragma: no cover - outbox must never break a request
        db.rollback()
        logger.exception("could not record outbound %s message", message.channel)
    finally:
        db.close()


def _provider_for(channel: Channel, settings: Settings) -> Provider:
    from . import providers

    name = {
        "email": settings.comms_email_provider,
        "sms": settings.comms_sms_provider,
        "whatsapp": settings.comms_whatsapp_provider,
    }[channel]
    registry: dict[str, Provider] = {
        "mock": providers.MockProvider(),
        "brevo": providers.BrevoEmailProvider(),
        "dlt_http": providers.DltSmsProvider(),
        "meta_cloud": providers.MetaWhatsAppProvider(),
    }
    if name not in registry:
        raise ValueError(f"unknown {channel} provider {name!r}")
    return registry[name]


def send(message: Message, settings: Settings | None = None) -> SendResult:
    settings = settings or get_settings()
    provider = _provider_for(message.channel, settings)
    if provider.name != "mock" and not (
        settings.comms_live_enabled and provider.configured(settings)
    ):
        result = SendResult(provider=provider.name, status="suppressed",
                            error="live delivery disabled or provider not configured")
    else:
        try:
            result = provider.send(message, settings)
        except Exception as exc:  # network/provider failure: record, don't raise
            logger.warning("%s delivery via %s failed: %s",
                           message.channel, provider.name, type(exc).__name__)
            result = SendResult(provider=provider.name, status="failed",
                                error=type(exc).__name__)
    _record(message, result, settings)
    return result
