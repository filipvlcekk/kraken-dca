"""Web UI authentication tests."""

from __future__ import annotations

from http.cookies import SimpleCookie

import itsdangerous.timed
import pytest
from fastapi.testclient import TestClient
from itsdangerous import BadSignature

from krakendca.web import auth
from krakendca.web.app import create_app

TEST_SESSION_SECRET = "test-session-secret-value-32-bytes"


def _session_cookie_value(response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[auth.COOKIE_NAME].value


def _set_web_auth_env(
    monkeypatch,
    password: str = "secret",
    session_secret: str = TEST_SESSION_SECRET,
) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", password)
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", session_secret)


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
    assert response.json() == {"ok": True, "data": {"authenticated": False}}


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
    assert session_response.json() == {
        "ok": True,
        "data": {"authenticated": False},
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
    assert restored.json() == {"ok": True, "data": {"authenticated": False}}


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
