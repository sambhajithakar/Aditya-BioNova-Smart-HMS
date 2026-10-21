"""Provider-agnostic outbound communications (e-mail, SMS, WhatsApp).

Callers use :func:`send` with a :class:`Message`; the configured provider per
channel decides delivery. The default ``mock`` provider records messages in
``comms_messages`` (readable through the development-only ``/dev/outbox``)
and contacts nobody. Live adapters (Brevo e-mail, DLT-registered SMS over
HTTP, Meta WhatsApp Cloud API) only transmit when ``COMMS_LIVE_ENABLED`` is
true AND their credentials are configured — until then they are suppressed
and recorded, so no paid API is ever called by accident.
"""
from .base import Message, SendResult, send

__all__ = ["Message", "SendResult", "send"]
