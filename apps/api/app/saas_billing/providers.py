"""Payment providers for SaaS subscription billing.

* ``RazorpayProvider`` — Razorpay **test mode** only (key ids ``rzp_test_*``;
  live keys are refused by config validation). Orders API, checkout
  signature ``HMAC_SHA256(order_id|payment_id, key_secret)``, webhook
  signature ``HMAC_SHA256(raw_body, webhook_secret)``, refunds API.
* ``SimulatorProvider`` — an in-process stand-in used for local demos and
  tests: it mints ``order_SIM…`` / ``pay_SIM…`` ids and signs with a key
  derived from JWT_SECRET, so the SAME signature-verification code path is
  exercised. It moves no money and is refused outside development/test.

Neither provider ever decides an amount: the server computes it from the
plan catalogue and the provider only echoes it back.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol

from ..config import Settings

HttpCall = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


def _urllib_call(method: str, url: str, headers: dict[str, str],
                 body: bytes | None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed https base
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signature_ok(secret: str | None, message: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    return hmac.compare_digest(hmac_hex(secret, message), signature.strip())


class ProviderError(RuntimeError):
    """``definitive`` is True when the provider answered and refused (HTTP 4xx).
    Otherwise (network error, timeout, 5xx) the outcome is unknown: the
    request may have been carried out, so a money movement must be checked
    with the provider before it is retried."""

    def __init__(self, message: str, *, definitive: bool = False) -> None:
        super().__init__(message)
        self.definitive = definitive


@dataclass
class ProviderRefund:
    provider_refund_id: str
    status: str  # provider status, e.g. "processed" | "pending" | "failed"


@dataclass
class CreatedOrder:
    provider_order_id: str
    checkout: dict  # parameters the browser needs for the hosted checkout


class PaymentProvider(Protocol):
    name: str
    mode: str  # "sandbox" | "simulator"

    def create_order(self, *, amount_paise: int, currency: str, receipt: str,
                     notes: dict[str, str]) -> CreatedOrder: ...

    def checkout_signature_ok(self, order_id: str, payment_id: str, signature: str) -> bool: ...

    def webhook_signature_ok(self, raw_body: bytes, signature: str | None) -> bool: ...

    def refund(self, provider_payment_id: str, amount_paise: int, notes: dict[str, str]
               ) -> str: ...

    def find_refund(self, provider_payment_id: str, reference: str) -> ProviderRefund | None:
        """The refund of this payment whose ``notes.refund`` is ``reference``."""
        ...

    def fetch_order_status(self, provider_order_id: str) -> str | None: ...


class RazorpayProvider:
    name = "razorpay"
    mode = "sandbox"

    def __init__(self, settings: Settings, http: HttpCall = _urllib_call) -> None:
        if not (settings.razorpay_key_id and settings.razorpay_key_secret):
            raise ProviderError("Razorpay test keys are not configured")
        if not settings.razorpay_key_id.startswith("rzp_test_"):
            raise ProviderError("Only Razorpay test keys are allowed")
        self.key_id = settings.razorpay_key_id
        self._secret = settings.razorpay_key_secret
        self._webhook_secret = settings.razorpay_webhook_secret
        self._base = settings.razorpay_api_base.rstrip("/")
        self._http = http

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.key_id}:{self._secret}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        try:
            status, raw = self._http(method, f"{self._base}{path}", self._headers(), body)
        except OSError as exc:
            raise ProviderError(f"Razorpay unreachable: {type(exc).__name__}") from exc
        if status >= 300:
            raise ProviderError(f"Razorpay HTTP {status}", definitive=400 <= status < 500)
        return json.loads(raw or b"{}")

    def create_order(self, *, amount_paise: int, currency: str, receipt: str,
                     notes: dict[str, str]) -> CreatedOrder:
        data = self._call("POST", "/orders", {"amount": amount_paise, "currency": currency,
                                              "receipt": receipt[:40], "notes": notes})
        if data.get("amount") != amount_paise or not str(data.get("id", "")).startswith("order_"):
            raise ProviderError("Razorpay returned an unexpected order")
        return CreatedOrder(data["id"], {"key_id": self.key_id, "order_id": data["id"],
                                         "amount": amount_paise, "currency": currency})

    def checkout_signature_ok(self, order_id: str, payment_id: str, signature: str) -> bool:
        return signature_ok(self._secret, f"{order_id}|{payment_id}".encode(), signature)

    def webhook_signature_ok(self, raw_body: bytes, signature: str | None) -> bool:
        return signature_ok(self._webhook_secret, raw_body, signature)

    def refund(self, provider_payment_id: str, amount_paise: int,
               notes: dict[str, str]) -> str:
        data = self._call("POST", f"/payments/{provider_payment_id}/refund",
                          {"amount": amount_paise, "notes": notes,
                           "receipt": notes.get("refund", "")[:40]})
        if not str(data.get("id", "")).startswith("rfnd_"):
            raise ProviderError("Razorpay returned an unexpected refund")
        return data["id"]

    def find_refund(self, provider_payment_id: str, reference: str) -> ProviderRefund | None:
        data = self._call("GET", f"/payments/{provider_payment_id}/refunds?count=100")
        for item in data.get("items") or []:
            if (item.get("notes") or {}).get("refund") == reference \
                    or item.get("receipt") == reference[:40]:
                return ProviderRefund(str(item.get("id")), str(item.get("status") or ""))
        return None

    def fetch_order_status(self, provider_order_id: str) -> str | None:
        return self._call("GET", f"/orders/{provider_order_id}").get("status")


class SimulatorProvider:
    """No network, no money. Signs exactly like Razorpay, with derived keys."""

    name = "simulator"
    mode = "simulator"

    def __init__(self, settings: Settings) -> None:
        if not settings.is_dev:
            raise ProviderError("The payment simulator is only available in development/test")
        base = settings.jwt_secret.encode()
        self._secret = hmac.new(base, b"saas-simulator-checkout", hashlib.sha256).hexdigest()
        self._webhook_secret = hmac.new(base, b"saas-simulator-webhook",
                                        hashlib.sha256).hexdigest()

    def create_order(self, *, amount_paise: int, currency: str, receipt: str,
                     notes: dict[str, str]) -> CreatedOrder:
        oid = "order_SIM" + secrets.token_hex(8)
        return CreatedOrder(oid, {"key_id": "simulator", "order_id": oid,
                                  "amount": amount_paise, "currency": currency})

    # the simulator's "hosted checkout" — used by the simulate endpoint/tests
    def sign_checkout(self, order_id: str, payment_id: str) -> str:
        return hmac_hex(self._secret, f"{order_id}|{payment_id}".encode())

    def sign_webhook(self, raw_body: bytes) -> str:
        return hmac_hex(self._webhook_secret, raw_body)

    def checkout_signature_ok(self, order_id: str, payment_id: str, signature: str) -> bool:
        return signature_ok(self._secret, f"{order_id}|{payment_id}".encode(), signature)

    def webhook_signature_ok(self, raw_body: bytes, signature: str | None) -> bool:
        return signature_ok(self._webhook_secret, raw_body, signature)

    def refund(self, provider_payment_id: str, amount_paise: int,
               notes: dict[str, str]) -> str:
        return "rfnd_SIM" + secrets.token_hex(8)

    def find_refund(self, provider_payment_id: str, reference: str) -> ProviderRefund | None:
        return None  # no remote state: an unresolved simulator refund is simply re-issued

    def fetch_order_status(self, provider_order_id: str) -> str | None:
        return None  # the simulator has no remote state; reconciliation uses local rows


_override: PaymentProvider | None = None


def set_provider_override(provider: PaymentProvider | None) -> None:
    """Tests inject a Razorpay provider with a fake HTTP transport."""
    global _override
    _override = provider


def get_provider(settings: Settings, name: str | None = None) -> PaymentProvider:
    if _override is not None and (name is None or name == _override.name):
        return _override
    chosen = name or settings.payments_provider
    if chosen == "razorpay":
        return RazorpayProvider(settings)
    if chosen == "simulator":
        return SimulatorProvider(settings)
    raise ProviderError(f"Unknown payments provider {chosen!r}")
