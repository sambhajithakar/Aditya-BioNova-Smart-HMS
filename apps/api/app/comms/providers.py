"""Concrete providers.

Live adapters build the vendor's documented HTTP request and hand it to an
injectable transport (``http_post``) so request construction is unit-tested
without network access. They are never reached unless live delivery is
explicitly enabled (see ``comms.base.send``).
"""
from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable

from ..config import Settings
from .base import Message, SendResult

HttpPost = Callable[[str, dict[str, str], bytes], tuple[int, bytes]]


def _urllib_post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https URLs
        return resp.status, resp.read()


class MockProvider:
    """Records the message only (development, tests, demos)."""

    name = "mock"

    def configured(self, settings: Settings) -> bool:
        return True

    def send(self, message: Message, settings: Settings) -> SendResult:
        return SendResult(provider=self.name, status="recorded")


class BrevoEmailProvider:
    """Brevo transactional e-mail API (``POST /v3/smtp/email``)."""

    name = "brevo"
    url = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, http_post: HttpPost = _urllib_post) -> None:
        self.http_post = http_post

    def configured(self, settings: Settings) -> bool:
        return bool(settings.brevo_api_key)

    def build(self, message: Message, settings: Settings) -> tuple[dict[str, str], bytes]:
        headers = {
            "api-key": settings.brevo_api_key or "",
            "content-type": "application/json",
            "accept": "application/json",
        }
        payload = {
            "sender": {"email": settings.comms_email_from},
            "to": [{"email": message.to}],
            "subject": message.subject,
            "textContent": message.body,
        }
        return headers, json.dumps(payload).encode()

    def send(self, message: Message, settings: Settings) -> SendResult:
        headers, body = self.build(message, settings)
        status, raw = self.http_post(self.url, headers, body)
        if 200 <= status < 300:
            msg_id = json.loads(raw or b"{}").get("messageId")
            return SendResult(provider=self.name, status="sent", provider_message_id=msg_id)
        return SendResult(provider=self.name, status="failed", error=f"HTTP {status}")


class DltSmsProvider:
    """Generic HTTP adapter for Indian DLT-compliant SMS gateways.

    TRAI DLT rules require a registered principal entity id, sender header and
    a pre-approved template id per message; the gateway endpoint/field names
    are vendor-specific, so this adapter posts a neutral JSON body that the
    chosen vendor's mapping is expected to accept (to be finalised once a
    vendor is approved).
    """

    name = "dlt_http"

    def __init__(self, http_post: HttpPost = _urllib_post) -> None:
        self.http_post = http_post

    def configured(self, settings: Settings) -> bool:
        return all((settings.sms_dlt_endpoint, settings.sms_dlt_api_key,
                    settings.sms_dlt_sender_id, settings.sms_dlt_entity_id))

    def build(self, message: Message, settings: Settings) -> tuple[dict[str, str], bytes]:
        if not message.template:
            raise ValueError("DLT SMS requires an approved template id")
        headers = {
            "authorization": f"Bearer {settings.sms_dlt_api_key}",
            "content-type": "application/json",
        }
        payload = {
            "to": message.to,
            "sender_id": settings.sms_dlt_sender_id,
            "entity_id": settings.sms_dlt_entity_id,
            "template_id": message.template,
            "variables": message.variables,
            "text": message.body,
        }
        return headers, json.dumps(payload).encode()

    def send(self, message: Message, settings: Settings) -> SendResult:
        headers, body = self.build(message, settings)
        status, _raw = self.http_post(settings.sms_dlt_endpoint or "", headers, body)
        ok = 200 <= status < 300
        return SendResult(provider=self.name, status="sent" if ok else "failed",
                          error=None if ok else f"HTTP {status}")


class MetaWhatsAppProvider:
    """Meta WhatsApp Cloud API — business-initiated messages use templates."""

    name = "meta_cloud"

    def __init__(self, http_post: HttpPost = _urllib_post) -> None:
        self.http_post = http_post

    def configured(self, settings: Settings) -> bool:
        return bool(settings.whatsapp_phone_number_id and settings.whatsapp_access_token)

    def url(self, settings: Settings) -> str:
        return (f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
                f"{settings.whatsapp_phone_number_id}/messages")

    def build(self, message: Message, settings: Settings) -> tuple[dict[str, str], bytes]:
        if not message.template:
            raise ValueError("WhatsApp business-initiated messages need a template")
        headers = {
            "authorization": f"Bearer {settings.whatsapp_access_token}",
            "content-type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": message.to,
            "type": "template",
            "template": {
                "name": message.template,
                "language": {"code": "en"},
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": v} for v in message.variables],
                }],
            },
        }
        return headers, json.dumps(payload).encode()

    def send(self, message: Message, settings: Settings) -> SendResult:
        headers, body = self.build(message, settings)
        status, raw = self.http_post(self.url(settings), headers, body)
        if 200 <= status < 300:
            ids = json.loads(raw or b"{}").get("messages") or [{}]
            return SendResult(provider=self.name, status="sent",
                              provider_message_id=ids[0].get("id"))
        return SendResult(provider=self.name, status="failed", error=f"HTTP {status}")
