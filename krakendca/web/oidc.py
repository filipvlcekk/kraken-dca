"""OpenID Connect configuration helpers for web UI authentication."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


OIDC_SCOPES = ("openid", "email", "profile", "groups")


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


def _required_env(values: Mapping[str, str], key: str) -> str:
    value = (values.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"{key} is required for OIDC web mode.")
    return value
