"""Password hashing and token primitives.

Passwords: scrypt (stdlib) with a per-password random salt, parameters from
the OWASP Password Storage Cheat Sheet (N=2^15, r=8, p=3 -> 32 MiB).
Format: ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>``; hashes made with older
parameters are upgraded transparently at the next successful login.
Access tokens: short-lived HS256 JWTs carrying the session id (``sid``) so
that revoking the server-side session invalidates them immediately.
Refresh tokens: opaque random strings; only SHA-256 hashes are persisted.
MFA: RFC 6238 TOTP (SHA-1, 30 s, 6 digits); seeds are AES-256-GCM encrypted
at rest with ``FIELD_ENCRYPTION_KEY``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from typing import Any
from urllib.parse import quote

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_settings

# --- scrypt password hashing ---------------------------------------------
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 3
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16
# scrypt needs memory > 128 * N * r; give it headroom (128*32768*8 = 32 MiB)
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=_SCRYPT_MAXMEM,
        )
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def password_needs_rehash(stored: str) -> bool:
    """True when ``stored`` was made with weaker-than-current parameters."""
    try:
        scheme, n, r, p, _salt, _hash = stored.split("$")
    except ValueError:
        return True
    return scheme != "scrypt" or (int(n), int(r), int(p)) != (
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P
    )


# A dummy hash used when a login email does not exist, so that response
# timing does not reveal whether the account is registered.
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalisation-000")


# --- Access tokens (JWT) ---------------------------------------------------
def create_access_token(*, user_id: str, session_id: str, org_id: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "sid": session_id,
        "org": org_id,
        "iss": settings.jwt_issuer,
        "iat": now,
        "nbf": now,
        "exp": now + settings.access_token_ttl_seconds,
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "sid", "org", "typ"]},
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


# --- Refresh tokens (opaque) ----------------------------------------------
def new_refresh_token() -> tuple[str, str]:
    """Return (plaintext_token, sha256_hex_hash). Plaintext is shown once."""
    token = secrets.token_urlsafe(48)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_token(token: str) -> str:
    """SHA-256 for single-use secrets (reset/invitation tokens, recovery codes)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- MFA challenge tokens ---------------------------------------------------
MFA_CHALLENGE_TTL_SECONDS = 300


def create_mfa_challenge_token(*, user_id: str, org_id: str) -> tuple[str, str]:
    """Short-lived token proving the password step passed. Returns (token, jti)."""
    settings = get_settings()
    now = int(time.time())
    jti = uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "org": org_id,
        "jti": jti,
        "iss": settings.jwt_issuer,
        "iat": now,
        "nbf": now,
        "exp": now + MFA_CHALLENGE_TTL_SECONDS,
        "typ": "mfa",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), jti


def decode_mfa_challenge_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "org", "jti", "typ"]},
    )
    if payload.get("typ") != "mfa":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


# --- TOTP (RFC 6238) ----------------------------------------------------------
TOTP_PERIOD = 30
TOTP_DIGITS = 6


def new_totp_secret() -> str:
    """160-bit random seed, base32 without padding (authenticator-app format)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (
        10 ** TOTP_DIGITS
    )
    return str(code).zfill(TOTP_DIGITS)


def totp_now(secret_b32: str, at: float | None = None) -> str:
    return _hotp(secret_b32, int((at if at is not None else time.time()) // TOTP_PERIOD))


def verify_totp(
    secret_b32: str, code: str, *, last_step: int | None, at: float | None = None
) -> int | None:
    """Return the matched time step (±1 step drift) or None.

    A step at or before ``last_step`` is refused so a code cannot be replayed.
    """
    if not (code.isdigit() and len(code) == TOTP_DIGITS):
        return None
    current = int((at if at is not None else time.time()) // TOTP_PERIOD)
    for step in (current - 1, current, current + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(_hotp(secret_b32, step), code):
            return step
    return None


def totp_uri(secret_b32: str, *, account: str, issuer: str = "Aditya BioNova HMS") -> str:
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"
    )


def new_recovery_codes(count: int = 10) -> list[str]:
    """Human-typable single-use codes, format ``xxxx-xxxx`` (lowercase hex)."""
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(count)]


# --- Field encryption (AES-256-GCM) ------------------------------------------
_ENC_PREFIX = "v1:"


def _field_key() -> bytes:
    settings = get_settings()
    if settings.field_encryption_key:
        key = base64.urlsafe_b64decode(settings.field_encryption_key + "==")
        if len(key) != 32:
            raise ValueError("FIELD_ENCRYPTION_KEY must decode to 32 bytes")
        return key
    # development/test only (production refuses to start without the key)
    return hashlib.sha256(b"hms-field-key:" + settings.jwt_secret.encode()).digest()


def encrypt_field(plaintext: str, *, context: str) -> str:
    """Encrypt with a fresh 96-bit nonce; ``context`` is bound as AAD."""
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_field_key()).encrypt(nonce, plaintext.encode(), context.encode())
    return _ENC_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode()


def decrypt_field(token: str, *, context: str) -> str:
    if not token.startswith(_ENC_PREFIX):
        raise ValueError("unknown field encryption format")
    raw = base64.urlsafe_b64decode(token[len(_ENC_PREFIX):])
    return AESGCM(_field_key()).decrypt(raw[:12], raw[12:], context.encode()).decode()
