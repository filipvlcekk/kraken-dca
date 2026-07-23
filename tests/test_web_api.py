"""Web API route tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from krakendca.config_store import REDACTED_SECRET
from krakendca.runner import RunResult
from krakendca.web.app import create_app


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
    monkeypatch.setattr("krakendca.web.app.SchedulerService", FakeSchedulerService)
    yield


@pytest.fixture()
def authed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_UI_PASSWORD", "secret")

    def _build(config: dict | str | None = None):
        path = str(tmp_path / "missing.yaml")
        if config is not None:
            path = write_config(tmp_path, config)
        app = create_app(config_path=path, static_dir=str(tmp_path / "frontend"))
        client = TestClient(app)
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


def test_missing_config_enters_setup_mode(authed_client) -> None:
    client, _path, _csrf = authed_client()

    config_response = client.get("/api/config")
    scheduler_response = client.get("/api/scheduler")

    assert config_response.status_code == 200
    assert config_response.json()["data"]["config_valid"] is False
    assert "config" in config_response.json()["data"]["validation_errors"]
    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["data"]["running"] is False
    assert scheduler_response.json()["data"]["jobs"] == []
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


def test_put_config_saves_and_reloads_scheduler(authed_client) -> None:
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
    assert body["data"]["scheduler_status"]["running"] is True
    with open(path, encoding="utf-8") as saved_file:
        saved = yaml.safe_load(saved_file)
    assert saved["dca_pairs"][0]["pair"] == "XXBTZEUR"
    assert FakeSchedulerService.instances[0].reload_calls[0]["dca_pairs"][0][
        "pair"
    ] == "XXBTZEUR"


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
    assert response.json()["data"]["config_applied"] is True
    assert FakeSchedulerService.instances[0].reload_calls[0]["dca_pairs"][0][
        "pair"
    ] == "XETHZEUR"


def test_manual_run_maps_completed_and_conflict_results(authed_client) -> None:
    client, _path, csrf = authed_client(valid_config())

    completed = client.post(
        "/api/pairs/XETHZEUR/run",
        headers={"X-CSRF-Token": csrf},
    )
    FakeSchedulerService.run_result = run_result(
        "XETHZEUR",
        "failed",
        reason="conflict",
    )
    conflict = client.post(
        "/api/pairs/XETHZEUR/run",
        headers={"X-CSRF-Token": csrf},
    )

    assert completed.status_code == 200
    assert completed.json()["data"]["result"]["status"] == "completed"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"


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
