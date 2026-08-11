"""Web UI authentication tests."""

from __future__ import annotations

from http.cookies import SimpleCookie
import time
from urllib.parse import parse_qs, urlparse

import itsdangerous.timed
import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from itsdangerous import BadSignature

from krakendca.web import auth
from krakendca.web import oidc
from krakendca.web.app import create_app

TEST_SESSION_SECRET = "test-session-secret-value-32-bytes"


class FakeOidcClient:
    def __init__(
        self,
        groups: list[str] | None = None,
        token_value: str = "opaque-token",
    ) -> None:
        self.groups = groups or ["kraken-dca-admins"]
        self.token_value = token_value
        self.calls: list[dict[str, str]] = []

    async def authenticate(self, code: str, nonce: str):
        self.calls.append({"code": code, "nonce": nonce})
        return oidc.OidcIdentity(
            subject="user-123",
            email="user@example.com",
            groups=self.groups,
            token_value=self.token_value,
        )


def _session_cookie_value(response) -> str:
    cookie = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookie.load(header)
    return cookie[auth.COOKIE_NAME].value


def _set_web_auth_env(
    monkeypatch,
    password: str = "secret",
    session_secret: str = TEST_SESSION_SECRET,
) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", password)
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", session_secret)


def _set_oidc_auth_env(monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "oidc")
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    monkeypatch.setenv("WEB_UI_OIDC_ISSUER", "https://id.example.com")
    monkeypatch.setenv("WEB_UI_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("WEB_UI_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv(
        "WEB_UI_OIDC_REDIRECT_URL",
        "https://app.example.com/api/auth/oidc/callback",
    )
    monkeypatch.setenv("WEB_UI_OIDC_ALLOWED_GROUP", "kraken-dca-admins")


def _oidc_config() -> oidc.OidcConfig:
    return oidc.OidcConfig(
        issuer="https://id.example.com",
        client_id="client-id",
        client_secret="client-secret",
        redirect_url="https://app.example.com/api/auth/oidc/callback",
        allowed_group="kraken-dca-admins",
    )


def _signed_id_token(
    key: RSAKey,
    claims: dict,
) -> str:
    return jwt.encode(
        {"alg": "RS256", "kid": key.as_dict()["kid"]},
        claims,
        key,
    )


def _valid_oidc_claims() -> dict:
    return {
        "iss": "https://id.example.com",
        "aud": "client-id",
        "sub": "user-123",
        "email": "user@example.com",
        "groups": ["kraken-dca-admins"],
        "nonce": "nonce-value",
        "exp": int(time.time()) + 300,
    }


def test_startup_requires_web_ui_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.delenv("WEB_UI_PASSWORD", raising=False)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with pytest.raises(RuntimeError, match="WEB_UI_PASSWORD"):
        with TestClient(app, base_url="https://testserver"):
            pass


def test_startup_rejects_empty_web_ui_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", "")
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with pytest.raises(RuntimeError, match="WEB_UI_PASSWORD"):
        with TestClient(app, base_url="https://testserver"):
            pass


def test_startup_requires_web_ui_auth_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("WEB_UI_AUTH_MODE", raising=False)
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with pytest.raises(RuntimeError, match="WEB_UI_AUTH_MODE"):
        with TestClient(app, base_url="https://testserver"):
            pass


def test_password_mode_requires_web_ui_password(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.delenv("WEB_UI_PASSWORD", raising=False)
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with pytest.raises(RuntimeError, match="WEB_UI_PASSWORD"):
        with TestClient(app, base_url="https://testserver"):
            pass


def test_oidc_mode_does_not_require_web_ui_password(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    monkeypatch.delenv("WEB_UI_PASSWORD", raising=False)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/session")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "authenticated": False,
        "auth_mode": "oidc",
        "oidc_login_url": "/api/auth/oidc/start",
    }


@pytest.mark.parametrize(
    "missing_env",
    [
        "WEB_UI_OIDC_ISSUER",
        "WEB_UI_OIDC_CLIENT_ID",
        "WEB_UI_OIDC_CLIENT_SECRET",
        "WEB_UI_OIDC_REDIRECT_URL",
        "WEB_UI_OIDC_ALLOWED_GROUP",
    ],
)
def test_oidc_mode_requires_oidc_configuration(
    tmp_path,
    monkeypatch,
    missing_env,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    monkeypatch.delenv(missing_env)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with pytest.raises(RuntimeError, match=missing_env):
        with TestClient(app, base_url="https://testserver"):
            pass


def test_oidc_start_redirects_to_provider_and_sets_state_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(
            "/api/auth/oidc/start",
            follow_redirects=False,
        )

    assert response.status_code in {302, 307}
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://id.example.com/authorize"
    )
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == [
        "https://app.example.com/api/auth/oidc/callback"
    ]
    assert query["scope"] == ["openid email profile groups"]
    assert query["state"][0]
    assert query["nonce"][0]

    cookie = response.headers["set-cookie"]
    assert "kraken_dca_oidc_state=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/auth/oidc" in cookie
    assert "Max-Age=600" in cookie


def test_oidc_start_is_rate_limited(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        for _attempt in range(auth.LOGIN_MAX_FAILURES):
            response = client.get(
                "/api/auth/oidc/start",
                follow_redirects=False,
            )
            assert response.status_code in {302, 307}

        response = client.get(
            "/api/auth/oidc/start",
            follow_redirects=False,
        )

    assert response.status_code == 429
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "rate_limited",
            "message": "Too many login attempts. Try again later.",
        },
    }


def test_oidc_callback_rejects_missing_state_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(
            "/api/auth/oidc/callback?code=code&state=state",
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert auth.COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_oidc_callback_rate_limit_prevents_token_exchange(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        fake_client = FakeOidcClient()
        client.app.state.oidc_client = fake_client
        start = client.get("/api/auth/oidc/start", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        client.app.state.oidc_throttle = auth.LoginThrottle(max_failures=0)
        response = client.get(
            f"/api/auth/oidc/callback?code=code&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert fake_client.calls == []


def test_oidc_callback_after_last_allowed_start_is_not_rate_limited(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        fake_client = FakeOidcClient()
        client.app.state.oidc_client = fake_client
        client.app.state.oidc_start_throttle = auth.LoginThrottle(
            max_failures=auth.LOGIN_MAX_FAILURES,
        )
        for _attempt in range(auth.LOGIN_MAX_FAILURES):
            start = client.get(
                "/api/auth/oidc/start",
                follow_redirects=False,
            )
            assert start.status_code in {302, 307}

        query = parse_qs(urlparse(start.headers["location"]).query)
        response = client.get(
            (
                "/api/auth/oidc/callback"
                f"?code=code&state={query['state'][0]}"
            ),
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/"
    assert fake_client.calls == [
        {"code": "code", "nonce": query["nonce"][0]},
    ]


def test_successful_oidc_login_clears_start_global_throttle(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        fake_client = FakeOidcClient()
        client.app.state.oidc_client = fake_client
        start_throttle = auth.LoginThrottle(
            max_failures=100,
            global_max_failures=1,
        )
        client.app.state.oidc_start_throttle = start_throttle
        client.app.state.oidc_throttle = start_throttle
        start = client.get("/api/auth/oidc/start", follow_redirects=False)
        query = parse_qs(urlparse(start.headers["location"]).query)
        client.app.state.oidc_throttle = auth.LoginThrottle(max_failures=100)
        callback = client.get(
            (
                "/api/auth/oidc/callback"
                f"?code=code&state={query['state'][0]}"
            ),
            follow_redirects=False,
        )
        client.app.state.oidc_throttle = start_throttle
        next_start = client.get(
            "/api/auth/oidc/start",
            follow_redirects=False,
        )

    assert callback.status_code == 307
    assert callback.headers["location"] == "/"
    assert next_start.status_code in {302, 307}


def test_oidc_callback_rejects_oversized_state_and_records_failure(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.app.state.oidc_throttle = auth.LoginThrottle(max_failures=1)
        response = client.get(
            f"/api/auth/oidc/callback?code=code&state={'s' * 257}",
            follow_redirects=False,
        )
        limited = client.get(
            "/api/auth/oidc/callback?code=code&state=state",
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"


def test_oidc_callback_rejects_oversized_code_before_token_exchange(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        fake_client = FakeOidcClient()
        client.app.state.oidc_client = fake_client
        start = client.get("/api/auth/oidc/start", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        client.app.state.oidc_throttle = auth.LoginThrottle(max_failures=1)
        response = client.get(
            f"/api/auth/oidc/callback?code={'c' * 4097}&state={state}",
            follow_redirects=False,
        )
        limited = client.get(
            f"/api/auth/oidc/callback?code=code&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert fake_client.calls == []
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"


def test_oidc_callback_rejects_tampered_state_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(
            oidc.OIDC_STATE_COOKIE_NAME,
            "tampered",
            path="/api/auth/oidc",
        )
        response = client.get(
            "/api/auth/oidc/callback?code=code&state=state",
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert auth.COOKIE_NAME not in response.headers.get("set-cookie", "")
    assert "Max-Age=0" not in response.headers.get("set-cookie", "")


def test_oidc_callback_rejects_state_mismatch(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        start = client.get("/api/auth/oidc/start", follow_redirects=False)
        location = start.headers["location"]
        state = parse_qs(urlparse(location).query)["state"][0]
        response = client.get(
            (
                "/api/auth/oidc/callback"
                f"?code=code&state={state}-wrong"
            ),
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert auth.COOKIE_NAME not in response.headers.get("set-cookie", "")
    assert "Max-Age=0" not in response.headers.get("set-cookie", "")


def test_oidc_callback_rejects_provider_error(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(
            "/api/auth/oidc/callback?error=access_denied",
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert auth.COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_oidc_callback_rejects_provider_error_with_state_mismatch(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.get("/api/auth/oidc/start", follow_redirects=False)
        response = client.get(
            (
                "/api/auth/oidc/callback"
                "?error=access_denied&state=wrong-state"
            ),
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert "Max-Age=0" not in response.headers.get("set-cookie", "")


def test_oidc_callback_rejects_missing_state_without_clearing_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.get("/api/auth/oidc/start", follow_redirects=False)
        response = client.get(
            "/api/auth/oidc/callback?error=access_denied",
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert "Max-Age=0" not in response.headers.get("set-cookie", "")


def test_oidc_callback_rejects_identity_without_allowed_group(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.app.state.oidc_client = FakeOidcClient(groups=["other"])
        start = client.get("/api/auth/oidc/start", follow_redirects=False)
        query = parse_qs(urlparse(start.headers["location"]).query)
        response = client.get(
            (
                "/api/auth/oidc/callback"
                f"?code=code&state={query['state'][0]}"
            ),
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login?error=oidc"
    assert auth.COOKIE_NAME not in response.headers.get("set-cookie", "")
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_oidc_callback_creates_app_session_without_storing_tokens(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        fake_client = FakeOidcClient(token_value="secret-access-token")
        client.app.state.oidc_client = fake_client
        start = client.get("/api/auth/oidc/start", follow_redirects=False)
        query = parse_qs(urlparse(start.headers["location"]).query)
        response = client.get(
            (
                "/api/auth/oidc/callback"
                f"?code=code&state={query['state'][0]}"
            ),
            follow_redirects=False,
        )
        restored = client.get("/api/session")

    assert response.status_code == 307
    assert response.headers["location"] == "/"
    assert fake_client.calls == [{"code": "code", "nonce": query["nonce"][0]}]
    assert oidc.OIDC_STATE_COOKIE_NAME in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    session = auth.serializer(TEST_SESSION_SECRET).loads(
        _session_cookie_value(response),
        max_age=auth.SESSION_MAX_AGE_SECONDS,
    )
    assert session["authenticated"] is True
    assert session["auth_mode"] == "oidc"
    assert session["sub"] == "user-123"
    assert session["email"] == "user@example.com"
    assert session["groups"] == ["kraken-dca-admins"]
    assert session["reauth_after"] > session["created_at"]
    assert "secret-access-token" not in str(session)
    assert "id_token" not in session
    assert "access_token" not in session
    assert "refresh_token" not in session
    assert restored.json()["data"]["authenticated"] is True
    assert restored.json()["data"]["csrf_token"]


def test_oidc_session_refresh_preserves_identity_payload(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.app.state.oidc_client = FakeOidcClient()
        start = client.get("/api/auth/oidc/start", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        callback = client.get(
            f"/api/auth/oidc/callback?code=code&state={state}",
            follow_redirects=False,
        )
        restored = client.get("/api/session")

    callback_session = auth.serializer(TEST_SESSION_SECRET).loads(
        _session_cookie_value(callback),
        max_age=auth.SESSION_MAX_AGE_SECONDS,
    )
    refreshed_session = auth.serializer(TEST_SESSION_SECRET).loads(
        _session_cookie_value(restored),
        max_age=auth.SESSION_MAX_AGE_SECONDS,
    )
    for key in (
        "auth_mode",
        "sub",
        "email",
        "groups",
        "created_at",
        "reauth_after",
    ):
        assert refreshed_session[key] == callback_session[key]


def test_expired_oidc_session_requires_reauthentication(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )
    expired_cookie = auth.serializer(TEST_SESSION_SECRET).dumps(
        {
            "authenticated": True,
            "csrf_token": auth.new_csrf_token(),
            "auth_mode": "oidc",
            "sub": "user-123",
            "groups": ["kraken-dca-admins"],
            "created_at": int(time.time()) - 7200,
            "reauth_after": int(time.time()) - 1,
        },
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(auth.COOKIE_NAME, expired_cookie)
        session_response = client.get("/api/session")
        config_response = client.get("/api/config")

    assert session_response.status_code == 200
    assert session_response.json()["data"] == {
        "authenticated": False,
        "auth_mode": "oidc",
        "oidc_login_url": "/api/auth/oidc/start",
    }
    assert config_response.status_code == 401


def test_oidc_mode_rejects_legacy_password_session_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )
    legacy_password_cookie = auth.serializer(TEST_SESSION_SECRET).dumps(
        {"authenticated": True, "csrf_token": auth.new_csrf_token()},
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(auth.COOKIE_NAME, legacy_password_cookie)
        session_response = client.get("/api/session")
        config_response = client.get("/api/config")

    assert session_response.status_code == 200
    assert session_response.json()["data"] == {
        "authenticated": False,
        "auth_mode": "oidc",
        "oidc_login_url": "/api/auth/oidc/start",
    }
    assert config_response.status_code == 401


def test_password_login_is_disabled_in_oidc_mode(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/session", json={"password": "secret"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_oidc_client_accepts_valid_id_token() -> None:
    key = RSAKey.generate_key(auto_kid=True)
    client = oidc.OidcClient(_oidc_config())
    token = _signed_id_token(key, _valid_oidc_claims())

    identity = client._identity_from_id_token(
        token,
        KeySet([key]).as_dict(),
        "nonce-value",
    )

    assert identity.subject == "user-123"
    assert identity.email == "user@example.com"
    assert identity.groups == ["kraken-dca-admins"]
    assert identity.token_value == token


@pytest.mark.parametrize(
    "claim_updates,nonce",
    [
        ({"iss": "https://evil.example.com"}, "nonce-value"),
        ({"aud": "wrong-client"}, "nonce-value"),
        ({"exp": 1}, "nonce-value"),
        ({}, "wrong-nonce"),
    ],
)
def test_oidc_client_rejects_invalid_id_token_claims(
    claim_updates,
    nonce,
) -> None:
    key = RSAKey.generate_key(auto_kid=True)
    claims = _valid_oidc_claims()
    claims.update(claim_updates)
    token = _signed_id_token(key, claims)
    client = oidc.OidcClient(_oidc_config())

    with pytest.raises(Exception):
        client._identity_from_id_token(
            token,
            KeySet([key]).as_dict(),
            nonce,
        )


def test_startup_requires_web_ui_session_secret(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.delenv("WEB_UI_SESSION_SECRET", raising=False)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with pytest.raises(RuntimeError, match="WEB_UI_SESSION_SECRET"):
        with TestClient(app, base_url="https://testserver"):
            pass


@pytest.mark.parametrize(
    "session_secret",
    ["short", "change-me", "change-me-change-me-change-me-change"],
)
def test_startup_rejects_weak_web_ui_session_secret(
    tmp_path,
    monkeypatch,
    session_secret,
) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", session_secret)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with pytest.raises(RuntimeError, match="WEB_UI_SESSION_SECRET"):
        with TestClient(app, base_url="https://testserver"):
            pass


def test_unauthenticated_session_probe_returns_false(
    tmp_path, monkeypatch
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/session")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "authenticated": False,
        "auth_mode": "password",
    }


def test_unauthenticated_oidc_session_probe_returns_login_capabilities(
    tmp_path,
    monkeypatch,
) -> None:
    _set_oidc_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/session")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data": {
            "authenticated": False,
            "auth_mode": "oidc",
            "oidc_login_url": "/api/auth/oidc/start",
        },
    }


def test_login_sets_signed_http_only_strict_secure_cookie_by_default(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    monkeypatch.delenv("WEB_UI_COOKIE_SECURE", raising=False)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/session", json={"password": "secret"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["csrf_token"]
    cookie = response.headers["set-cookie"]
    assert "kraken_dca_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Max-Age=43200" in cookie
    assert "Path=/" in cookie
    assert "Secure" in cookie


def test_secure_cookie_can_be_disabled_for_local_http(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    monkeypatch.setenv("WEB_UI_COOKIE_SECURE", " false ")
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/session", json={"password": "secret"})

    assert response.status_code == 200
    assert "Secure" not in response.headers["set-cookie"]


def test_expired_session_cookie_is_rejected(tmp_path, monkeypatch) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )
    now = 1_800_000_000
    monkeypatch.setattr(
        itsdangerous.timed.TimestampSigner,
        "get_timestamp",
        lambda _self: now - auth.SESSION_MAX_AGE_SECONDS - 1,
    )
    expired_cookie = auth.serializer(TEST_SESSION_SECRET).dumps(
        {"authenticated": True, "csrf_token": auth.new_csrf_token()},
    )
    monkeypatch.setattr(
        itsdangerous.timed.TimestampSigner,
        "get_timestamp",
        lambda _self: now,
    )

    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(auth.COOKIE_NAME, expired_cookie)
        session_response = client.get("/api/session")
        config_response = client.get("/api/config")

    assert session_response.status_code == 200
    assert session_response.json()["data"] == {
        "authenticated": False,
        "auth_mode": "password",
    }
    assert config_response.status_code == 401
    assert config_response.json()["error"]["code"] == "unauthenticated"


def test_secure_cookie_can_be_enabled(tmp_path, monkeypatch) -> None:
    _set_web_auth_env(monkeypatch)
    monkeypatch.setenv("WEB_UI_COOKIE_SECURE", "true")
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/session", json={"password": "secret"})

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_session_secret_override_signs_session_cookie(
    tmp_path, monkeypatch
) -> None:
    override_secret = "override-session-secret-value-32-bytes"
    _set_web_auth_env(monkeypatch, session_secret=override_secret)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/session", json={"password": "secret"})

    cookie_value = _session_cookie_value(response)
    payload = auth.serializer(override_secret).loads(
        cookie_value,
        max_age=auth.SESSION_MAX_AGE_SECONDS,
    )
    assert payload["authenticated"] is True
    with pytest.raises(BadSignature):
        auth.serializer("secret").loads(
            cookie_value,
            max_age=auth.SESSION_MAX_AGE_SECONDS,
        )


def test_login_rejects_wrong_password(tmp_path, monkeypatch) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/session", json={"password": "wrong"})

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "unauthenticated",
            "message": "Invalid password.",
        },
    }


def test_login_rate_limits_repeated_failed_password_attempts(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        for _attempt in range(5):
            response = client.post("/api/session", json={"password": "wrong"})
            assert response.status_code == 401

        response = client.post("/api/session", json={"password": "wrong"})

    assert response.status_code == 429
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "rate_limited",
            "message": "Too many login attempts. Try again later.",
        },
    }


def test_login_rejects_malformed_json_with_api_envelope(
    tmp_path, monkeypatch
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/session",
            content=b'{"password":',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "validation_error"


def test_login_rejects_invalid_utf8_json_with_api_envelope(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/session",
            content=b"\xff",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "validation_error"


def test_login_rejects_non_object_json_with_api_envelope(
    tmp_path, monkeypatch
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/session", json=["secret"])

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "validation_error"


def test_login_rejects_non_ascii_password_without_500(
    tmp_path, monkeypatch
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/session", json={"password": "pässword"})

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "unauthenticated",
            "message": "Invalid password.",
        },
    }


def test_session_restore_returns_fresh_csrf_token(
    tmp_path, monkeypatch
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/session", json={"password": "secret"})
        restored = client.get("/api/session")

    assert login.status_code == 200
    assert restored.status_code == 200
    assert restored.json()["data"]["authenticated"] is True
    assert restored.json()["data"]["csrf_token"]


def test_authenticated_api_refreshes_session_cookie_without_rotating_csrf(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/session", json={"password": "secret"})
        csrf_token = login.json()["data"]["csrf_token"]
        response = client.get("/api/config")

    assert response.status_code == 200
    assert "set-cookie" in response.headers
    refreshed = auth.serializer(TEST_SESSION_SECRET).loads(
        _session_cookie_value(response),
        max_age=auth.SESSION_MAX_AGE_SECONDS,
    )
    assert refreshed["csrf_token"] == csrf_token


def test_failed_csrf_request_does_not_refresh_session_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/session", json={"password": "secret"})
        assert login.status_code == 200
        response = client.post(
            "/api/scheduler/reload",
            headers={"X-CSRF-Token": "invalid"},
        )

    assert response.status_code == 403
    assert auth.COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_logout_clears_session_cookie(tmp_path, monkeypatch) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/session", json={"password": "secret"})
        csrf_token = login.json()["data"]["csrf_token"]
        response = client.delete(
            "/api/session",
            headers={"X-CSRF-Token": csrf_token},
        )
        restored = client.get("/api/session")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": {"authenticated": False}}
    assert "kraken_dca_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "Path=/" in response.headers["set-cookie"]
    assert restored.json()["data"] == {
        "authenticated": False,
        "auth_mode": "password",
    }


def test_api_requires_auth_except_session_probe(tmp_path, monkeypatch) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/config")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_static_login_allowed_but_spa_routes_require_auth(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        login = client.get("/login")
        protected = client.get("/dashboard", follow_redirects=False)

    assert login.status_code == 200
    assert "Kraken DCA" in login.text
    assert protected.status_code in {307, 401}
    if protected.status_code == 307:
        assert protected.headers["location"] == "/login"


def test_public_static_assets_are_allowed_without_auth(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text(
        "console.log('asset');", encoding="utf-8"
    )
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('asset');"


def test_encoded_asset_traversal_does_not_serve_non_asset_file(
    tmp_path,
    monkeypatch,
) -> None:
    _set_web_auth_env(monkeypatch)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (tmp_path / "secret.txt").write_text("do not serve", encoding="utf-8")
    app = create_app(
        config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path)
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(
            "/assets/%2e%2e/secret.txt", follow_redirects=False
        )

    assert response.status_code in {307, 401, 404}
    assert response.text != "do not serve"
