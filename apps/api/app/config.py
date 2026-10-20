"""Environment-based application configuration.

All secrets come from the environment (or a local git-ignored .env).
No secret is ever hard-coded for production use: outside development/test
the application refuses to start with a missing, short or well-known secret.
"""
from __future__ import annotations

import ipaddress
from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that must never protect a non-development deployment.
_KNOWN_INSECURE_SECRETS = {
    "insecure-dev-only-secret-change-me",
    "replace_me_with_a_long_random_secret",
    "change_me",
    "changeme",
    "secret",
}
_DEV_ENVIRONMENTS = {"development", "test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Aditya BioNova Smart HMS API"
    environment: str = "development"

    # Runtime data access: the NON-OWNER application role. PostgreSQL row-level
    # security is enforced for this role (the table owner would bypass RLS).
    database_url: str = "postgresql+psycopg2://hms_app:change_me@127.0.0.1:5433/hms_dev"
    # DDL / migrations only: the table-owner role. Never used to serve requests.
    migration_database_url: str = "postgresql+psycopg2://hms:change_me@127.0.0.1:5433/hms_dev"

    jwt_secret: str = "insecure-dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "aditya-bionova-hms"
    # Accept both the field names and the JWT_*_TTL_SECONDS names documented
    # in .env.example (previously silently ignored).
    access_token_ttl_seconds: int = Field(
        default=1800, ge=60,
        validation_alias=AliasChoices("ACCESS_TOKEN_TTL_SECONDS", "JWT_ACCESS_TTL_SECONDS"),
    )
    # Idle lifetime of a refresh token (renewed on every rotation) ...
    refresh_token_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 14, ge=300,
        validation_alias=AliasChoices("REFRESH_TOKEN_TTL_SECONDS", "JWT_REFRESH_TTL_SECONDS"),
    )
    # ... capped by an absolute lifetime of the whole rotation family.
    session_absolute_ttl_seconds: int = Field(default=60 * 60 * 24 * 30, ge=3600)

    # Key for encrypting secrets at rest (TOTP seeds): urlsafe-base64, 32 bytes.
    # Required outside development/test; derived from JWT_SECRET otherwise.
    field_encryption_key: str | None = None

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Reverse proxies whose X-Forwarded-For header is trusted (IPs or CIDRs).
    trusted_proxies: list[str] = ["127.0.0.1/32", "::1/128"]

    # Public URL of the web portal, used in e-mailed links (reset, invitations).
    web_base_url: str = "http://localhost:3000"

    # --- Abuse protection (fixed-window counters stored in PostgreSQL so
    # they hold across API instances). Window lengths are in seconds.
    rate_limit_enabled: bool = True
    rl_login_per_ip: int = 30            # per minute
    rl_login_failures_per_account: int = 5  # per 15 minutes -> lockout
    rl_register_per_ip: int = 10         # per hour
    rl_refresh_per_ip: int = 120         # per minute
    rl_mfa_attempts: int = 5             # per challenge / per user per 15 min
    rl_password_reset_per_account: int = 3  # per hour
    rl_password_reset_per_ip: int = 20   # per hour
    rl_invite_accept_per_ip: int = 20    # per hour

    # --- Communications: provider-agnostic; "mock" stores messages locally
    # (dev outbox) and never contacts a third party.
    comms_email_provider: str = "mock"      # mock | brevo
    comms_sms_provider: str = "mock"        # mock | dlt_http
    comms_whatsapp_provider: str = "mock"   # mock | meta_cloud
    # Live providers stay disabled until credentials & pricing are approved.
    comms_live_enabled: bool = False
    comms_email_from: str = "no-reply@example.invalid"
    brevo_api_key: str | None = None
    sms_dlt_endpoint: str | None = None
    sms_dlt_api_key: str | None = None
    sms_dlt_sender_id: str | None = None
    sms_dlt_entity_id: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_api_version: str = "v21.0"

    @field_validator("jwt_secret")
    @classmethod
    def _min_secret_length(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("JWT_SECRET must be at least 16 characters")
        return v

    @field_validator("trusted_proxies")
    @classmethod
    def _valid_networks(cls, v: list[str]) -> list[str]:
        for net in v:
            ipaddress.ip_network(net, strict=False)
        return v

    @model_validator(mode="after")
    def _production_secrets(self) -> "Settings":
        if self.environment in _DEV_ENVIRONMENTS:
            return self
        if self.jwt_secret in _KNOWN_INSECURE_SECRETS or len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET must be a unique random value of at least 32 characters "
                f"when ENVIRONMENT={self.environment!r}"
            )
        if not self.field_encryption_key:
            raise ValueError(
                f"FIELD_ENCRYPTION_KEY is required when ENVIRONMENT={self.environment!r}"
            )
        return self

    @property
    def is_dev(self) -> bool:
        return self.environment in _DEV_ENVIRONMENTS


@lru_cache
def get_settings() -> Settings:
    return Settings()
