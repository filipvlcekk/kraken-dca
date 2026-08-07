"""Password session and CSRF helpers for the web UI."""

from __future__ import annotations

import os
import secrets
import time
from hmac import compare_digest
from threading import Lock
from typing import Any, Literal, Mapping

from fastapi import Request
from fastapi.responses import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from krakendca.web.schemas import ApiException

COOKIE_NAME = "kraken_dca_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
SESSION_SALT = "kraken-dca-web-session"
SESSION_SECRET_MIN_LENGTH = 32
LOGIN_MAX_FAILURES = 5
LOGIN_GLOBAL_MAX_FAILURES = 50
LOGIN_WINDOW_SECONDS = 5 * 60
WEAK_SESSION_SECRETS = {
    "change-me",
    "changeme",
    "password",
    "secret",
}
WEAK_SESSION_SECRET_PREFIXES = ("change-me",)
AUTH_MODES = {"password", "oidc"}


class LoginThrottle:
    """In-memory failed-login throttle for the single-process web UI."""

    def __init__(
        self,
        max_failures: int = LOGIN_MAX_FAILURES,
        global_max_failures: int = LOGIN_GLOBAL_MAX_FAILURES,
        window_seconds: int = LOGIN_WINDOW_SECONDS,
    ) -> None:
        self._max_failures = max_failures
        self._global_max_failures = global_max_failures
        self._window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._global_failures: list[float] = []
        self._lock = Lock()

    def is_allowed(self, client_key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            return (
                len(self._failures.get(client_key, [])) < self._max_failures
                and len(self._global_failures) < self._global_max_failures
            )

    def record_failure(self, client_key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            self._failures.setdefault(client_key, []).append(now)
            self._global_failures.append(now)

    def record_success(self, client_key: str) -> None:
        with self._lock:
            self._failures.pop(client_key, None)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        self._global_failures = [
            failure for failure in self._global_failures if failure >= cutoff
        ]
        for client_key, failures in list(self._failures.items()):
            recent = [failure for failure in failures if failure >= cutoff]
            if recent:
                self._failures[client_key] = recent
            else:
                self._failures.pop(client_key, None)


def require_web_password(env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    password = values.get("WEB_UI_PASSWORD")
    if not password:
        raise RuntimeError("WEB_UI_PASSWORD is required for web mode.")
    return password


def require_auth_mode(
    env: Mapping[str, str] | None = None,
) -> Literal["password", "oidc"]:
    values = os.environ if env is None else env
    mode = (values.get("WEB_UI_AUTH_MODE") or "").strip().lower()
    if mode not in AUTH_MODES:
        raise RuntimeError(
            "WEB_UI_AUTH_MODE is required for web mode and must be "
            "'password' or 'oidc'.",
        )
    return mode  # type: ignore[return-value]


def session_secret(
    password: str | None,
    env: Mapping[str, str] | None = None,
) -> str:
    del password
    values = os.environ if env is None else env
    secret = (values.get("WEB_UI_SESSION_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("WEB_UI_SESSION_SECRET is required for web mode.")
    if (
        len(secret) < SESSION_SECRET_MIN_LENGTH
        or secret.lower() in WEAK_SESSION_SECRETS
        or secret.lower().startswith(WEAK_SESSION_SECRET_PREFIXES)
    ):
        raise RuntimeError(
            "WEB_UI_SESSION_SECRET must be a high-entropy value "
            f"with at least {SESSION_SECRET_MIN_LENGTH} characters.",
        )
    return secret


def cookie_secure(env: Mapping[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    value = values.get("WEB_UI_COOKIE_SECURE", "true").strip().lower()
    return value not in {"false", "0", "no", "off"}


def serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret, salt=SESSION_SALT)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_password(submitted: str, expected: str) -> bool:
    return compare_digest(submitted.encode("utf-8"), expected.encode("utf-8"))


def require_login_allowed(request: Request) -> None:
    throttle: LoginThrottle = request.app.state.login_throttle
    if not throttle.is_allowed(_client_key(request)):
        raise ApiException(
            429,
            "rate_limited",
            "Too many login attempts. Try again later.",
        )


def record_login_failure(request: Request) -> None:
    throttle: LoginThrottle = request.app.state.login_throttle
    throttle.record_failure(_client_key(request))


def record_login_success(request: Request) -> None:
    throttle: LoginThrottle = request.app.state.login_throttle
    throttle.record_success(_client_key(request))


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
    request.state.authenticated_session = payload
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


def set_session_cookie(
    request: Request,
    response: Response,
    csrf_token: str,
) -> None:
    cookie = encode_session(request.app.state.session_serializer, csrf_token)
    response.set_cookie(
        COOKIE_NAME,
        cookie,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        path="/",
        samesite="strict",
        secure=request.app.state.cookie_secure,
    )


def _client_key(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"
