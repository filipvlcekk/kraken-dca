"""In-process APScheduler wrapper for web-mode DCA runs."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from krakenapi import KrakenApi

from krakendca import config_store
from krakendca.runner import RunResult, run_pair
from krakendca.schedule import normalize_cron_day_of_week

logger = logging.getLogger(__name__)

_PUBLIC_ENV_VAR = "KRAKEN_API_PUBLIC_KEY"
_PRIVATE_ENV_VAR = "KRAKEN_API_PRIVATE_KEY"


@dataclass(frozen=True)
class _JobSpec:
    id: str
    pair: str
    mode: str
    enabled: bool
    cron: str | None
    timezone: str
    trigger: CronTrigger


class _ReloadAborted(RuntimeError):
    """Internal signal for lifecycle races that should not mutate active state."""


class SchedulerService:
    """Manage scheduled and manual single-pair DCA runs."""

    def __init__(
        self,
        config_path: str,
        env: Mapping[str, str] | None = None,
        kraken_api_factory: Callable[[str, str], KrakenApi] | None = None,
        runner: Callable[[dict, str, KrakenApi], RunResult] | None = None,
    ) -> None:
        self.config_path = config_path
        self._env = env
        self._kraken_api_factory = kraken_api_factory or KrakenApi
        self._runner = runner or run_pair
        self._scheduler = self._create_scheduler()
        self._lifecycle_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._pair_locks: dict[str, threading.Lock] = {}
        self._job_specs: dict[str, _JobSpec] = {}
        self._active_config: dict | None = None
        self._shutdown_requested = False

        self.saved_config_fingerprint: str | None = None
        self.active_config_fingerprint: str | None = None
        self.reload_error: str | None = None
        self.last_reload_at: str | None = None

    def start(self) -> None:
        """Load config, register active jobs, and start APScheduler."""
        with self._lifecycle_lock:
            with self._state_lock:
                config = config_store.load_config(self.config_path)
                normalized = config_store.validate_config(config, self._env)
                fingerprint = config_store.fingerprint_config(normalized, self._env)
                specs = self._build_job_specs(normalized)
                run_gate = threading.Event()
                if self._shutdown_requested:
                    self._scheduler = self._create_scheduler()
                self._add_specs_to_scheduler(
                    self._scheduler,
                    specs,
                    normalized,
                    run_gate,
                )
                self._active_config = normalized
                self._job_specs = {spec.id: spec for spec in specs}
                self.saved_config_fingerprint = fingerprint
                self.active_config_fingerprint = fingerprint
                self.reload_error = None
                self._shutdown_requested = False
                run_gate.set()
                if not self._scheduler.running:
                    self._scheduler.start()

    def shutdown(self) -> None:
        """Stop APScheduler if it is running."""
        with self._state_lock:
            self._shutdown_requested = True

        with self._lifecycle_lock:
            with self._state_lock:
                scheduler = self._scheduler
                running = scheduler.running
            if running:
                scheduler.shutdown(wait=True)

    def reload(self, config: dict) -> dict:
        """Validate config and atomically replace active scheduler jobs."""
        with self._lifecycle_lock:
            normalized = config_store.validate_config(config, self._env)
            saved_fingerprint = config_store.fingerprint_config(normalized, self._env)
            last_reload_at = _utc_now_iso()
            replacement_scheduler = None

            try:
                specs = self._build_job_specs(normalized)
                replacement_scheduler = self._create_scheduler()
                run_gate = threading.Event()
                self._add_specs_to_scheduler(
                    replacement_scheduler,
                    specs,
                    normalized,
                    run_gate,
                )
                with self._state_lock:
                    active_scheduler_running = self._scheduler.running
                    shutdown_requested = self._shutdown_requested
                if shutdown_requested:
                    raise _ReloadAborted("shutdown requested during scheduler reload")
                if active_scheduler_running:
                    replacement_scheduler.start()

                old_scheduler = None
                with self._state_lock:
                    if self._shutdown_requested:
                        raise _ReloadAborted(
                            "shutdown requested during scheduler reload"
                        )
                    old_scheduler = self._scheduler

                if old_scheduler is not None and old_scheduler.running:
                    old_scheduler.shutdown(wait=True)

                with self._state_lock:
                    if self._shutdown_requested:
                        raise _ReloadAborted(
                            "shutdown requested during scheduler reload"
                        )
                    self.saved_config_fingerprint = saved_fingerprint
                    self.last_reload_at = last_reload_at
                    self._scheduler = replacement_scheduler
                    self._active_config = normalized
                    self._job_specs = {spec.id: spec for spec in specs}
                    self.active_config_fingerprint = saved_fingerprint
                    self.reload_error = None
                    run_gate.set()
            except _ReloadAborted as exc:
                if (
                    replacement_scheduler is not None
                    and replacement_scheduler.running
                ):
                    replacement_scheduler.shutdown(wait=True)
                with self._state_lock:
                    self.saved_config_fingerprint = saved_fingerprint
                    self.last_reload_at = last_reload_at
                    self.reload_error = str(exc)
                return self.status()
            except Exception as exc:
                if (
                    replacement_scheduler is not None
                    and replacement_scheduler.running
                ):
                    replacement_scheduler.shutdown(wait=True)
                with self._state_lock:
                    self.saved_config_fingerprint = saved_fingerprint
                    self.last_reload_at = last_reload_at
                    self.reload_error = str(exc)
                logger.exception("Scheduler reload failed.")
                return self.status()

            return self.status()

    def status(self) -> dict:
        """Return scheduler state and public job metadata."""
        with self._state_lock:
            return {
                "running": self._scheduler.running,
                "config_applied": self._config_applied(),
                "saved_config_fingerprint": self.saved_config_fingerprint,
                "active_config_fingerprint": self.active_config_fingerprint,
                "reload_error": self.reload_error,
                "last_reload_at": self.last_reload_at,
                "jobs": [
                    self._job_status(spec)
                    for spec in sorted(
                        self._job_specs.values(),
                        key=lambda job_spec: job_spec.id,
                    )
                ],
            }

    def run_pair_now(self, pair: str) -> RunResult:
        """Run one pair immediately when config is applied and pair is idle."""
        with self._state_lock:
            config_applied = self._config_applied()
            active_config = self._active_config
            lock = self._lock_for_pair(pair)

        if not config_applied or active_config is None:
            return _failed_result(
                pair,
                "config_not_applied",
                "Saved config has not been applied to the scheduler.",
            )

        if not lock.acquire(blocking=False):
            return _failed_result(
                pair,
                "conflict",
                f"Pair {pair} is already running.",
            )

        try:
            return self._run_pair_with_config(pair, active_config)
        finally:
            lock.release()

    def _run_scheduled_pair(
        self,
        pair: str,
        config: dict,
        run_gate: threading.Event,
    ) -> RunResult | None:
        if not run_gate.is_set():
            logger.info("Skipping scheduled DCA run for %s; job is not active.", pair)
            return None

        lock = self._lock_for_pair(pair)
        if not lock.acquire(blocking=False):
            logger.warning("Skipping scheduled DCA run for %s; pair is busy.", pair)
            return None

        try:
            return self._run_pair_with_config(pair, config)
        finally:
            lock.release()

    def _run_pair_with_active_config(self, pair: str) -> RunResult:
        with self._state_lock:
            active_config = self._active_config

        if active_config is None:
            return _failed_result(
                pair,
                "config_not_loaded",
                "Scheduler config has not been loaded.",
            )

        return self._run_pair_with_config(pair, active_config)

    def _run_pair_with_config(self, pair: str, config: dict) -> RunResult:
        public_key, private_key = self._effective_api_keys(config)
        kraken_api = self._kraken_api_factory(public_key, private_key)
        return self._runner(config, pair, kraken_api)

    def _build_job_specs(self, config: dict) -> list[_JobSpec]:
        specs = []
        for dca_pair in config.get("dca_pairs") or []:
            pair = dca_pair.get("pair")
            schedule = dca_pair.get("schedule")
            if schedule is not None:
                if not schedule.get("enabled", True):
                    continue
                cron = normalize_cron_day_of_week(schedule["cron"])
                schedule_timezone = schedule["timezone"]
                specs.append(
                    _JobSpec(
                        id=f"dca:{pair}",
                        pair=pair,
                        mode="cron",
                        enabled=True,
                        cron=cron,
                        timezone=schedule_timezone,
                        trigger=CronTrigger.from_crontab(
                            cron,
                            timezone=schedule_timezone,
                        ),
                    )
                )
                self._lock_for_pair(pair)
                continue

            if "delay" in dca_pair:
                specs.append(
                    _JobSpec(
                        id=f"legacy-delay:{pair}",
                        pair=pair,
                        mode="legacy-delay",
                        enabled=True,
                        cron=None,
                        timezone="UTC",
                        trigger=CronTrigger(minute=0, timezone="UTC"),
                    )
                )
                self._lock_for_pair(pair)
        return specs

    def _add_specs_to_scheduler(
        self,
        scheduler: BackgroundScheduler,
        specs: list[_JobSpec],
        config: dict,
        run_gate: threading.Event,
    ) -> None:
        for spec in specs:
            scheduler.add_job(
                self._run_scheduled_pair,
                trigger=spec.trigger,
                args=[spec.pair, config, run_gate],
                id=spec.id,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
                replace_existing=True,
            )

    def _job_status(self, spec: _JobSpec) -> dict:
        job = self._scheduler.get_job(spec.id)
        next_run_at = None
        if job is not None and job.next_run_time is not None:
            next_run_at = job.next_run_time.isoformat()

        return {
            "id": spec.id,
            "pair": spec.pair,
            "mode": spec.mode,
            "enabled": spec.enabled,
            "cron": spec.cron,
            "timezone": spec.timezone,
            "next_run_at": next_run_at,
            "running": self._lock_for_pair(spec.pair).locked(),
        }

    def _lock_for_pair(self, pair: str) -> threading.Lock:
        with self._state_lock:
            if pair not in self._pair_locks:
                self._pair_locks[pair] = threading.Lock()
            return self._pair_locks[pair]

    def _effective_api_keys(self, config: dict) -> tuple[str, str]:
        api = config.get("api") or {}
        public_key = api.get("public_key")
        if public_key is None:
            public_key = self._env_value(_PUBLIC_ENV_VAR)
        private_key = api.get("private_key")
        if private_key is None:
            private_key = self._env_value(_PRIVATE_ENV_VAR)
        return public_key, private_key

    def _env_value(self, key: str) -> str | None:
        if self._env is None:
            return os.environ.get(key)
        return self._env.get(key)

    def _create_scheduler(self) -> BackgroundScheduler:
        return BackgroundScheduler(timezone="UTC")

    def _config_applied(self) -> bool:
        return (
            self.reload_error is None
            and self.saved_config_fingerprint is not None
            and self.active_config_fingerprint is not None
            and self.saved_config_fingerprint
            == self.active_config_fingerprint
        )


def _failed_result(pair: str, reason: str, message: str) -> RunResult:
    now = datetime.now(timezone.utc)
    return RunResult(
        pair=pair,
        status="failed",
        reason=reason,
        started_at=now,
        finished_at=now,
        order_txid=None,
        message=message,
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
