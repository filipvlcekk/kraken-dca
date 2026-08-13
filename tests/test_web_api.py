"""Web API route tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import csv

import pytest
import yaml
from fastapi.testclient import TestClient

from krakendca.config_store import REDACTED_SECRET
from krakendca.runner import RunResult
from krakendca.web.app import create_app

TEST_SESSION_SECRET = "test-session-secret-value-32-bytes"


def valid_config(pair: str = "XETHZEUR") -> dict:
    return {
        "api": {
            "public_key": "FILE_PUBLIC",
            "private_key": "FILE_PRIVATE",
        },
        "dca_pairs": [
            {
                "pair": pair,
                "delay": 1,
                "amount": 15,
            }
        ],
    }


def write_config(tmp_path, config: dict | str) -> str:
    path = tmp_path / "config.yaml"
    if isinstance(config, str):
        path.write_text(config, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(path)


@dataclass
class FakeSchedulerService:
    config_path: str
    env: dict | None = None
    kraken_api_factory: object | None = None
    runner: object | None = None

    instances: list["FakeSchedulerService"] = None
    reload_exception: Exception | None = None
    run_result: RunResult | None = None

    def __post_init__(self) -> None:
        self.started = False
        self.shutdown_called = False
        self.reload_calls: list[dict] = []
        type(self).instances.append(self)

    def start(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def reload(self, config: dict) -> dict:
        self.reload_calls.append(config)
        if type(self).reload_exception is not None:
            raise type(self).reload_exception
        return self.status()

    def status(self) -> dict:
        return {
            "running": self.started,
            "config_applied": True,
            "jobs": [{"id": "legacy-delay:XETHZEUR", "pair": "XETHZEUR"}],
        }

    def run_pair_now(self, pair: str) -> RunResult:
        return type(self).run_result or run_result(pair, "completed")


FakeSchedulerService.instances = []


@pytest.fixture(autouse=True)
def reset_fake_scheduler(monkeypatch):
    FakeSchedulerService.instances = []
    FakeSchedulerService.reload_exception = None
    FakeSchedulerService.run_result = None
    monkeypatch.setattr(
        "krakendca.web.app.SchedulerService", FakeSchedulerService
    )
    yield


@pytest.fixture()
def authed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)

    def _build(config: dict | str | None = None):
        path = str(tmp_path / "missing.yaml")
        if config is not None:
            path = write_config(tmp_path, config)
        app = create_app(
            config_path=path, static_dir=str(tmp_path / "frontend")
        )
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        login = client.post("/api/session", json={"password": "secret"})
        csrf_token = login.json()["data"]["csrf_token"]
        return client, path, csrf_token

    clients = []

    def _tracked(config: dict | str | None = None):
        client, path, csrf = _build(config)
        clients.append(client)
        return client, path, csrf

    yield _tracked

    for client in clients:
        client.__exit__(None, None, None)


def run_result(
    pair: str,
    status: str,
    *,
    reason: str | None = None,
    message: str = "message",
) -> RunResult:
    now = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
    return RunResult(
        pair=pair,
        status=status,
        reason=reason,
        started_at=now,
        finished_at=now,
        order_txid="TXID" if status == "completed" else None,
        message=message,
    )


def test_valid_config_starts_scheduler_and_returns_redacted_config(
    authed_client,
) -> None:
    client, _path, _csrf = authed_client(valid_config())

    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["config_valid"] is True
    assert body["data"]["validation_errors"] == {}
    assert body["data"]["config"]["api"] == {
        "public_key": REDACTED_SECRET,
        "private_key": REDACTED_SECRET,
    }
    assert body["data"]["secrets"]["public_key"] == {
        "configured": True,
        "source": "file",
    }
    assert FakeSchedulerService.instances[0].started is True


def test_env_credentials_are_redacted_as_null_with_env_secret_source(
    authed_client,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KRAKEN_API_PUBLIC_KEY", "ENV_PUBLIC")
    monkeypatch.setenv("KRAKEN_API_PRIVATE_KEY", "ENV_PRIVATE")
    config = valid_config()
    config.pop("api")
    client, _path, _csrf = authed_client(config)

    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["config"]["api"] == {
        "public_key": None,
        "private_key": None,
    }
    assert data["secrets"] == {
        "public_key": {"configured": True, "source": "env"},
        "private_key": {"configured": True, "source": "env"},
    }


def test_missing_config_enters_setup_mode(authed_client) -> None:
    client, _path, _csrf = authed_client()

    config_response = client.get("/api/config")
    scheduler_response = client.get("/api/scheduler")

    assert config_response.status_code == 200
    assert config_response.json()["data"]["config_valid"] is False
    assert "config" in config_response.json()["data"]["validation_errors"]
    assert scheduler_response.status_code == 200
    scheduler = scheduler_response.json()["data"]
    assert scheduler["running"] is False
    assert scheduler["jobs"] == []
    assert _scheduler_contract_keys().issubset(scheduler)
    assert scheduler["last_reload_at"] is None
    assert FakeSchedulerService.instances == []


@pytest.mark.parametrize("config_text", ["[]", "foo"])
def test_non_mapping_yaml_enters_degraded_mode_without_starting_scheduler(
    authed_client,
    config_text,
) -> None:
    client, _path, _csrf = authed_client(config_text)

    response = client.get("/api/config")
    scheduler_response = client.get("/api/scheduler")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["config_valid"] is False
    assert data["config"] == {}
    assert data["raw_yaml"] is None
    assert "config" in data["validation_errors"]
    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["data"]["running"] is False
    assert FakeSchedulerService.instances == []


def test_malformed_yaml_enters_degraded_mode_without_secrets(
    authed_client,
) -> None:
    client, _path, _csrf = authed_client("api: [unterminated")

    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["config_valid"] is False
    assert data["config"] == {}
    assert data["validation_errors"]["config"]
    assert FakeSchedulerService.instances == []


def test_invalid_utf8_config_enters_degraded_mode_without_leaking_bytes(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    config_path = tmp_path / "config.yaml"
    config_path.write_bytes(b"api:\n  private_key: \xff\n")
    app = create_app(
        config_path=str(config_path), static_dir=str(tmp_path / "frontend")
    )

    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/session", json={"password": "secret"})
        response = client.get("/api/config")
        scheduler_response = client.get("/api/scheduler")

    assert login.status_code == 200
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["config_valid"] is False
    assert data["config"] == {}
    assert data["raw_yaml"] is None
    assert data["validation_errors"] == {"config": "Config YAML is malformed."}
    assert "\\ufffd" not in json.dumps(response.json())
    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["data"]["running"] is False
    assert FakeSchedulerService.instances == []


def test_malformed_yaml_does_not_leak_secret_text_in_degraded_config_response(
    authed_client,
) -> None:
    secret = "-----BEGIN FAKE PRIVATE KEY-----"
    client, _path, _csrf = authed_client(
        f'api:\n  private_key: "{secret}\ndca_pairs: []\n',
    )

    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["raw_yaml"] is None
    assert secret not in json.dumps(body)


def test_yaml_parser_error_text_is_sanitized_in_degraded_config_response(
    tmp_path,
    monkeypatch,
) -> None:
    secret = "-----BEGIN FAKE PRIVATE KEY-----"
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f'api:\n  private_key: "{secret}\ndca_pairs: []\n',
        encoding="utf-8",
    )

    def raise_parser_error(_path):
        raise yaml.YAMLError(f"parser leaked {secret}")

    monkeypatch.setattr(
        "krakendca.web.app.load_config_preserving_root",
        raise_parser_error,
    )
    app = create_app(
        config_path=str(config_path), static_dir=str(tmp_path / "frontend")
    )

    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/session", json={"password": "secret"})
        response = client.get("/api/config")

    assert login.status_code == 200
    body = response.json()
    assert body["data"]["raw_yaml"] is None
    assert secret not in json.dumps(body)


def test_semantic_validation_errors_are_returned_redacted(
    authed_client,
) -> None:
    invalid = valid_config()
    invalid["dca_pairs"][0]["amount"] = 0
    client, _path, _csrf = authed_client(invalid)

    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["config_valid"] is False
    assert data["config"]["api"]["public_key"] == REDACTED_SECRET
    assert "dca_pairs.0.amount" in data["validation_errors"]
    assert FakeSchedulerService.instances == []


def test_put_config_requires_valid_csrf(authed_client) -> None:
    client, _path, _csrf = authed_client(valid_config())

    response = client.put("/api/config", json={"config": valid_config()})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_invalid"


def test_put_config_rejects_malformed_json_with_api_envelope(
    authed_client,
) -> None:
    client, _path, csrf = authed_client(valid_config())

    response = client.put(
        "/api/config",
        content=b'{"config":',
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "validation_error"


def test_put_config_rejects_invalid_utf8_json_with_api_envelope(
    authed_client,
) -> None:
    client, _path, csrf = authed_client(valid_config())

    response = client.put(
        "/api/config",
        content=b"\xff",
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "validation_error"


def test_put_config_rejects_non_object_json_with_api_envelope(
    authed_client,
) -> None:
    client, _path, csrf = authed_client(valid_config())

    response = client.put(
        "/api/config",
        json=[],
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "validation_error",
            "message": "Request body must be a JSON object.",
            "fields": {"body": "Request body must be a JSON object."},
        },
    }


def test_put_config_saves_and_returns_required_scheduler_contract(
    authed_client,
) -> None:
    client, path, csrf = authed_client(valid_config())
    submitted = valid_config("XXBTZEUR")

    response = client.put(
        "/api/config",
        json={"config": submitted},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["config"]["dca_pairs"][0]["pair"] == "XXBTZEUR"
    assert "scheduler_status" not in body["data"]
    assert body["data"]["scheduler"]["running"] is True
    assert _scheduler_contract_keys().issubset(body["data"]["scheduler"])
    with open(path, encoding="utf-8") as saved_file:
        saved = yaml.safe_load(saved_file)
    assert saved["dca_pairs"][0]["pair"] == "XXBTZEUR"
    assert (
        FakeSchedulerService.instances[0].reload_calls[0]["dca_pairs"][0][
            "pair"
        ]
        == "XXBTZEUR"
    )


def test_put_config_validation_error_returns_400(authed_client) -> None:
    client, _path, csrf = authed_client(valid_config())
    submitted = valid_config()
    submitted["dca_pairs"][0]["amount"] = 0

    response = client.put(
        "/api/config",
        json={"config": submitted},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert "dca_pairs.0.amount" in response.json()["error"]["fields"]


def test_put_config_rejects_truthy_non_mapping_api_with_validation_error(
    authed_client,
) -> None:
    client, _path, csrf = authed_client(valid_config())
    submitted = valid_config()
    submitted["api"] = ["public_key"]

    response = client.put(
        "/api/config",
        json={"config": submitted},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["fields"] == {
        "api": "API credentials must be an object."
    }


def test_put_config_rejects_unsafe_orders_filepath(authed_client) -> None:
    client, _path, csrf = authed_client(valid_config())
    submitted = valid_config()
    submitted["orders_filepath"] = "/tmp/orders.csv"

    response = client.put(
        "/api/config",
        json={"config": submitted},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    expected = (
        "orders_filepath must be a relative CSV filename without directories."
    )
    assert response.json()["error"]["fields"] == {"orders_filepath": expected}


def test_put_config_malformed_existing_yaml_error_does_not_leak_secret(
    authed_client,
) -> None:
    secret = "-----BEGIN FAKE PRIVATE KEY-----"
    client, path, csrf = authed_client()
    with open(path, "w", encoding="utf-8") as config_file:
        config_file.write(f'api:\n  private_key: "{secret}\ndca_pairs: []\n')

    response = client.put(
        "/api/config",
        json={"config": valid_config()},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert secret not in json.dumps(body)


def test_put_config_invalid_utf8_existing_config_returns_validation_error(
    authed_client,
) -> None:
    client, path, csrf = authed_client()
    with open(path, "wb") as config_file:
        config_file.write(b"api:\n  private_key: \xff\n")

    response = client.put(
        "/api/config",
        json={"config": valid_config()},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["fields"] == {
        "config": "Existing config YAML is malformed.",
    }
    assert "\\ufffd" not in json.dumps(body)


def test_put_config_parser_error_text_is_sanitized(
    authed_client, monkeypatch
) -> None:
    secret = "-----BEGIN FAKE PRIVATE KEY-----"
    client, _path, csrf = authed_client(valid_config())

    def raise_parser_error(_path, _submitted):
        raise yaml.YAMLError(f"parser leaked {secret}")

    monkeypatch.setattr(
        "krakendca.web.routes_config.config_store.save_config",
        raise_parser_error,
    )

    response = client.put(
        "/api/config",
        json={"config": valid_config()},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert secret not in json.dumps(body)


def test_put_config_persistence_failure_returns_500_envelope_without_leak(
    authed_client,
    monkeypatch,
) -> None:
    secret = "-----BEGIN FAKE PRIVATE KEY-----"
    client, _path, csrf = authed_client(valid_config())

    def raise_persistence_error(_path, _submitted):
        raise OSError(f"disk error leaked {secret}")

    monkeypatch.setattr(
        "krakendca.web.routes_config.config_store.save_config",
        raise_persistence_error,
    )

    response = client.put(
        "/api/config",
        json={"config": valid_config("XXBTZEUR")},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "config_persistence_failed"
    assert body["error"]["message"] == "Config could not be saved."
    assert body["error"]["details"] == {
        "config_saved": False,
        "scheduler_reloaded": False,
    }
    assert secret not in json.dumps(body)


def test_put_config_reports_reload_failure_after_save(authed_client) -> None:
    FakeSchedulerService.reload_exception = RuntimeError("boom")
    client, _path, csrf = authed_client(valid_config())

    response = client.put(
        "/api/config",
        json={"config": valid_config("XXBTZEUR")},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 500
    assert response.json()["error"]["details"] == {
        "config_saved": True,
        "scheduler_reloaded": False,
    }


def test_reload_reads_saved_config_not_client_payload(authed_client) -> None:
    client, _path, csrf = authed_client(valid_config("XETHZEUR"))

    response = client.post(
        "/api/scheduler/reload",
        json={"config": valid_config("SHOULD_NOT_USE")},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"scheduler"}
    assert data["scheduler"]["config_applied"] is True
    assert _scheduler_contract_keys().issubset(data["scheduler"])
    assert (
        FakeSchedulerService.instances[0].reload_calls[0]["dca_pairs"][0][
            "pair"
        ]
        == "XETHZEUR"
    )


def test_asset_pair_search_returns_canonical_pair_suggestions(
    authed_client,
    monkeypatch,
) -> None:
    client, _path, _csrf = authed_client(valid_config())
    fake_instances = []

    class FakeKrakenClient:
        def __init__(self, *_args, **_kwargs) -> None:
            self.closed = False
            fake_instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            self.close()

        def close(self) -> None:
            self.closed = True

        def get_asset_pairs(self) -> dict:
            return {
                "XXBTZEUR": {
                    "altname": "XBTEUR",
                    "wsname": "XBT/EUR",
                    "base": "XXBT",
                    "quote": "ZEUR",
                    "pair_decimals": 1,
                    "lot_decimals": 8,
                    "ordermin": "0.0002",
                }
            }

    monkeypatch.setattr(
        "krakendca.web.routes_asset_pairs.KrakenClient",
        FakeKrakenClient,
    )

    response = client.get("/api/asset-pairs?q=BTC%2FEUR")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data": {
            "pairs": [
                {
                    "pair": "XXBTZEUR",
                    "altname": "XBTEUR",
                    "wsname": "XBT/EUR",
                    "base": "XXBT",
                    "quote": "ZEUR",
                }
            ]
        },
    }
    assert fake_instances[0].closed is True


@pytest.mark.parametrize("config_text", ["[]", "foo"])
def test_reload_rejects_non_mapping_saved_config_with_validation_envelope(
    authed_client,
    config_text,
) -> None:
    client, _path, csrf = authed_client(config_text)

    response = client.post(
        "/api/scheduler/reload",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "validation_error"
    assert "config" in response.json()["error"]["fields"]
    assert FakeSchedulerService.instances == []


def test_reload_malformed_yaml_error_does_not_leak_secret(
    authed_client,
) -> None:
    secret = "-----BEGIN FAKE PRIVATE KEY-----"
    client, _path, csrf = authed_client(
        f'api:\n  private_key: "{secret}\ndca_pairs: []\n',
    )

    response = client.post(
        "/api/scheduler/reload",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert secret not in json.dumps(body)


def test_reload_invalid_utf8_config_returns_validation_error(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    config_path = tmp_path / "config.yaml"
    config_path.write_bytes(b"api:\n  private_key: \xff\n")
    app = create_app(
        config_path=str(config_path), static_dir=str(tmp_path / "frontend")
    )

    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/session", json={"password": "secret"})
        csrf = login.json()["data"]["csrf_token"]
        response = client.post(
            "/api/scheduler/reload",
            headers={"X-CSRF-Token": csrf},
        )

    assert login.status_code == 200
    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["fields"] == {"config": "Config YAML is malformed."}
    assert "\\ufffd" not in json.dumps(body)
    assert FakeSchedulerService.instances == []


def test_reload_parser_error_text_is_sanitized(
    authed_client, monkeypatch
) -> None:
    secret = "-----BEGIN FAKE PRIVATE KEY-----"
    client, _path, csrf = authed_client(valid_config())

    def raise_parser_error(_path):
        raise yaml.YAMLError(f"parser leaked {secret}")

    monkeypatch.setattr(
        "krakendca.web.routes_scheduler.load_config_preserving_root",
        raise_parser_error,
    )

    response = client.post(
        "/api/scheduler/reload",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert secret not in json.dumps(body)


def test_scheduler_status_returns_required_contract_for_active_scheduler(
    authed_client,
) -> None:
    client, _path, _csrf = authed_client(valid_config())

    response = client.get("/api/scheduler")

    assert response.status_code == 200
    scheduler = response.json()["data"]
    assert _scheduler_contract_keys().issubset(scheduler)
    assert scheduler["running"] is True
    assert scheduler["config_applied"] is True
    assert scheduler["last_reload_at"] is None


def test_manual_run_completed_success_returns_result_fields_at_data_top_level(
    authed_client,
) -> None:
    client, _path, csrf = authed_client(valid_config())

    response = client.post(
        "/api/pairs/XETHZEUR/run",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "result" not in data
    assert data == {
        "pair": "XETHZEUR",
        "status": "completed",
        "reason": None,
        "started_at": "2026-07-22T09:00:00+00:00",
        "finished_at": "2026-07-22T09:00:00+00:00",
        "order_txid": "TXID",
        "message": "message",
    }


def test_manual_run_accepts_encoded_slash_pair_path(authed_client) -> None:
    client, _path, csrf = authed_client(valid_config("XBT/EUR"))

    response = client.post(
        "/api/pairs/XBT%2FEUR/run",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.json()["data"]["pair"] == "XBT/EUR"


def test_manual_run_maps_conflict_result_to_409(authed_client) -> None:
    FakeSchedulerService.run_result = run_result(
        "XETHZEUR",
        "failed",
        reason="conflict",
    )
    client, _path, csrf = authed_client(valid_config())

    response = client.post(
        "/api/pairs/XETHZEUR/run",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("DELETE", "/api/session"),
        ("POST", "/api/scheduler/reload"),
        ("POST", "/api/pairs/XETHZEUR/run"),
    ],
)
@pytest.mark.parametrize("csrf_token", [None, "invalid"])
def test_authenticated_unsafe_api_routes_require_valid_csrf(
    authed_client,
    method,
    path,
    csrf_token,
) -> None:
    client, _path, _csrf = authed_client(valid_config())
    headers = {}
    if csrf_token is not None:
        headers["X-CSRF-Token"] = csrf_token

    response = client.request(method, path, headers=headers)

    assert response.status_code == 403
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "csrf_invalid",
            "message": "Missing or invalid CSRF token.",
        },
    }


@pytest.mark.parametrize(
    ("status", "reason", "expected_status", "expected_code"),
    [
        ("skipped", "min_order_interval", 200, None),
        ("failed", "config_not_applied", 409, "config_not_applied"),
        ("failed", "domain_error", 400, "domain_error"),
        ("failed", "domain", 400, "domain"),
        ("failed", "insufficient_funds", 400, "insufficient_funds"),
        ("failed", "network_error", 502, "network_error"),
        ("failed", "history_unwritable", 500, "history_unwritable"),
        (
            "failed",
            "history_persistence_failed",
            500,
            "history_persistence_failed",
        ),
        ("failed", "unexpected", 500, "unexpected"),
        ("failed", None, 500, "failed"),
    ],
)
def test_manual_run_result_status_mapping(
    authed_client,
    status,
    reason,
    expected_status,
    expected_code,
) -> None:
    FakeSchedulerService.run_result = run_result(
        "XETHZEUR",
        status,
        reason=reason,
    )
    client, _path, csrf = authed_client(valid_config())

    response = client.post(
        "/api/pairs/XETHZEUR/run",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == expected_status
    body = response.json()
    if expected_status == 200:
        assert body["ok"] is True
        assert body["data"]["pair"] == "XETHZEUR"
        assert body["data"]["status"] == status
        assert body["data"]["reason"] == reason
    else:
        assert body["ok"] is False
        assert body["error"]["code"] == expected_code
        assert body["error"]["details"]["result"]["pair"] == "XETHZEUR"


def test_manual_run_maps_kraken_error_to_502(authed_client) -> None:
    FakeSchedulerService.run_result = run_result(
        "XETHZEUR",
        "failed",
        reason="kraken_error",
    )
    client, _path, csrf = authed_client(valid_config())

    response = client.post(
        "/api/pairs/XETHZEUR/run",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "kraken_error"


def test_history_requires_authentication(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    app = create_app(
        config_path=write_config(tmp_path, valid_config()),
        static_dir=str(tmp_path / "frontend"),
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/history")

    assert response.status_code == 401
    assert response.json()["ok"] is False


def test_history_returns_empty_state_for_missing_orders_file(
    authed_client,
) -> None:
    config = valid_config()
    config["orders_filepath"] = "orders.csv"
    client, _path, _csrf = authed_client(config)

    response = client.get("/api/history")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["entries"] == []
    assert data["pairs"] == []
    assert data["portfolio"]["trade_count"] == 0
    assert data["portfolio"]["total_spent"] == "0"
    assert data["chart"] == []
    assert data["valuation"]["status"] == "not_available"


def test_history_returns_completed_order_summary(
    authed_client,
    monkeypatch,
) -> None:
    config = valid_config()
    config["orders_filepath"] = "orders.csv"
    client, path, _csrf = authed_client(config)
    _write_order_rows(
        path,
        [
            _history_row(
                date="2026-07-20 10:00:00",
                volume="0.01",
                price="20",
                fee="0.05",
                total_price="20.05",
                txid="ETH1",
            ),
            _history_row(
                date="2026-07-21 10:00:00",
                volume="0.02",
                price="40",
                fee="0.10",
                total_price="40.10",
                txid="ETH2",
            ),
        ],
    )

    class FakeKrakenClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_pair_ticker(self, pair: str) -> dict:
            assert pair == "XETHZEUR"
            return {"XETHZEUR": {"c": ["2500.0", "0.01"]}}

    monkeypatch.setattr(
        "krakendca.web.routes_history.KrakenClient",
        FakeKrakenClient,
    )

    response = client.get("/api/history")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [entry["txid"] for entry in data["entries"]] == ["ETH2", "ETH1"]
    assert data["pairs"][0]["pair"] == "XETHZEUR"
    assert data["pairs"][0]["trade_count"] == 2
    assert data["pairs"][0]["total_volume"] == "0.03"
    assert data["pairs"][0]["total_spent"] == "60.15"
    assert data["pairs"][0]["estimated_value"] == "75.000"
    assert data["pairs"][0]["estimated_pl"] == "14.850"
    assert data["portfolio"]["estimated_pl"] == "14.850"
    assert data["chart"][-1]["cumulative_spent"] == "60.15"
    assert data["valuation"]["status"] == "live"


def test_history_keeps_csv_data_when_live_prices_fail(
    authed_client,
    monkeypatch,
) -> None:
    config = valid_config()
    config["orders_filepath"] = "orders.csv"
    client, path, _csrf = authed_client(config)
    _write_order_rows(path, [_history_row()])

    class FailingKrakenClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_pair_ticker(self, _pair: str) -> dict:
            raise ConnectionError("network down")

    monkeypatch.setattr(
        "krakendca.web.routes_history.KrakenClient",
        FailingKrakenClient,
    )

    response = client.get("/api/history")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["entries"][0]["txid"] == "TXID"
    assert data["pairs"][0]["estimated_pl"] is None
    assert data["valuation"]["status"] == "unavailable"
    assert data["valuation"]["message"] == "Live Kraken price unavailable."


def test_history_uses_pair_level_orders_filepath(
    authed_client,
    monkeypatch,
) -> None:
    config = valid_config()
    config["orders_filepath"] = "unused-default.csv"
    config["dca_pairs"][0]["orders_filepath"] = "pair-orders.csv"
    client, path, _csrf = authed_client(config)
    from pathlib import Path

    _write_order_rows_to_path(
        Path(path).parent / "pair-orders.csv",
        [_history_row(txid="PAIR-FILE")],
    )

    class FakeKrakenClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_pair_ticker(self, _pair: str) -> dict:
            return {"XETHZEUR": {"c": ["2500.0", "0.01"]}}

    monkeypatch.setattr(
        "krakendca.web.routes_history.KrakenClient",
        FakeKrakenClient,
    )

    response = client.get("/api/history")

    assert response.status_code == 200
    assert [entry["txid"] for entry in response.json()["data"]["entries"]] == [
        "PAIR-FILE"
    ]


def _scheduler_contract_keys() -> set[str]:
    return {
        "running",
        "config_applied",
        "saved_config_fingerprint",
        "active_config_fingerprint",
        "reload_error",
        "last_reload_at",
        "jobs",
    }


def _write_order_rows(config_path: str, rows: list[dict[str, str]]) -> None:
    _write_order_rows_to_path(tmp_orders_path(config_path), rows)


def _write_order_rows_to_path(path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def tmp_orders_path(config_path: str):
    from pathlib import Path

    return Path(config_path).parent / "orders.csv"


def _history_row(
    *,
    date: str = "2026-07-20 10:00:00",
    pair: str = "XETHZEUR",
    volume: str = "0.01",
    price: str = "20",
    fee: str = "0.05",
    total_price: str = "20.05",
    txid: str = "TXID",
) -> dict[str, str]:
    return {
        "date": date,
        "pair": pair,
        "type": "buy",
        "order_type": "limit",
        "o_flags": "fciq",
        "pair_price": "2000",
        "volume": volume,
        "price": price,
        "fee": fee,
        "total_price": total_price,
        "txid": txid,
        "description": f"buy {volume} {pair} @ limit 2000",
    }
