"""Web UI authentication tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from krakendca.web.app import create_app


def test_startup_requires_web_ui_password(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("WEB_UI_PASSWORD", raising=False)
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="WEB_UI_PASSWORD"):
        with TestClient(app):
            pass


def test_unauthenticated_session_probe_returns_false(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/session")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": {"authenticated": False}}


def test_login_sets_signed_http_only_strict_cookie(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.delenv("WEB_UI_COOKIE_SECURE", raising=False)
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with TestClient(app) as client:
        response = client.post("/api/session", json={"password": "secret"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["csrf_token"]
    cookie = response.headers["set-cookie"]
    assert "kraken_dca_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" not in cookie


def test_secure_cookie_can_be_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.setenv("WEB_UI_COOKIE_SECURE", "true")
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with TestClient(app) as client:
        response = client.post("/api/session", json={"password": "secret"})

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_login_rejects_wrong_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with TestClient(app) as client:
        response = client.post("/api/session", json={"password": "wrong"})

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "unauthenticated",
            "message": "Invalid password.",
        },
    }


def test_session_restore_returns_fresh_csrf_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with TestClient(app) as client:
        login = client.post("/api/session", json={"password": "secret"})
        restored = client.get("/api/session")

    assert login.status_code == 200
    assert restored.status_code == 200
    assert restored.json()["data"]["authenticated"] is True
    assert restored.json()["data"]["csrf_token"]


def test_logout_clears_session_cookie(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with TestClient(app) as client:
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
    assert restored.json() == {"ok": True, "data": {"authenticated": False}}


def test_api_requires_auth_except_session_probe(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/config")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_static_login_allowed_but_spa_routes_require_auth(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))

    with TestClient(app) as client:
        login = client.get("/login")
        protected = client.get("/dashboard", follow_redirects=False)

    assert login.status_code == 200
    assert "Kraken DCA" in login.text
    assert protected.status_code in {307, 401}
    if protected.status_code == 307:
        assert protected.headers["location"] == "/login"
