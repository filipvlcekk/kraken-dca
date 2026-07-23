"""Password session and CSRF helpers for the web UI."""

from __future__ import annotations

import os
import secrets
from hmac import compare_digest
from typing import Any, Mapping

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from krakendca.web.schemas import ApiException

COOKIE_NAME = "kraken_dca_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
SESSION_SALT = "kraken-dca-web-session"


def require_web_password(env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    password = values.get("WEB_UI_PASSWORD")
    if not password:
        raise RuntimeError("WEB_UI_PASSWORD is required for web mode.")
    return password


def session_secret(password: str, env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    return values.get("WEB_UI_SESSION_SECRET") or password


def cookie_secure(env: Mapping[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return values.get("WEB_UI_COOKIE_SECURE", "").lower() == "true"


def serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret, salt=SESSION_SALT)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_password(submitted: str, expected: str) -> bool:
    return compare_digest(submitted, expected)


def encode_session(
    signer: URLSafeTimedSerializer,
    csrf_token: str,
) -> str:
    return signer.dumps({"authenticated": True, "csrf_token": csrf_token})


def decode_session(request: Request) -> dict[str, Any] | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None

    signer: URLSafeTimedSerializer = request.app.state.session_serializer
    try:
        payload = signer.loads(cookie, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None

    if not payload.get("authenticated") or not payload.get("csrf_token"):
        return None
    return payload


def require_authenticated_session(request: Request) -> dict[str, Any]:
    session = decode_session(request)
    if session is None:
        raise ApiException(
            401,
            "unauthenticated",
            "Authentication is required.",
        )
    return session


def require_csrf(request: Request) -> dict[str, Any]:
    session = require_authenticated_session(request)
    submitted = request.headers.get("X-CSRF-Token") or ""
    expected = str(session.get("csrf_token") or "")
    if not submitted or not compare_digest(submitted, expected):
        raise ApiException(
            403,
            "csrf_invalid",
            "Missing or invalid CSRF token.",
        )
    return session
