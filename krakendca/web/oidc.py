"""OpenID Connect configuration helpers for web UI authentication."""

from __future__ import annotations

from dataclasses import dataclass
import os
import secrets
from typing import Mapping
from urllib.parse import urlencode

from itsdangerous import URLSafeTimedSerializer

OIDC_SCOPES = ("openid", "email", "profile", "groups")
OIDC_STATE_COOKIE_NAME = "kraken_dca_oidc_state"
OIDC_STATE_MAX_AGE_SECONDS = 10 * 60
OIDC_STATE_SALT = "kraken-dca-oidc-state"


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_url: str
    allowed_group: str
    scopes: tuple[str, ...] = OIDC_SCOPES


def require_oidc_config(
    env: Mapping[str, str] | None = None,
) -> OidcConfig:
    values = os.environ if env is None else env
    issuer = _required_env(values, "WEB_UI_OIDC_ISSUER").rstrip("/")
    return OidcConfig(
        issuer=issuer,
        client_id=_required_env(values, "WEB_UI_OIDC_CLIENT_ID"),
        client_secret=_required_env(values, "WEB_UI_OIDC_CLIENT_SECRET"),
        redirect_url=_required_env(values, "WEB_UI_OIDC_REDIRECT_URL"),
        allowed_group=_required_env(values, "WEB_UI_OIDC_ALLOWED_GROUP"),
    )


def state_serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret, salt=OIDC_STATE_SALT)


def new_state() -> str:
    return secrets.token_urlsafe(32)


def authorization_url(config: OidcConfig, state: str, nonce: str) -> str:
    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_url,
        "scope": " ".join(config.scopes),
        "state": state,
        "nonce": nonce,
    }
    return f"{config.issuer}/authorize?{urlencode(params)}"


def _required_env(values: Mapping[str, str], key: str) -> str:
    value = (values.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"{key} is required for OIDC web mode.")
    return value
