"""Scheduler service tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import yaml

from krakendca.config_store import ConfigValidationError, fingerprint_config
from krakendca.runner import RunResult
from krakendca.scheduler import SchedulerService


def _config(pairs: list[dict], api: dict | None = None) -> dict:
    return {
        "api": api
        if api is not None
        else {
            "public_key": "FILE_PUBLIC_KEY",
            "private_key": "FILE_PRIVATE_KEY",
        },
        "dca_pairs": pairs,
    }


def _pair(
    pair: str = "XETHZEUR",
    *,
    schedule: dict | None = None,
    delay: int | object | None = 1,
) -> dict:
    dca_pair = {"pair": pair, "amount": 15}
    if schedule is not None:
        dca_pair["schedule"] = schedule
    if delay is not None:
        dca_pair["delay"] = delay
    return dca_pair


def _write_config(tmp_path, config: dict) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(path)


def _started_service(
    tmp_path,
    config: dict,
    *,
    runner=None,
    factory=None,
    env: dict | None = None,
) -> SchedulerService:
    service = SchedulerService(
        _write_config(tmp_path, config),
        env={} if env is None else env,
        kraken_api_factory=factory or FakeKrakenFactory(),
        runner=runner or FakeRunner(),
    )
    service.start()
    return service


def _job(status: dict, job_id: str) -> dict:
    return {job["id"]: job for job in status["jobs"]}[job_id]


def _ok_result(pair: str) -> RunResult:
    now = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
    return RunResult(
        pair=pair,
        status="success",
        reason=None,
        started_at=now,
        finished_at=now,
        order_txid=None,
        message="ok",
    )


class FakeKrakenFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, public_key: str, private_key: str) -> dict:
        self.calls.append((public_key, private_key))
        return {"public_key": public_key, "private_key": private_key}


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, str, object]] = []

    def __call__(self, config: dict, pair: str, kraken_api: object) -> RunResult:
        self.calls.append((config, pair, kraken_api))
        return _ok_result(pair)


def test_start_sets_running_true_and_matching_fingerprints(tmp_path) -> None:
    config = _config(
        [
            _pair(
                schedule={
                    "enabled": True,
                    "cron": "0 9 * * *",
                    "timezone": "UTC",
                }
            )
        ]
    )
    expected_fingerprint = fingerprint_config(config, {})
    service = SchedulerService(
        _write_config(tmp_path, config),
        env={},
        kraken_api_factory=FakeKrakenFactory(),
        runner=FakeRunner(),
    )

    service.start()
    try:
        status = service.status()
    finally:
        service.shutdown()

    assert status["running"] is True
    assert status["saved_config_fingerprint"] == expected_fingerprint
    assert status["active_config_fingerprint"] == expected_fingerprint
    assert status["config_applied"] is True


def test_not_started_status_reports_config_not_applied(tmp_path) -> None:
    service = SchedulerService(
        _write_config(tmp_path, _config([_pair()])),
        env={},
        kraken_api_factory=FakeKrakenFactory(),
        runner=FakeRunner(),
    )

    status = service.status()

    assert status["running"] is False
    assert status["config_applied"] is False
    assert status["saved_config_fingerprint"] is None
    assert status["active_config_fingerprint"] is None
    assert status["jobs"] == []


def test_start_assigns_active_state_before_starting_scheduler(
    tmp_path,
    monkeypatch,
) -> None:
    config = _config([_pair("XETHZEUR", delay=1)])
    expected_fingerprint = fingerprint_config(config, {})
    service = SchedulerService(
        _write_config(tmp_path, config),
        env={},
        kraken_api_factory=FakeKrakenFactory(),
        runner=FakeRunner(),
    )
    observed = {}
    original_start = service._scheduler.start

    def start_spy(*args, **kwargs):
        observed["active_config"] = service._active_config
        observed["job_ids"] = set(service._job_specs)
        observed["saved_fingerprint"] = service.saved_config_fingerprint
        observed["active_fingerprint"] = service.active_config_fingerprint
        observed["reload_error"] = service.reload_error
        return original_start(*args, **kwargs)

    monkeypatch.setattr(service._scheduler, "start", start_spy)

    service.start()
    try:
        assert observed["active_config"] is not None
        assert observed["active_config"]["dca_pairs"][0]["pair"] == "XETHZEUR"
        assert observed["job_ids"] == {"legacy-delay:XETHZEUR"}
        assert observed["saved_fingerprint"] == expected_fingerprint
        assert observed["active_fingerprint"] == expected_fingerprint
        assert observed["reload_error"] is None
    finally:
        service.shutdown()


def test_shutdown_waits_for_running_jobs(tmp_path, monkeypatch) -> None:
    service = _started_service(tmp_path, _config([_pair("XETHZEUR", delay=1)]))
    observed = []
    original_shutdown = service._scheduler.shutdown

    def shutdown_spy(*, wait: bool = True):
        observed.append(wait)
        return original_shutdown(wait=wait)

    monkeypatch.setattr(service._scheduler, "shutdown", shutdown_spy)

    service.shutdown()

    assert observed == [True]


def test_reload_success_replaces_jobs_and_updates_lifecycle_state(tmp_path) -> None:
    service = _started_service(tmp_path, _config([_pair("XETHZEUR", delay=1)]))
    new_config = _config(
        [
            _pair(
                "XXBTZEUR",
                schedule={
                    "enabled": True,
                    "cron": "30 10 * * *",
                    "timezone": "Europe/Prague",
                },
                delay=None,
            )
        ]
    )
    expected_fingerprint = fingerprint_config(new_config, {})

    try:
        status = service.reload(new_config)
    finally:
        service.shutdown()

    assert status["config_applied"] is True
    assert status["saved_config_fingerprint"] == expected_fingerprint
    assert status["active_config_fingerprint"] == expected_fingerprint
    assert status["reload_error"] is None
    assert status["last_reload_at"] is not None
    assert {job["id"] for job in status["jobs"]} == {"dca:XXBTZEUR"}


def test_reload_runtime_failure_preserves_previous_active_jobs_when_restore_succeeds(
    tmp_path,
    monkeypatch,
) -> None:
    old_config = _config(
        [
            _pair(
                "XETHZEUR",
                schedule={
                    "enabled": True,
                    "cron": "0 9 * * *",
                    "timezone": "UTC",
                },
                delay=None,
            )
        ]
    )
    service = _started_service(tmp_path, old_config)
    old_fingerprint = fingerprint_config(old_config, {})
    new_config = _config(
        [
            _pair(
                "XXBTZEUR",
                schedule={
                    "enabled": True,
                    "cron": "30 10 * * *",
                    "timezone": "UTC",
                },
                delay=None,
            )
        ]
    )
    new_fingerprint = fingerprint_config(new_config, {})
    original_add_job = service._scheduler.add_job

    def add_job_spy(*args, **kwargs):
        if kwargs.get("id") == "dca:XXBTZEUR":
            raise RuntimeError("new job add failed")
        return original_add_job(*args, **kwargs)

    monkeypatch.setattr(service._scheduler, "add_job", add_job_spy)

    try:
        status = service.reload(new_config)
    finally:
        service.shutdown()

    assert status["config_applied"] is False
    assert status["saved_config_fingerprint"] == new_fingerprint
    assert status["active_config_fingerprint"] == old_fingerprint
    assert "new job add failed" in status["reload_error"]
    assert {job["id"] for job in status["jobs"]} == {"dca:XETHZEUR"}


def test_reload_restore_failure_does_not_report_stale_jobs(
    tmp_path,
    monkeypatch,
) -> None:
    old_config = _config([_pair("XETHZEUR", delay=1)])
    service = _started_service(tmp_path, old_config)
    old_fingerprint = fingerprint_config(old_config, {})
    new_config = _config([_pair("XXBTZEUR", delay=1)])
    new_fingerprint = fingerprint_config(new_config, {})

    def add_job_spy(*args, **kwargs):
        raise RuntimeError(f"cannot add {kwargs.get('id')}")

    monkeypatch.setattr(service._scheduler, "add_job", add_job_spy)

    try:
        status = service.reload(new_config)
        actual_scheduler_jobs = service._scheduler.get_jobs()
    finally:
        service.shutdown()

    assert status["config_applied"] is False
    assert status["saved_config_fingerprint"] == new_fingerprint
    assert status["active_config_fingerprint"] == old_fingerprint
    assert status["jobs"] == []
    assert actual_scheduler_jobs == []
    assert "cannot add legacy-delay:XXBTZEUR" in status["reload_error"]


def test_scheduler_jobs_use_required_apscheduler_options(tmp_path) -> None:
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * *",
                        "timezone": "UTC",
                    }
                ),
                _pair("XXBTZEUR", delay=2),
            ]
        ),
    )

    try:
        jobs = {
            job.id: job
            for job in (
                service._scheduler.get_job("dca:XETHZEUR"),
                service._scheduler.get_job("legacy-delay:XXBTZEUR"),
            )
        }
    finally:
        service.shutdown()

    for job in jobs.values():
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.misfire_grace_time == 300


def test_reload_validation_error_propagates_and_preserves_active_state(
    tmp_path,
) -> None:
    config = _config(
        [
            _pair(
                schedule={
                    "enabled": True,
                    "cron": "0 9 * * *",
                    "timezone": "UTC",
                }
            )
        ]
    )
    service = _started_service(tmp_path, config)
    original_fingerprint = fingerprint_config(config, {})

    try:
        with pytest.raises(ConfigValidationError):
            service.reload(
                _config(
                    [
                        _pair(
                            "XXBTZEUR",
                            schedule={
                                "enabled": True,
                                "cron": "not cron",
                                "timezone": "UTC",
                            },
                            delay=None,
                        )
                    ]
                )
            )
        status = service.status()
    finally:
        service.shutdown()

    assert status["config_applied"] is True
    assert status["saved_config_fingerprint"] == original_fingerprint
    assert status["active_config_fingerprint"] == original_fingerprint
    assert status["reload_error"] is None
    assert status["last_reload_at"] is None
    assert {job["id"] for job in status["jobs"]} == {"dca:XETHZEUR"}


def test_registers_enabled_cron_and_delay_only_jobs_but_not_disabled_jobs(
    tmp_path,
) -> None:
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    "XETHZEUR",
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * *",
                        "timezone": "Europe/Prague",
                    },
                ),
                _pair("XXBTZEUR", delay=2),
                _pair(
                    "XLTCZEUR",
                    schedule={"enabled": False},
                    delay=3,
                ),
                _pair(
                    "XDOGEZEUR",
                    schedule={
                        "cron": "30 10 * * *",
                        "timezone": "UTC",
                    },
                    delay=None,
                ),
            ]
        ),
    )

    try:
        status = service.status()
    finally:
        service.shutdown()

    jobs = {job["id"]: job for job in status["jobs"]}
    assert set(jobs) == {
        "dca:XETHZEUR",
        "legacy-delay:XXBTZEUR",
        "dca:XDOGEZEUR",
    }
    assert jobs["dca:XETHZEUR"]["mode"] == "cron"
    assert jobs["dca:XETHZEUR"]["cron"] == "0 9 * * *"
    assert jobs["dca:XETHZEUR"]["timezone"] == "Europe/Prague"
    assert jobs["legacy-delay:XXBTZEUR"]["mode"] == "legacy-delay"
    assert jobs["legacy-delay:XXBTZEUR"]["cron"] is None
    assert jobs["legacy-delay:XXBTZEUR"]["timezone"] == "UTC"


def test_scheduler_job_status_contains_public_shape(tmp_path) -> None:
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * *",
                        "timezone": "Europe/Prague",
                    },
                )
            ]
        ),
    )

    try:
        job = _job(service.status(), "dca:XETHZEUR")
    finally:
        service.shutdown()

    assert set(job) == {
        "id",
        "pair",
        "mode",
        "enabled",
        "cron",
        "timezone",
        "next_run_at",
        "running",
    }
    assert job["pair"] == "XETHZEUR"
    assert job["enabled"] is True
    assert job["next_run_at"] is not None
    assert job["running"] is False


def test_cron_trigger_timezone_matches_pair_schedule_timezone(tmp_path) -> None:
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * *",
                        "timezone": "Europe/Prague",
                    }
                )
            ]
        ),
    )

    try:
        job = service._scheduler.get_job("dca:XETHZEUR")
    finally:
        service.shutdown()

    assert str(job.trigger.timezone) == "Europe/Prague"


def test_legacy_delay_only_pairs_register_hourly_fallback_trigger(tmp_path) -> None:
    service = _started_service(tmp_path, _config([_pair(delay=2)]))

    try:
        trigger = service._scheduler.get_job("legacy-delay:XETHZEUR").trigger
        first = trigger.get_next_fire_time(
            None,
            datetime(2026, 7, 22, 0, 1, tzinfo=timezone.utc),
        )
        second = trigger.get_next_fire_time(first, first)
    finally:
        service.shutdown()

    assert first.isoformat() == "2026-07-22T01:00:00+00:00"
    assert second.isoformat() == "2026-07-22T02:00:00+00:00"


def test_uses_one_lock_per_pair_across_reload(tmp_path) -> None:
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * *",
                        "timezone": "UTC",
                    }
                )
            ]
        ),
    )
    original_lock = service._pair_locks["XETHZEUR"]

    try:
        service.reload(_config([_pair("XETHZEUR", delay=2)]))
        reloaded_lock = service._pair_locks["XETHZEUR"]
    finally:
        service.shutdown()

    assert reloaded_lock is original_lock


def test_manual_run_returns_conflict_when_pair_is_already_running(tmp_path) -> None:
    runner = FakeRunner()
    service = _started_service(tmp_path, _config([_pair()]), runner=runner)
    lock = service._pair_locks["XETHZEUR"]
    lock.acquire()

    try:
        result = service.run_pair_now("XETHZEUR")
    finally:
        lock.release()
        service.shutdown()

    assert result.status == "failed"
    assert result.reason == "conflict"
    assert runner.calls == []


def test_manual_run_returns_config_not_applied_when_fingerprints_differ(
    tmp_path,
    monkeypatch,
) -> None:
    runner = FakeRunner()
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * *",
                        "timezone": "UTC",
                    }
                )
            ]
        ),
        runner=runner,
    )
    original_add_job = service._scheduler.add_job

    def add_job_spy(*args, **kwargs):
        if kwargs.get("id") == "dca:XXBTZEUR":
            raise RuntimeError("new job add failed")
        return original_add_job(*args, **kwargs)

    monkeypatch.setattr(service._scheduler, "add_job", add_job_spy)

    try:
        service.reload(
            _config(
                [
                    _pair(
                        "XXBTZEUR",
                        schedule={
                            "enabled": True,
                            "cron": "30 10 * * *",
                            "timezone": "UTC",
                        },
                        delay=None,
                    )
                ]
            )
        )
        result = service.run_pair_now("XETHZEUR")
    finally:
        service.shutdown()

    assert result.status == "failed"
    assert result.reason == "config_not_applied"
    assert runner.calls == []


def test_manual_run_uses_same_active_config_snapshot_when_reload_happens(
    tmp_path,
) -> None:
    runner_calls = []
    factory_calls = []
    old_config = _config(
        [_pair("XETHZEUR", delay=1)],
        api={
            "public_key": "OLD_PUBLIC_KEY",
            "private_key": "OLD_PRIVATE_KEY",
        },
    )
    new_config = _config(
        [_pair("XETHZEUR", delay=2)],
        api={
            "public_key": "NEW_PUBLIC_KEY",
            "private_key": "NEW_PRIVATE_KEY",
        },
    )

    def factory(public_key: str, private_key: str) -> dict:
        factory_calls.append((public_key, private_key))
        service.reload(new_config)
        return {"public_key": public_key, "private_key": private_key}

    def runner(config: dict, pair: str, kraken_api: object) -> RunResult:
        runner_calls.append((config, pair, kraken_api))
        return _ok_result(pair)

    service = SchedulerService(
        _write_config(tmp_path, old_config),
        env={},
        kraken_api_factory=factory,
        runner=runner,
    )
    service.start()

    try:
        result = service.run_pair_now("XETHZEUR")
    finally:
        service.shutdown()

    assert result.status == "success"
    assert factory_calls == [("OLD_PUBLIC_KEY", "OLD_PRIVATE_KEY")]
    assert runner_calls[0][0]["api"]["public_key"] == "OLD_PUBLIC_KEY"
    assert runner_calls[0][0]["dca_pairs"][0]["delay"] == 1
    assert runner_calls[0][2] == {
        "public_key": "OLD_PUBLIC_KEY",
        "private_key": "OLD_PRIVATE_KEY",
    }


def test_reload_failure_preserves_previous_active_jobs_and_reports_mismatch(
    tmp_path,
) -> None:
    old_config = _config(
        [
            _pair(
                schedule={
                    "enabled": True,
                    "cron": "0 9 * * *",
                    "timezone": "UTC",
                }
            )
        ]
    )
    service = _started_service(tmp_path, old_config)
    old_fingerprint = fingerprint_config(old_config, {})
    new_config = _config(
        [
            _pair(
                "XXBTZEUR",
                schedule={
                    "enabled": True,
                    "cron": "0 9 L * *",
                    "timezone": "UTC",
                },
            )
        ]
    )
    new_fingerprint = fingerprint_config(new_config, {})

    try:
        status = service.reload(new_config)
    finally:
        service.shutdown()

    assert status["config_applied"] is False
    assert status["saved_config_fingerprint"] == new_fingerprint
    assert status["active_config_fingerprint"] == old_fingerprint
    assert status["reload_error"]
    assert status["last_reload_at"] is not None
    assert {job["id"] for job in status["jobs"]} == {"dca:XETHZEUR"}


def test_status_reports_config_applied_false_when_fingerprints_differ(
    tmp_path,
) -> None:
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * *",
                        "timezone": "UTC",
                    }
                )
            ]
        ),
    )

    try:
        service.reload(
            _config(
                [
                    _pair(
                        schedule={
                            "enabled": True,
                            "cron": "0 9 L * *",
                            "timezone": "UTC",
                        }
                    )
                ]
            )
        )
        status = service.status()
    finally:
        service.shutdown()

    assert status["config_applied"] is False
    assert status["reload_error"] is not None
    assert status["last_reload_at"] is not None
    assert status["saved_config_fingerprint"] != status["active_config_fingerprint"]


def test_scheduler_normalizes_unix_cron_day_of_week_before_creating_trigger(
    tmp_path,
    monkeypatch,
) -> None:
    import krakendca.scheduler as scheduler_module

    calls = []
    original = scheduler_module.normalize_cron_day_of_week

    def spy(cron: str) -> str:
        calls.append(cron)
        return original(cron)

    monkeypatch.setattr(scheduler_module, "normalize_cron_day_of_week", spy)
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * 0",
                        "timezone": "UTC",
                    },
                    delay=None,
                )
            ]
        ),
    )

    try:
        job = service._scheduler.get_job("dca:XETHZEUR")
    finally:
        service.shutdown()

    assert calls == ["0 9 * * sun"]
    assert str(job.trigger) == (
        "cron[month='*', day='*', day_of_week='sun', hour='9', minute='0']"
    )


@pytest.mark.parametrize("sunday_alias", ["0", "7"])
def test_numeric_sunday_aliases_create_same_next_run_as_sun(
    tmp_path,
    sunday_alias: str,
) -> None:
    service = _started_service(
        tmp_path,
        _config(
            [
                _pair(
                    "XZEROZEUR",
                    schedule={
                        "enabled": True,
                        "cron": f"0 9 * * {sunday_alias}",
                        "timezone": "UTC",
                    },
                    delay=None,
                ),
                _pair(
                    "XSUNZEUR",
                    schedule={
                        "enabled": True,
                        "cron": "0 9 * * sun",
                        "timezone": "UTC",
                    },
                    delay=None,
                ),
            ]
        ),
    )

    try:
        base = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
        numeric_next = service._scheduler.get_job(
            "dca:XZEROZEUR"
        ).trigger.get_next_fire_time(None, base)
        named_next = service._scheduler.get_job(
            "dca:XSUNZEUR"
        ).trigger.get_next_fire_time(None, base)
    finally:
        service.shutdown()

    assert numeric_next == named_next


def test_manual_run_uses_file_credentials_for_kraken_factory(tmp_path) -> None:
    runner = FakeRunner()
    factory = FakeKrakenFactory()
    service = _started_service(
        tmp_path,
        _config([_pair()]),
        runner=runner,
        factory=factory,
    )

    try:
        result = service.run_pair_now("XETHZEUR")
    finally:
        service.shutdown()

    assert result.status == "success"
    assert factory.calls == [("FILE_PUBLIC_KEY", "FILE_PRIVATE_KEY")]
    assert runner.calls[0][1] == "XETHZEUR"


def test_manual_run_uses_env_credentials_for_kraken_factory(tmp_path) -> None:
    runner = FakeRunner()
    factory = FakeKrakenFactory()
    service = _started_service(
        tmp_path,
        _config([_pair()], api={"public_key": None, "private_key": None}),
        runner=runner,
        factory=factory,
        env={
            "KRAKEN_API_PUBLIC_KEY": "ENV_PUBLIC_KEY",
            "KRAKEN_API_PRIVATE_KEY": "ENV_PRIVATE_KEY",
        },
    )

    try:
        result = service.run_pair_now("XETHZEUR")
    finally:
        service.shutdown()

    assert result.status == "success"
    assert factory.calls == [("ENV_PUBLIC_KEY", "ENV_PRIVATE_KEY")]
