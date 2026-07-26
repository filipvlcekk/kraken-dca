# Web UI Cron Scheduler Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Docker-first Vue web UI and FastAPI backend that edits `config.yaml`, authenticates with `WEB_UI_PASSWORD`, and runs per-pair DCA schedules inside the container.

**Architecture:** Add focused Python modules for config persistence, schedule validation, authenticated API routes, DCA run orchestration, and APScheduler job management. Add a Vue 3 + Vite frontend under `frontend/` and serve its production build from FastAPI. Keep the existing CLI path compatible by routing config validation through the new shared config store.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, APScheduler, croniter, PyYAML, pytest, Vue 3, Vite, TypeScript, cron-parser, cronstrue.

---

**Spec:** `docs/superpowers/specs/2026-07-21-web-ui-cron-scheduler-design.md`

**Implementation Notes:**

- Use @superpowers:test-driven-development for implementation tasks.
- Keep each commit small and runnable.
- Do not remove legacy `delay` support.
- Run backend tests through commands like `python -m pytest tests/test_config.py -v` because this environment may not expose `pytest` as a shell command.
- If dependencies are missing locally, install them in the project environment before running full tests.

## Chunk 1: Backend Foundation

### Task 1: Dependencies And Test Fixtures

**Files:**
- Modify: `requirements.txt`
- Create: `tests/test_requirements.py`
- Create: `tests/fixtures/config_schedule.yaml`
- Create: `tests/fixtures/config_env_credentials.yaml`

- [ ] **Step 1: Add dependency declaration test**

Create `tests/test_requirements.py` with a test that asserts `requirements.txt` declares required backend web dependencies:

```python
from pathlib import Path


def test_web_scheduler_dependencies_are_declared() -> None:
    requirements = Path("requirements.txt").read_text()
    for package in (
        "APScheduler==",
        "croniter==",
        "fastapi==",
        "httpx==",
        "itsdangerous==",
        "uvicorn==",
    ):
        assert package in requirements
```

- [ ] **Step 2: Run dependency test and verify failure before install**

Run: `python -m pytest tests/test_requirements.py -v`

Expected: FAIL until new dependencies are listed.

- [ ] **Step 3: Add backend dependencies**

Add pinned dependencies to `requirements.txt`:

```text
APScheduler==3.10.4
croniter==6.0.0
fastapi==0.115.6
httpx==0.28.1
itsdangerous==2.2.0
uvicorn==0.34.0
```

- [ ] **Step 4: Install backend dependencies**

Run: `python -m pip install -r requirements.txt`

Expected: PASS and installs FastAPI, Uvicorn, APScheduler, croniter, httpx, and itsdangerous.

- [ ] **Step 5: Add fixture configs**

Create `tests/fixtures/config_schedule.yaml` with one cron pair and one disabled pair:

```yaml
api:
  public_key: "KRAKEN_API_PUBLIC_KEY"
  private_key: "KRAKEN_API_PRIVATE_KEY"

dca_pairs:
  - pair: "XETHZEUR"
    amount: 15
    schedule:
      enabled: true
      cron: "0 9 * * *"
      timezone: "Europe/Prague"
    min_order_interval_minutes: 30
    limit_factor: 0.985
    max_price: 2900.10
  - pair: "XXBTZEUR"
    amount: 20
    schedule:
      enabled: false
    delay: 3
```

Create `tests/fixtures/config_env_credentials.yaml`:

```yaml
dca_pairs:
  - pair: "XETHZEUR"
    delay: 1
    amount: 15
```

- [ ] **Step 6: Verify requirement declaration and existing config tests pass**

Run: `python -m pytest tests/test_requirements.py -v`

Expected: PASS.

Run: `python -m pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt tests/test_requirements.py tests/fixtures/config_schedule.yaml tests/fixtures/config_env_credentials.yaml
git commit -m "test: add web scheduler dependency fixtures"
```

### Task 2: Schedule Validation Module

**Files:**
- Create: `krakendca/schedule.py`
- Create: `tests/test_schedule.py`

- [ ] **Step 1: Write failing schedule validation tests**

Create tests for:

- Valid five-field cron.
- Reject six-field cron.
- Reject seven-field cron.
- Reject Quartz-style cron with `?`.
- Enabled schedules with omitted `cron` are invalid.
- Reject invalid timezone.
- Default timezone is `UTC`.
- Unix day-of-week `0` and `7` both normalize to `sun`.
- Unix day-of-week `1` through `6` normalize to `mon` through `sat`.
- Day-of-week lists and ranges normalize token-by-token, e.g. `1,3,5` becomes `mon,wed,fri` and `1-5` becomes `mon-fri`.
- Weekday names `sun` through `sat` validate and normalize to lowercase.
- Omitted `enabled` is treated as enabled.
- Disabled schedules do not require cron or timezone.
- Disabled schedules still reject invalid provided cron or timezone.
- Preset minute values are exactly `[5, 10, 15, 20, 30]`.
- Preset hour values are exactly `[1, 2, 3, 4, 6, 8, 12, 24]`.
- Monthly preset helper rejects day 29, 30, and 31.
- `build_monthly_cron(day=28, hour=9, minute=0)` returns `0 9 28 * *`.
- `next_run_times("0 9 * * *", "Europe/Prague", now="2026-07-21T06:00:00Z")` returns timezone-aware ISO timestamps starting with `2026-07-21T09:00:00+02:00`.
- `next_run_times("0 9 * * *", "UTC", now="2026-07-21T06:00:00Z")` starts with `2026-07-21T09:00:00+00:00`.

Example:

```python
from krakendca.schedule import validate_schedule


def test_validate_schedule_defaults_timezone_to_utc() -> None:
    schedule = validate_schedule({"enabled": True, "cron": "0 9 * * *"})
    assert schedule["timezone"] == "UTC"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_schedule.py -v`

Expected: FAIL with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: Implement schedule helpers**

Implement in `krakendca/schedule.py`:

- `MINUTE_PRESET_VALUES = (5, 10, 15, 20, 30)`
- `HOUR_PRESET_VALUES = (1, 2, 3, 4, 6, 8, 12, 24)`
- `validate_schedule(schedule: dict) -> dict`
- `normalize_cron_day_of_week(cron: str) -> str`
- `next_run_times(cron: str, timezone: str, count: int = 3, now: str | None = None) -> list[str]`
- `build_daily_cron(hour: int, minute: int) -> str`
- `build_weekly_cron(day_name: str, hour: int, minute: int) -> str`
- `build_monthly_cron(day: int, hour: int, minute: int) -> str`
- `build_every_minutes_cron(minutes: int) -> str`
- `build_every_hours_cron(hours: int) -> str`

Use `zoneinfo.ZoneInfo` for timezone validation and `croniter` for cron validation and next-run calculation.

Preset helper contracts:

- `build_daily_cron(9, 0)` returns `0 9 * * *`.
- `build_weekly_cron("mon", 9, 0)` returns `0 9 * * mon`.
- `build_monthly_cron(28, 9, 0)` returns `0 9 28 * *`.
- `build_every_minutes_cron(15)` returns `*/15 * * * *`.
- `build_every_hours_cron(6)` returns `0 */6 * * *`.
- Invalid preset values raise `ValueError` with a field-specific message.
- `normalize_cron_day_of_week("0 9 * * 0")` returns `0 9 * * sun`.
- `normalize_cron_day_of_week("0 9 * * 7")` returns `0 9 * * sun`.
- `normalize_cron_day_of_week("0 9 * * 1-5")` returns `0 9 * * mon-fri`.
- `normalize_cron_day_of_week("0 9 * * 1,3,5")` returns `0 9 * * mon,wed,fri`.

- [ ] **Step 4: Run schedule tests**

Run: `python -m pytest tests/test_schedule.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add krakendca/schedule.py tests/test_schedule.py
git commit -m "feat: add cron schedule validation"
```

### Task 3: Shared Config Store And Legacy Config Wrapper

**Files:**
- Create: `krakendca/config_store.py`
- Modify: `krakendca/config.py`
- Modify: `tests/test_config.py`
- Create: `tests/test_config_store.py`

- [ ] **Step 1: Write failing config store tests**

Cover:

- Load legacy `delay` config.
- Load schedule config.
- Reject duplicate pair names.
- Reject invalid cron.
- `schedule.enabled: false` takes precedence over `delay`.
- `min_order_interval_minutes` accepts `0` and `525600`.
- `min_order_interval_minutes` rejects negative values, non-integers, and values above `525600`.
- Omitted `min_order_interval_minutes` normalizes to `30`.
- Validation errors expose field paths such as `dca_pairs.0.schedule.cron`.
- Redact file credentials using `__KRADCA_SECRET_REDACTED__`.
- Preserve redacted credentials on save.
- Replace redacted credentials when submitted values are new non-redacted strings.
- Return secret metadata shape with `secrets.public_key/private_key.configured` and `source`.
- `null` credentials are omitted from written YAML and may use env fallback.
- Atomic save creates backup names like `config.yaml.bak.20260721T120000Z`.
- Backup retention keeps only the 10 newest `config.yaml.bak.*` files.
- Config fingerprint redacts credential values.
- Config fingerprint uses canonical normalized config after defaults are applied.
- Config fingerprint includes credential source and presence.
- Config fingerprint does not change when only secret values change and source/presence stay the same.
- Empty string credentials are invalid.
- CLI rejects enabled cron-scheduled pairs with a clear web-mode error.
- CLI skips `schedule.enabled: false` pairs.
- CLI treats `schedule.enabled: false` as disabled even when `delay` is present.
- CLI uses enabled `schedule` over `delay` and emits the web-mode error.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_config_store.py tests/test_config.py -v`

Expected: FAIL because `config_store` is missing and `Config` still owns validation.

- [ ] **Step 3: Implement config store**

Implement `krakendca/config_store.py` with focused functions/classes:

- Constant: `REDACTED_SECRET = "__KRADCA_SECRET_REDACTED__"`.
- Function: `load_config(path: str) -> dict`.
- Function: `validate_config(config: dict, env: dict | None = None) -> dict`.
- Function: `redact_config(config: dict, env: dict | None = None) -> dict` returning `{"config": redacted_config, "secrets": secret_metadata}`.
- Function: `merge_redacted_config(submitted: dict, existing: dict, env: dict | None = None) -> dict`.
- Function: `save_config(path: str, submitted: dict, env: dict | None = None) -> dict`.
- Function: `fingerprint_config(config: dict, env: dict | None = None) -> str`.
- Function: `get_cli_dca_pairs(config: dict) -> list[dict]`.
- Exception: `ConfigValidationError(message: str, fields: dict[str, str])`.

Use `os.replace` for atomic replacement and keep the 10 newest backups.

Validation contract:

- `validate_config()` returns normalized config with defaults applied.
- `validate_config()` raises `ConfigValidationError` for field-level validation errors.
- Pair-level validation owns `min_order_interval_minutes`; `schedule.validate_schedule()` owns only cron, timezone, and schedule shape.
- `redact_config()` is the only function that builds secret metadata for API responses.

- [ ] **Step 4: Refactor `Config` to delegate validation**

Update `krakendca/config.py` so `Config.__init__` calls `config_store.load_config()` and `config_store.validate_config()`, then assigns:

- `api_public_key`
- `api_private_key`
- `dca_pairs`

Preserve existing error messages asserted by current tests.

Use `get_cli_dca_pairs(config: dict) -> list[dict]` in `Config.__init__` for `Config.dca_pairs`:

- Delay-only pairs remain executable.
- Disabled scheduled pairs are ignored by CLI initialization.
- Enabled scheduled pairs raise a clear error that cron schedules require web mode.

- [ ] **Step 5: Run config tests**

Run: `python -m pytest tests/test_config_store.py tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add krakendca/config_store.py krakendca/config.py tests/test_config.py tests/test_config_store.py
git commit -m "feat: add shared config store"
```

## Chunk 2: Runtime, Scheduler, And API

### Task 4: Runner And Cron-Safe Duplicate Protection

**Files:**
- Create: `krakendca/runner.py`
- Modify: `krakendca/dca.py`
- Create: `tests/test_runner.py`
- Modify: `tests/test_dca.py`

- [ ] **Step 1: Write failing runner tests**

Cover:

- `RunResult` returns `completed`, `skipped`, and `failed` shapes.
- Manual and scheduled runs use the same duplicate-order guard.
- `min_order_interval_minutes=0` skips closed-order lookback.
- Default `min_order_interval_minutes` is 30.
- `ignore_differing_orders` applies to open and closed order checks.
- Unwritable `orders.csv` before a run returns a clear persistence failure before order submission when detectible.
- Scheduled runs log unwritable order history failures clearly.
- History persistence failure after successful order submission returns `history_persistence_failed`.
- Insufficient funds returns a `failed` result with reason `insufficient_funds`.
- Max-price guard returns a `skipped` result with reason `max_price_exceeded`.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_runner.py tests/test_dca.py -v`

Expected: FAIL with missing `krakendca.runner` or missing DCA safety hooks.

- [ ] **Step 3: Add runner result model**

Implement `krakendca/runner.py` with:

```python
@dataclass
class RunResult:
    pair: str
    status: str
    reason: str | None
    started_at: datetime
    finished_at: datetime | None
    order_txid: str | None
    message: str
```

Add `run_pair(config: dict, pair_name: str, ka: KrakenApi) -> RunResult`.

Runner contract:

- `run_pair()` finds exactly one pair config by `pair_name`; missing pairs return `failed` with reason `pair_not_found`.
- It fetches Kraken asset pairs once and builds `Pair` with `Pair.get_pair_from_kraken()`.
- It constructs `DCA` with pair amount, `limit_factor`, `max_price`, `ignore_differing_orders`, `orders_filepath`, and either legacy `delay` or cron `min_order_interval_minutes`.
- It passes cron vs legacy safety mode explicitly so `delay` is not used to block valid cron schedules.
- It returns `order_txid` from the submitted `Order` when an order is created.
- It maps duplicate-order and max-price guards to `skipped` results.
- It maps pre-submit order-history write failure to `failed` with reason `history_unwritable`.
- It maps insufficient funds to `failed` with reason `insufficient_funds`.
- It maps Kraken/network exceptions to `failed` with reason `kraken_error`.
- It maps order-history persistence failure after submission to `failed` with reason `history_persistence_failed` and a warning message that the order may already have been placed.

Required `DCA` changes:

- `handle_dca_logic()` should return a typed outcome object or raise typed exceptions that `runner` can map without parsing log text.
- Completed runs must expose the submitted order txid.
- Duplicate-order guard returns or raises reason `duplicate_order`.
- Max-price guard returns or raises reason `max_price_exceeded`.
- Balance failures raise or return reason `insufficient_funds`.
- Order-history failures before submission use reason `history_unwritable`.
- Order-history failures after submission use reason `history_persistence_failed`.

- [ ] **Step 4: Update DCA for min interval safety**

Add optional `min_order_interval_minutes` to `DCA.__init__`.

Keep existing `delay` behavior for legacy mode. Add a separate closed-order lookback path for cron mode using UTC timestamps and minutes.

- [ ] **Step 5: Run runner and DCA tests**

Run: `python -m pytest tests/test_runner.py tests/test_dca.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add krakendca/runner.py krakendca/dca.py tests/test_runner.py tests/test_dca.py
git commit -m "feat: add DCA run result orchestration"
```

### Task 5: Scheduler Wrapper

**Files:**
- Create: `krakendca/scheduler.py`
- Create: `tests/test_scheduler.py`

- [x] **Step 1: Write failing scheduler tests**

Cover:

- Registers job IDs using the `dca:XETHZEUR` pattern for enabled schedules.
- Registers job IDs using the `legacy-delay:XETHZEUR` pattern for delay-only pairs.
- Does not register disabled schedule jobs.
- Uses one lock per pair.
- Manual run returns conflict when pair is already running.
- Manual run returns `config_not_applied` when saved and active config fingerprints differ.
- Reload failure preserves previous active jobs.
- `config_applied` is false when saved fingerprint differs from active fingerprint.
- Reload mismatch status includes `reload_error`, `last_reload_at`, `saved_config_fingerprint`, and `active_config_fingerprint`.
- Scheduler job status contains `id`, `pair`, `mode`, `enabled`, `cron`, `timezone`, `next_run_at`, and `running`.
- Cron trigger timezone matches the pair schedule timezone.
- Legacy delay-only pairs register an hourly fallback trigger.
- `schedule.enabled: false` with `delay` does not register a scheduler job.
- Omitted `schedule.enabled` is treated as enabled for scheduler registration.
- Scheduler normalizes Unix cron day-of-week before creating APScheduler triggers.
- A schedule using `0` or `7` for Sunday creates the same next run as `sun`.

- [x] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_scheduler.py -v`

Expected: FAIL with missing `krakendca.scheduler`.

- [x] **Step 3: Implement scheduler service**

Implement `krakendca/scheduler.py` with a `SchedulerService` class.

Constructor contract:

```python
SchedulerService(
    config_path: str,
    env: Mapping[str, str] | None = None,
    kraken_api_factory: Callable[[str, str], KrakenApi] | None = None,
    runner: Callable[[dict, str, KrakenApi], RunResult] | None = None,
)
```

State contract:

- Tracks `saved_config_fingerprint`.
- Tracks `active_config_fingerprint`.
- Tracks `reload_error`.
- Tracks `last_reload_at`.
- Tracks per-pair locks.
- Stores normalized active config used by scheduled and manual runs.
- On successful startup load, sets saved and active fingerprints to the loaded config fingerprint.
- On `reload(config)` success, replaces jobs atomically and updates active fingerprint to saved fingerprint.
- On `reload(config)` failure, keeps prior jobs and active fingerprint, updates saved fingerprint, and stores `reload_error`.
- `POST /api/scheduler/reload` reloads from saved `config.yaml`, not from client-submitted payload.

Expose these methods:

- `start(self) -> None`.
- `shutdown(self) -> None`.
- `reload(self, config: dict) -> dict`.
- `status(self) -> dict`.
- `run_pair_now(self, pair: str) -> RunResult`.

Use `BackgroundScheduler`, `max_instances=1`, coalescing, and 5 minute misfire grace. Always call `normalize_cron_day_of_week()` before converting cron config into an APScheduler trigger. `run_pair_now()` must return a conflict result without running DCA when `saved_config_fingerprint != active_config_fingerprint`.

Job status contract:

```json
{
  "id": "dca:XETHZEUR",
  "pair": "XETHZEUR",
  "mode": "cron",
  "enabled": true,
  "cron": "0 9 * * *",
  "timezone": "Europe/Prague",
  "next_run_at": "2026-07-22T09:00:00+02:00",
  "running": false
}
```

- [x] **Step 4: Run scheduler tests**

Run: `python -m pytest tests/test_scheduler.py -v`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add krakendca/scheduler.py tests/test_scheduler.py
git commit -m "feat: add in-process DCA scheduler"
```

### Task 6: FastAPI Web App, Auth, And API Routes

**Files:**
- Create: `krakendca/web/__init__.py`
- Create: `krakendca/web/app.py`
- Create: `krakendca/web/auth.py`
- Create: `krakendca/web/routes_config.py`
- Create: `krakendca/web/routes_scheduler.py`
- Create: `krakendca/web/routes_session.py`
- Create: `krakendca/web/schemas.py`
- Create: `krakendca/web/static.py`
- Create: `tests/test_web_auth.py`
- Create: `tests/test_web_api.py`

- [x] **Step 1: Write failing auth tests**

Cover:

- Missing `WEB_UI_PASSWORD` fails app startup.
- Login succeeds with correct password and returns `csrf_token`.
- Login fails with wrong password.
- `GET /api/session` restores auth and returns a fresh CSRF token after login.
- Session cookie has `HttpOnly` and `SameSite=Strict`.
- Session cookie expiry is enforced at 12 hours of inactivity.
- `WEB_UI_SESSION_SECRET` signs sessions when set.
- `WEB_UI_COOKIE_SECURE=true` sets the cookie `Secure` attribute.
- `WEB_UI_COOKIE_SECURE` unset keeps `Secure` disabled for local Docker HTTP.
- Unsafe methods reject missing or invalid `X-CSRF-Token`.
- Logout clears session.

- [x] **Step 2: Write failing API tests**

Cover:

- `GET /api/config` requires auth.
- `GET /api/config` redacts credentials.
- `GET /api/config` returns `secrets.public_key/private_key.configured` and `source`.
- `GET /api/config` returns `null` file credential values when credentials are provided from env.
- Every API success response follows `{"ok": true, "data": {"field": "value"}}` with endpoint-specific data.
- Every API error response follows `{"ok": false, "error": {"code": "error_code", "message": "Human-readable message"}}`.
- Unauthenticated API calls return `401`.
- Authenticated but forbidden actions return `403`.
- Already-running manual pair runs return `409`.
- Domain failures such as insufficient funds return `400`.
- Kraken/network failures return `502`.
- Unexpected persistence or scheduler failures return `500`.
- `PUT /api/config` validates and saves config.
- `PUT /api/config` returns `400` field errors for invalid config.
- `PUT /api/config` reload failure response includes `config_saved: true` and `scheduler_reloaded: false`.
- Missing `config.yaml` setup mode returns `config_valid: false` and no jobs.
- Semantic-invalid config degraded mode returns redacted structured config and validation errors.
- `GET /api/scheduler` returns job state.
- `GET /api/scheduler` returns `config_applied: false` and fingerprints on reload mismatch.
- `POST /api/scheduler/reload` returns scheduler status.
- `POST /api/pairs/{pair}/run` maps `completed`, `skipped`, `config_not_applied`, and Kraken failure results.
- Malformed YAML degraded mode returns `raw_yaml: null`.
- Static UI routes require auth except login route and assets needed to render login.
- `GET /api/session` authenticated success returns `{"ok": true, "data": {"authenticated": true, "csrf_token": "non-empty-token"}}`.
- `POST /api/session` success returns `{"ok": true, "data": {"authenticated": true, "csrf_token": "non-empty-token"}}`.
- `DELETE /api/session` success returns `{"ok": true, "data": {"authenticated": false}}`.
- `GET /api/config` success returns `{"ok": true, "data": {"config": {}, "secrets": {}, "config_valid": true, "validation_errors": []}}`.
- `PUT /api/config` success returns `{"ok": true, "data": {"config": {}, "scheduler": {"config_applied": true}}}`.
- `PUT /api/config` validation failure returns `400` with field errors.
- `PUT /api/config` reload failure returns `500` with `{"config_saved": true, "scheduler_reloaded": false}` in error details.
- `GET /api/scheduler` success returns `{"ok": true, "data": {"running": true, "config_applied": true, "jobs": [], "last_reload_at": "iso-or-null"}}`.
- `POST /api/scheduler/reload` success returns `{"ok": true, "data": {"scheduler": {}}}`.
- Manual run completed returns `{"ok": true, "data": {"pair": "XETHZEUR", "status": "completed"}}`.
- Manual run skipped returns `{"ok": true, "data": {"pair": "XETHZEUR", "status": "skipped", "reason": "duplicate_order"}}`.
- Manual run `config_not_applied` returns `409` with code `config_not_applied`.
- Manual run `history_unwritable` returns `500` with code `history_unwritable`.
- Manual run `history_persistence_failed` returns `500` with code `history_persistence_failed`.
- Manual run `kraken_error` returns `502` with code `kraken_error`.

- [x] **Step 3: Run web tests and verify failure**

Run: `python -m pytest tests/test_web_auth.py tests/test_web_api.py -v`

Expected: FAIL with missing `krakendca.web`.

- [x] **Step 4: Implement auth module**

Use `itsdangerous.URLSafeTimedSerializer` for signed cookies and `secrets.compare_digest` for password checks. Keep cookie name `kraken_dca_session`. Return a fresh CSRF token from both `POST /api/session` and `GET /api/session`. Include cookie attribute handling for `HttpOnly`, `SameSite=Strict`, 12-hour max age, optional `Secure`, and optional `WEB_UI_SESSION_SECRET`.

- [x] **Step 5: Implement response schemas and error mapping**

Implement `krakendca/web/schemas.py` with helpers for:

- Success response wrapping.
- Error response wrapping.
- Field validation error payloads.
- `RunResult` to HTTP status mapping.

- [x] **Step 6: Implement app factory and lifespan**

Implement `create_app(config_path: str = "/app/config.yaml", static_dir: str = "/app/frontend") -> FastAPI`.

Also expose a module-level app for Docker:

```python
app = create_app()
```

Use FastAPI lifespan startup/shutdown hooks:

- On startup, require `WEB_UI_PASSWORD`.
- Load config through `config_store`.
- Enter setup mode for missing config.
- Enter degraded mode for invalid YAML or semantic validation errors.
- Start `SchedulerService` only when config is valid.
- On shutdown, stop `SchedulerService` cleanly.

- [x] **Step 7: Implement session route module**

Add `krakendca/web/routes_session.py` with `GET /api/session`, `POST /api/session`, and `DELETE /api/session` using `krakendca.web.auth`.

- [x] **Step 8: Implement config route module**

Add `krakendca/web/routes_config.py` with `GET /api/config` and `PUT /api/config` using `config_store`. Include setup mode, semantic-invalid degraded mode, malformed YAML degraded mode, redaction, secret metadata, env credential `null` values, save, and reload-failure response handling.

- [x] **Step 9: Implement scheduler and manual-run route module**

Add `krakendca/web/routes_scheduler.py` with `GET /api/scheduler`, `POST /api/scheduler/reload`, and `POST /api/pairs/{pair}/run`. Map scheduler conflicts and runner outcomes to the documented status codes.

- [x] **Step 10: Implement static frontend serving module**

Add `krakendca/web/static.py`. Mount static frontend assets only after API routes. Return `index.html` for authenticated SPA routes and login shell for unauthenticated users.

- [x] **Step 11: Run web tests**

Run: `python -m pytest tests/test_web_auth.py tests/test_web_api.py -v`

Expected: PASS.

- [x] **Step 12: Commit**

```bash
git add krakendca/web tests/test_web_auth.py tests/test_web_api.py
git commit -m "feat: add authenticated web API"
```

## Chunk 3: Frontend

### Task 7: Frontend Scaffold And Test Harness

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/style.css`

- [x] **Step 1: Scaffold Vue 3 + Vite + TypeScript**

Use pinned Vite Vue template.

Run: `npm create vite@5.5.5 frontend -- --template vue-ts`

Run: `npm --prefix frontend install vue@3.5.13 cron-parser@5.3.1 cronstrue@2.59.0`

Run: `npm --prefix frontend install --save-dev @vitejs/plugin-vue@5.2.1 vite@6.0.7 typescript@5.7.2 vitest@2.1.8 vue-tsc@2.2.0 @vue/test-utils@2.4.6 jsdom@25.0.1`

Pin generated package versions in `frontend/package-lock.json`.

- [x] **Step 2: Configure frontend test scripts**

Ensure `frontend/package.json` contains:

```json
{
  "scripts": {
    "test": "vitest",
    "build": "vue-tsc -b && vite build"
  }
}
```

Configure Vitest with jsdom in `frontend/vite.config.ts`.

- [x] **Step 3: Run empty frontend checks**

Run: `npm --prefix frontend test -- --run`

Expected: PASS with the generated starter tests or no test files.

Run: `npm --prefix frontend run build`

Expected: PASS and output in `frontend/dist`.

- [x] **Step 4: Commit**

```bash
git add frontend
git commit -m "chore: scaffold Vue frontend"
```

### Task 8: Frontend API Client And Schedule Helpers

**Files:**
- Create: `frontend/src/api.ts`
- Create: `frontend/src/schedule.ts`
- Create: `frontend/src/__tests__/schedule.test.ts`
- Create: `frontend/src/__tests__/api.test.ts`

- [ ] **Step 1: Write failing API and schedule tests**

Cover:

- API client attaches `X-CSRF-Token` on unsafe requests.
- API client exposes session restore, login, logout, config load/save, scheduler reload, scheduler status, and manual run functions.
- Config save sends expected payload and preserves redacted secret sentinel values.
- Env-backed credentials round-trip as omitted or `null` and redacted sentinels are never written literally as new secret values.
- Cron-managed pairs write explicit `schedule.enabled`.
- Preset minute values are `[5, 10, 15, 20, 30]`.
- Preset hour values are `[1, 2, 3, 4, 6, 8, 12, 24]`.
- Daily preset generates `0 9 * * *`.
- Weekly preset uses weekday names.
- Every-15-minutes preset generates `*/15 * * * *`.
- Every-6-hours preset generates `0 */6 * * *`.
- Monthly day 28 preset generates `0 9 28 * *`.
- Advanced cron validation rejects six-field cron.
- Monthly preset rejects days above 28.
- Schedule summary renders a human-readable cron description.
- Timezone-aware next-run preview renders the next three run times.
- Next-run preview changes when timezone changes.

Run: `npm --prefix frontend test -- --run`

Expected: FAIL until `api.ts` and `schedule.ts` are implemented.

- [ ] **Step 2: Implement API client**

Define response types matching backend `ok/data/error` shapes. Add typed API helpers for session restore, login, logout, config load/save, scheduler reload, scheduler status, and manual run.

Export these TypeScript types and functions:

- `type ApiSuccess<T>`.
- `type ApiError`.
- `type ApiResponse<T>`.
- `type AppConfig`.
- `type DcaPairConfig`.
- `type SecretMetadata`.
- `type SchedulerStatus`.
- `type RunResult`.
- `restoreSession()`.
- `login(password: string)`.
- `logout(csrfToken: string)`.
- `loadConfig()`.
- `saveConfig(config: AppConfig, csrfToken: string)`.
- `loadSchedulerStatus()`.
- `reloadScheduler(csrfToken: string)`.
- `runPairNow(pair: string, csrfToken: string)`.

- [ ] **Step 3: Implement schedule helpers**

Implement `frontend/src/schedule.ts`:

- Preset value constants.
- Preset-to-cron builders.
- Advanced cron validation.
- Human-readable schedule summary through `cronstrue`.
- Timezone-aware next-run preview through `cron-parser`.

Export these functions:

- `buildDailyCron(hour: number, minute: number): string`.
- `buildWeeklyCron(dayName: string, hour: number, minute: number): string`.
- `buildMonthlyCron(day: number, hour: number, minute: number): string`.
- `buildEveryMinutesCron(minutes: number): string`.
- `buildEveryHoursCron(hours: number): string`.
- `validateCron(cron: string): string | null`.
- `describeCron(cron: string): string`.
- `previewNextRuns(cron: string, timezone: string, count?: number): string[]`.
- `cronRunsMoreFrequentlyThan(cron: string, timezone: string, minIntervalMinutes: number): boolean`.

- [ ] **Step 4: Run API and schedule tests**

Run: `npm --prefix frontend test -- --run frontend/src/__tests__/api.test.ts frontend/src/__tests__/schedule.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/authStore.ts frontend/src/schedule.ts frontend/src/__tests__/api.test.ts frontend/src/__tests__/schedule.test.ts
git commit -m "feat: add frontend API and schedule helpers"
```

### Task 9: Frontend Config And Credential Editing

**Files:**
- Create: `frontend/src/configStore.ts`
- Create: `frontend/src/components/CredentialEditor.vue`
- Create: `frontend/src/components/ConfigWarnings.vue`
- Create: `frontend/src/__tests__/credentialEditor.test.ts`
- Create: `frontend/src/__tests__/configStore.test.ts`
- Create: `frontend/src/__tests__/configWarnings.test.ts`

- [ ] **Step 1: Write failing config and credential tests**

Cover:

- Config store loads config and secret metadata.
- Config store tracks dirty state and field validation errors.
- Config store save sends payloads shaped like `{"config": {"dca_pairs": []}}`.
- Config store ensures cron-managed pairs include explicit `schedule.enabled`.
- Config store add-pair creates a new pair with `schedule.enabled: true`, default cron, default timezone, amount, and `min_order_interval_minutes: 30`.
- Config store remove-pair removes the pair from the full config save payload.
- Credential editor shows file credentials as redacted.
- Credential editor shows env credential source/status.
- Credential editor requires explicit replacement before sending a new secret.
- Credential editor can clear file credentials so env credentials remain omitted from saved YAML.
- Credential editor never emits the redacted sentinel as a replacement secret.
- Persistence warnings render config and order-history write failures.
- Setup/degraded mode renders corrective config state.

Run: `npm --prefix frontend test -- --run`

Expected: FAIL until config store and components exist.

- [ ] **Step 2: Implement config store**

Implement `configStore.ts` for config loading, editing, add pair, remove pair, validation errors, dirty state, redacted credential replacement state, env-backed credential omission, explicit `schedule.enabled`, and save lifecycle.

- [ ] **Step 3: Implement credential editor**

Implement `CredentialEditor.vue` props and events:

- Props: `apiConfig`, `secrets`.
- Emits: `replace-public-key`, `replace-private-key`, `clear-file-public-key`, `clear-file-private-key`.
- Behavior: display source/status, keep redacted values untouched until explicit replacement.

- [ ] **Step 4: Implement config warnings**

Implement `ConfigWarnings.vue` props:

- `configValid`.
- `validationErrors`.
- `configPersistenceError`.
- `orderHistoryWarning`.
- `setupMode`.

- [ ] **Step 5: Run config and credential tests**

Run: `npm --prefix frontend test -- --run frontend/src/__tests__/configStore.test.ts frontend/src/__tests__/credentialEditor.test.ts frontend/src/__tests__/configWarnings.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/configStore.ts frontend/src/components/CredentialEditor.vue frontend/src/components/ConfigWarnings.vue frontend/src/__tests__/configStore.test.ts frontend/src/__tests__/credentialEditor.test.ts frontend/src/__tests__/configWarnings.test.ts
git commit -m "feat: add frontend config editing"
```

### Task 10: Frontend Scheduler And Pair UI

**Files:**
- Create: `frontend/src/schedulerStore.ts`
- Create: `frontend/src/components/SchedulerStatus.vue`
- Create: `frontend/src/components/ScheduleEditor.vue`
- Create: `frontend/src/components/PairEditor.vue`
- Create: `frontend/src/__tests__/schedulerStatus.test.ts`
- Create: `frontend/src/__tests__/scheduleEditor.test.ts`
- Create: `frontend/src/__tests__/pairEditor.test.ts`

- [ ] **Step 1: Write failing scheduler and pair UI tests**

Cover:

- Scheduler store loads status, reloads scheduler, and tracks manual run state by pair.
- Scheduler status renders running state, job count, next runs, config mismatch, reload errors, and retry action.
- Schedule editor renders the enabled toggle, preset mode, advanced cron mode, timezone selector, summary text, timezone-aware next-run preview, and min-interval warning.
- Pair editor renders pair name, amount, limit factor, max price, `ignore_differing_orders`, validation errors, manual run button, and manual run completed/skipped/running-conflict/failed states.

Run: `npm --prefix frontend test -- --run frontend/src/__tests__/schedulerStatus.test.ts frontend/src/__tests__/scheduleEditor.test.ts frontend/src/__tests__/pairEditor.test.ts`

Expected: FAIL until scheduler store and pair UI components exist.

- [ ] **Step 2: Implement scheduler store**

Implement `schedulerStore.ts` with methods `loadStatus`, `reload`, and `runPairNow(pair)`.

- [ ] **Step 3: Implement scheduler status component**

Implement `SchedulerStatus.vue` props:

- `status`.
- `onReload`.

- [ ] **Step 4: Implement schedule editor component**

Implement `ScheduleEditor.vue` props and events:

- Props: `schedule`, `minOrderIntervalMinutes`, `fieldErrors`.
- Emits: `update:schedule`, `update:minOrderIntervalMinutes`.
- Behavior: preset mode, advanced mode, summary, next runs, min-interval warning.

- [ ] **Step 5: Implement pair editor component**

Implement `PairEditor.vue` props and events:

- Props: `pairConfig`, `fieldErrors`, `manualRunState`.
- Emits: `update:pairConfig`, `run-now`, `remove`.

Pair add behavior lives in `configStore.ts`; the app shell should expose an "Add pair" action that calls the store and includes the new pair in the next full config save.

- [ ] **Step 6: Run scheduler and pair UI tests**

Run: `npm --prefix frontend test -- --run frontend/src/__tests__/schedulerStatus.test.ts frontend/src/__tests__/scheduleEditor.test.ts frontend/src/__tests__/pairEditor.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/schedulerStore.ts frontend/src/components/SchedulerStatus.vue frontend/src/components/ScheduleEditor.vue frontend/src/components/PairEditor.vue frontend/src/__tests__/schedulerStatus.test.ts frontend/src/__tests__/scheduleEditor.test.ts frontend/src/__tests__/pairEditor.test.ts
git commit -m "feat: add frontend scheduler controls"
```

### Task 11: Frontend Auth, App Shell, And Design

**Files:**
- Modify: `frontend/src/authStore.ts`
- Create: `frontend/src/components/LoginView.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Create: `frontend/src/__tests__/loginView.test.ts`
- Create: `frontend/src/__tests__/app.test.ts`

- [ ] **Step 1: Write failing auth shell tests**

Cover:

- Auth store restores session through `GET /api/session`.
- Login view submits password and displays failed login errors.
- App renders login shell when unauthenticated.
- App renders authenticated dashboard after session restore.
- App shows setup/degraded state through `ConfigWarnings`.

Run: `npm --prefix frontend test -- --run frontend/src/__tests__/loginView.test.ts frontend/src/__tests__/app.test.ts`

Expected: FAIL until auth shell components exist.

- [ ] **Step 2: Implement auth store**

Implement `authStore.ts` for CSRF restoration, login, logout, and authenticated state.

- [ ] **Step 3: Implement login component**

Implement `LoginView.vue` for password auth and failed-login state.

- [ ] **Step 4: Compose authenticated app shell**

Implement `App.vue` for high-level composition only: choose login vs authenticated shell and wire store-backed components together.

- [ ] **Step 5: Add intentional visual design**

Use custom CSS variables, a non-default typography stack, strong information hierarchy, responsive pair cards, and a clear warning style for trading-sensitive actions. Do not add a heavy UI component library.

- [ ] **Step 6: Run auth shell tests**

Run: `npm --prefix frontend test -- --run frontend/src/__tests__/loginView.test.ts frontend/src/__tests__/app.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/authStore.ts frontend/src/components/LoginView.vue frontend/src/App.vue frontend/src/style.css frontend/src/__tests__/loginView.test.ts frontend/src/__tests__/app.test.ts
git commit -m "feat: add frontend app shell"
```

### Task 12: Frontend Full Checks

**Files:**
- No planned edits unless frontend verification reveals a bug.

- [ ] **Step 1: Run all frontend tests**

Run: `npm --prefix frontend test -- --run`

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: PASS and output in `frontend/dist`.

- [ ] **Step 3: Commit frontend verification fixes if needed**

Only commit if verification required source or test changes:

```bash
git status --short
git add frontend/src frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.json
git commit -m "fix: stabilize frontend checks"
```

## Chunk 4: Docker Runtime And Documentation

### Task 13: Docker Runtime And Documentation

**Files:**
- Modify: `Dockerfile`
- Modify: `README.md`
- Modify: `config-sample.yaml`
- Modify: `tests/fixtures/config.yaml`
- Create: `tests/test_docker_runtime.py`

- [ ] **Step 1: Write failing docs/runtime tests**

Add tests that assert:

- `Dockerfile` uses a Node build stage.
- Final command uses `uvicorn krakendca.web.app:app --host 0.0.0.0 --port 8080 --workers 1`.
- Dockerfile copies `frontend/dist` into the FastAPI static asset directory used by `krakendca.web.app`.
- Dockerfile removes system cron installation and crontab setup from the default runtime.
- Final runtime image does not include Node.
- Dockerfile does not copy `config-sample.yaml` to `/app/config.yaml`; missing config should trigger setup mode.
- Dockerfile declares `EXPOSE 8080`.
- `README.md` documents `WEB_UI_PASSWORD`.
- `README.md` documents optional `WEB_UI_SESSION_SECRET`.
- `README.md` documents optional `WEB_UI_COOKIE_SECURE`.
- `README.md` documents port mapping such as `-p 8080:8080`.
- `README.md` documents writable `config.yaml`.
- `README.md` removes or qualifies previous read-only `config.yaml` mount guidance for web UI mode.
- `README.md` documents writable `orders.csv` or data mount.
- `README.md` documents per-pair schedule schema.
- `README.md` documents legacy `delay`.
- `README.md` documents manual run behavior.
- `README.md` documents scheduler reload behavior.
- `config-sample.yaml` includes schedule examples.
- `tests/fixtures/config.yaml` stays equal to `config-sample.yaml`.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_docker_runtime.py tests/test_config.py::test_default_config_file_is_correct -v`

Expected: FAIL until Dockerfile, README, and sample config are updated.

- [ ] **Step 3: Update Dockerfile**

Use multi-stage build:

- Node stage builds `frontend/dist`.
- Python runtime installs `requirements.txt`.
- Runtime copies app code and `frontend/dist` into the static directory expected by `krakendca.web.app`.
- Runtime does not bake `config-sample.yaml` into `/app/config.yaml`; users mount writable config or use setup mode.
- Runtime ensures `/app/orders.csv` or the configured order history path is writable by the unprivileged user.
- Runtime keeps unprivileged user.
- Runtime exposes `8080`.
- Runtime command is single worker Uvicorn.
- Remove system cron installation and crontab setup from the default web runtime image.

- [ ] **Step 4: Update README**

Document:

- Docker web UI usage.
- `WEB_UI_PASSWORD`.
- Optional `WEB_UI_SESSION_SECRET`.
- Optional `WEB_UI_COOKIE_SECURE`.
- Port mapping with `-p 8080:8080`.
- Writable `config.yaml`.
- Existing read-only config mount guidance applies only to legacy CLI/cron mode, not web UI mode.
- Writable `orders.csv`.
- Per-pair `schedule` schema.
- Legacy `delay` fallback.
- Manual run and scheduler reload behavior.

- [ ] **Step 5: Update sample config and fixture**

Update `config-sample.yaml` and `tests/fixtures/config.yaml` with:

- One cron-managed pair containing `schedule.enabled: true`, a five-field `schedule.cron`, `schedule.timezone`, and `min_order_interval_minutes`.
- One disabled scheduled pair containing `schedule.enabled: false`.
- One legacy example or commented docs showing `delay` fallback behavior.

- [ ] **Step 6: Run backend and docs tests**

Run: `python -m pytest tests/test_docker_runtime.py tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 7: Build Docker image**

Run: `docker build -t kraken-dca:web-ui .`

Expected: PASS.

- [ ] **Step 8: Verify Docker container serves the web UI**

Run: `docker run --rm -d --name kraken-dca-web-ui-test -e WEB_UI_PASSWORD=test -p 18080:8080 kraken-dca:web-ui`

Expected: prints a container id.

If any following Docker smoke command fails, run `docker stop kraken-dca-web-ui-test` before retrying.

Run: `bash -c 'for i in 1 2 3 4 5; do curl -fsS http://localhost:18080/ && exit 0; sleep 1; done; exit 1'`

Expected: returns HTML within 5 attempts.

Run: `curl -fsS http://localhost:18080/`

Expected: returns the built Vue HTML and references compiled assets.

Run: `curl -fsS http://localhost:18080/ | grep -E 'assets/.+\\.(js|css)'`

Expected: finds at least one compiled JS or CSS asset reference.

Run: `ASSET_PATH=$(curl -fsS http://localhost:18080/ | sed -nE 's/.*src="([^"]*assets[^"]*\\.js)".*/\\1/p' | head -n 1) && curl -fsS "http://localhost:18080${ASSET_PATH}"`

Expected: returns compiled JavaScript.

Run: `docker exec kraken-dca-web-ui-test sh -c 'command -v node >/dev/null; test $? -ne 0'`

Expected: PASS, confirming Node is absent from the final runtime image.

Run: `docker stop kraken-dca-web-ui-test`

Expected: stops the container.

- [ ] **Step 9: Commit**

```bash
git add Dockerfile README.md config-sample.yaml tests/fixtures/config.yaml tests/test_docker_runtime.py
git commit -m "feat: run web scheduler in Docker"
```

## Chunk 5: Final Verification

### Task 14: Full Verification

**Files:**
- Create: `tests/test_web_smoke.py`
- Modify: source files only if verification reveals a bug.

- [ ] **Step 1: Run frontend build before smoke test**

Run: `npm --prefix frontend run build`

Expected: PASS and output in `frontend/dist`.

- [ ] **Step 2: Add integration smoke test**

Create `tests/test_web_smoke.py` that uses FastAPI `TestClient` to:

- Start the app with a temp config path and `WEB_UI_PASSWORD`.
- Load `/` and receive an HTML response.
- Assert the `/` response references built frontend assets.
- Log in through `POST /api/session`.
- Assert login returns `ok: true`, `authenticated: true`, and a non-empty string `csrf_token`.
- Read config through `GET /api/config`.
- Assert config response uses the standard `ok/data` shape and returns either valid config data or setup mode state.

Use this skeleton:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from krakendca.web.app import create_app


def test_web_app_serves_frontend_and_config(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
api:
  public_key: "KRAKEN_API_PUBLIC_KEY"
  private_key: "KRAKEN_API_PRIVATE_KEY"

dca_pairs:
  - pair: "XETHZEUR"
    amount: 15
    schedule:
      enabled: true
      cron: "0 9 * * *"
      timezone: "Europe/Prague"
""".strip()
    )
    static_dir = Path("frontend/dist")
    assert static_dir.joinpath("index.html").exists()
    monkeypatch.setenv("WEB_UI_PASSWORD", "test-password")

    app = create_app(config_path=str(config_path), static_dir=str(static_dir))
    with TestClient(app) as client:
        html = client.get("/")
        assert html.status_code == 200
        assert "text/html" in html.headers["content-type"]
        assert "assets/" in html.text

        login = client.post("/api/session", json={"password": "test-password"})
        assert login.status_code == 200
        login_payload = login.json()
        assert login_payload["ok"] is True
        assert login_payload["data"]["authenticated"] is True
        assert isinstance(login_payload["data"]["csrf_token"], str)
        assert login_payload["data"]["csrf_token"]

        config = client.get("/api/config")
        assert config.status_code == 200
        payload = config.json()
        assert payload["ok"] is True
        assert "data" in payload
        assert "config_valid" in payload["data"]
```

- [ ] **Step 3: Run integration smoke test**

Run: `python -m pytest tests/test_web_smoke.py -v`

Expected: PASS.

- [ ] **Step 4: Commit smoke test**

```bash
git add tests/test_web_smoke.py
git commit -m "test: add web UI smoke test"
```

- [ ] **Step 5: Run backend tests**

Run: `python -m pytest -v`

Expected: PASS.

- [ ] **Step 6: Run frontend tests**

Run: `npm --prefix frontend test -- --run`

Expected: PASS.

- [ ] **Step 7: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 8: Run Docker build**

Run: `docker build -t kraken-dca:web-ui .`

Expected: PASS.

- [ ] **Step 9: Start Docker container smoke**

Run: `docker run --rm -d --name kraken-dca-web-ui-final -e WEB_UI_PASSWORD=test -p 18080:8080 kraken-dca:web-ui`

Expected: prints a container id.

If any following Docker smoke command fails, run `docker stop kraken-dca-web-ui-final` before retrying.

- [ ] **Step 10: Wait for Docker web readiness**

Run: `bash -c 'for i in 1 2 3 4 5; do curl -fsS http://localhost:18080/ && exit 0; sleep 1; done; exit 1'`

Expected: returns built Vue HTML.

- [ ] **Step 11: Verify Docker web asset references**

Run: `curl -fsS http://localhost:18080/ | grep -E 'assets/.+\\.(js|css)'`

Expected: finds at least one compiled JS or CSS asset reference.

- [ ] **Step 12: Stop Docker smoke container**

Run: `docker stop kraken-dca-web-ui-final`

Expected: stops the container.

- [ ] **Step 13: Commit any verification fixes**

Only commit if verification required code changes:

```bash
git status --short
git add krakendca frontend/src frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.json tests Dockerfile README.md config-sample.yaml requirements.txt
git commit -m "fix: stabilize web scheduler verification"
```

- [ ] **Step 14: Inspect final git status**

Run: `git status --short --branch`

Expected: clean working tree on feature branch.
