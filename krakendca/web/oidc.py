"""OpenID Connect configuration helpers for web UI authentication."""

from __future__ import annotations

from dataclasses import dataclass
import os
import secrets
import time
from typing import Any
from typing import Mapping
from urllib.parse import urlencode

import httpx
from joserfc.errors import JoseError
from joserfc import jwt
from joserfc.jwk import KeySet
from joserfc.jwk import import_key
from joserfc.jwt import JWTClaimsRegistry
from itsdangerous import URLSafeTimedSerializer

OIDC_SCOPES = ("openid", "email", "profile", "groups")
OIDC_STATE_COOKIE_NAME = "kraken_dca_oidc_state"
OIDC_STATE_MAX_AGE_SECONDS = 10 * 60
OIDC_STATE_SALT = "kraken-dca-oidc-state"
OIDC_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_url: str
    allowed_group: str
    scopes: tuple[str, ...] = OIDC_SCOPES


@dataclass(frozen=True)
class OidcIdentity:
    subject: str
    email: str | None
    groups: list[str]
    token_value: str | None = None


class OidcAuthError(Exception):
    """Raised when the provider response cannot authenticate a user."""


EXPECTED_AUTH_EXCEPTIONS = (
    OidcAuthError,
    JoseError,
    httpx.HTTPError,
    ValueError,
    KeyError,
    TypeError,
)


class OidcClient:
    def __init__(self, config: OidcConfig) -> None:
        self._config = config

    async def authenticate(self, code: str, nonce: str) -> OidcIdentity:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                f"{self._config.issuer}/api/oidc/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._config.redirect_url,
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                },
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            id_token = str(token_payload.get("id_token") or "")
            if not id_token:
                raise OidcAuthError(
                    "Provider response did not include id_token."
                )

            jwks_response = await client.get(
                f"{self._config.issuer}/.well-known/jwks.json"
            )
            jwks_response.raise_for_status()
            return self._identity_from_id_token(
                id_token,
                jwks_response.json(),
                nonce,
            )

    def _identity_from_id_token(
        self,
        id_token: str,
        jwks: dict[str, Any],
        nonce: str,
    ) -> OidcIdentity:
        key_set = KeySet([import_key(key) for key in jwks.get("keys", [])])
        token = jwt.decode(id_token, key_set, algorithms=["RS256"])
        JWTClaimsRegistry(
            iss={"essential": True, "value": self._config.issuer},
            aud={"essential": True, "value": self._config.client_id},
            exp={"essential": True},
            sub={"essential": True},
        ).validate(token.claims)
        if token.claims.get("nonce") != nonce:
            raise OidcAuthError("OIDC nonce mismatch.")

        groups = token.claims.get("groups") or []
        if not isinstance(groups, list):
            groups = []
        return OidcIdentity(
            subject=str(token.claims["sub"]),
            email=_optional_string(token.claims.get("email")),
            groups=[str(group) for group in groups],
            token_value=id_token,
        )


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


def session_payload(identity: OidcIdentity) -> dict[str, object]:
    created_at = int(time.time())
    return {
        "auth_mode": "oidc",
        "sub": identity.subject,
        "email": identity.email,
        "groups": identity.groups,
        "created_at": created_at,
        "reauth_after": created_at + OIDC_SESSION_MAX_AGE_SECONDS,
    }


def session_refresh_payload(session: Mapping[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in (
        "auth_mode",
        "sub",
        "email",
        "groups",
        "created_at",
        "reauth_after",
    ):
        if key in session:
            payload[key] = session[key]
    return payload


def _required_env(values: Mapping[str, str], key: str) -> str:
    value = (values.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"{key} is required for OIDC web mode.")
    return value


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
