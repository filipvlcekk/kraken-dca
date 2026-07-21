# Web UI Cron Scheduler Design

## Goal

Add a lightweight Docker-first web UI that lets users configure Kraken DCA pairs, set a per-pair cron schedule, persist the configuration to `config.yaml`, and manage scheduled DCA execution from inside the container.

The UI should make common schedules easy through presets while still allowing advanced users to enter raw cron expressions.

## Current State

The project is currently a Python CLI-style application. Docker starts system cron, and cron runs `__main__.py` every hour. Each DCA pair has a `delay` value in days, and the DCA logic uses that delay to avoid placing duplicate orders within the configured day window.

There is no frontend, no HTTP API, and no long-running Python scheduler process.

## Recommended Approach

Use a single Docker container that runs a Python web process:

- FastAPI provides authenticated JSON APIs.
- FastAPI serves the built Vue frontend as static files.
- APScheduler runs inside the same Python process.
- Vue 3 + Vite + TypeScript provides the frontend.
- `config.yaml` remains the source of truth.

This avoids writing generated crontab files at runtime and avoids managing multiple long-running processes in the same container.

## Architecture Units

Backend units:

- `krakendca.web.app`: FastAPI app factory, route registration, static frontend serving, startup/shutdown hooks.
- `krakendca.web.auth`: password login, signed session cookie handling, CSRF token validation, logout.
- `krakendca.web.schemas`: request and response models shared by API routes.
- `krakendca.config_store`: load, validate, redact, merge redacted secrets, backup, and atomic persistence for `config.yaml`.
- `krakendca.schedule`: five-field cron validation, timezone validation, next-run calculation, preset-to-cron helpers when needed by tests.
- `krakendca.scheduler`: APScheduler wrapper that maps config pairs to jobs, tracks active config state, reload errors, locks, and job status.
- `krakendca.runner`: executes one DCA pair through the existing Kraken DCA logic, owns open-order and min-interval safety checks, and returns a structured run result.

Frontend units:

- API client module for typed backend calls.
- Config store for loaded editable state, validation errors, dirty state, and save lifecycle.
- Pair editor component for pair trading settings.
- Schedule editor component for preset mode, advanced cron mode, timezone, summary, and next-run preview.
- Login view and authenticated app shell.

Each backend unit should be independently testable without starting the full web server except route-level integration tests.

## Frontend

Use Vue 3 + Vite + TypeScript without Nuxt and without a heavy component framework.

Each DCA pair is displayed as an editable card:

- Pair name.
- Amount.
- Optional limit factor.
- Optional max price.
- Optional `ignore_differing_orders`.
- Schedule enabled toggle.
- Schedule preset builder.
- Advanced cron input.
- Timezone selector.
- Human-readable schedule summary.
- Next run preview.

The schedule editor has two modes:

- Presets for common cases: daily, weekly, monthly, every X hours, every X minutes.
- Advanced mode for direct five-field cron input.

The frontend validates cron input for immediate feedback, but backend validation is authoritative.

Required UI states:

- Login screen for `WEB_UI_PASSWORD`.
- Setup mode when `config.yaml` does not exist.
- Degraded config mode when saved YAML or semantic validation is invalid.
- Scheduler status banner with running state, job count, next run times, and reload errors.
- Reload recovery action when `config_applied` is false.
- Manual run button per pair with clear `completed`, `skipped`, `running`, and `failed` results.
- Credential editor that shows redacted file credentials, env credential status, and explicit replacement controls.
- Warning when `orders.csv` is not writable or config persistence fails.

Suggested frontend cron libraries:

- `cron-parser` for validation and next-run preview with timezone support.
- `cronstrue` for human-readable descriptions.

## Backend

Add a FastAPI application alongside the existing CLI entrypoint.

Core endpoints:

- `GET /api/session` restores session state and returns a fresh CSRF token for authenticated sessions.
- `POST /api/session` logs in with `WEB_UI_PASSWORD`.
- `DELETE /api/session` logs out.
- `GET /api/config` returns the editable config with API credentials redacted.
- `PUT /api/config` validates and atomically writes `config.yaml`.
- `GET /api/scheduler` returns scheduler status and registered jobs.
- `POST /api/scheduler/reload` reloads jobs from config.
- `POST /api/pairs/{pair}/run` manually triggers one DCA pair.

The existing CLI entrypoint can remain for backwards compatibility, but Docker should default to the web process.

API responses should use a consistent shape:

```json
{
  "ok": false,
  "error": {
    "code": "invalid_config",
    "message": "Config validation failed.",
    "fields": {
      "dca_pairs.0.schedule.cron": "Invalid cron expression."
    }
  }
}
```

Successful responses should use `{"ok": true, "data": {"field": "value"}}` with endpoint-specific data.

Use these status codes:

- `400` for validation errors.
- `401` for unauthenticated access.
- `403` for authenticated but disallowed actions.
- `409` for scheduler/job concurrency conflicts.
- `502` for Kraken API or network failures.
- `500` for unexpected persistence or scheduler failures.

API contract:

| Endpoint | Request | Success response |
| --- | --- | --- |
| `GET /api/session` | empty | `{"ok": true, "data": {"authenticated": true, "csrf_token": "csrf-token-value"}}` |
| `POST /api/session` | `{"password": "user-password"}` | `{"ok": true, "data": {"authenticated": true, "csrf_token": "csrf-token-value"}}` and a session cookie |
| `DELETE /api/session` | empty | `{"ok": true, "data": {"authenticated": false}}` |
| `GET /api/config` | empty | `{"ok": true, "data": {"config": {"dca_pairs": []}, "secrets": {"public_key": {"configured": true, "source": "file"}}, "config_valid": true, "validation_errors": []}}` |
| `PUT /api/config` | `{"config": {"dca_pairs": []}}` | `{"ok": true, "data": {"config": {"dca_pairs": []}, "scheduler": {"config_applied": true}}}` |
| `GET /api/scheduler` | empty | `{"ok": true, "data": {"running": true, "config_applied": true, "jobs": [], "last_reload_at": "2026-07-21T10:00:00Z"}}` |
| `POST /api/scheduler/reload` | empty | `{"ok": true, "data": {"scheduler": {"running": true, "config_applied": true}}}` |
| `POST /api/pairs/{pair}/run` | empty | `{"ok": true, "data": {"pair": "XETHZEUR", "status": "completed", "started_at": "2026-07-21T10:00:00Z", "finished_at": "2026-07-21T10:00:03Z"}}` |

Scheduler job response shape:

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

Manual run response outcomes:

```json
{"ok": true, "data": {"pair": "XETHZEUR", "status": "skipped", "reason": "duplicate_order"}}
```

```json
{"ok": false, "error": {"code": "insufficient_funds", "message": "Insufficient funds to buy configured amount."}}
```

Manual run status handling:

- `completed` with `200` when an order was submitted and history was saved.
- `skipped` with `200` for expected DCA guards such as duplicate order or max-price protection.
- `409` when the pair is already running.
- `409` with code `config_not_applied` when saved config differs from active scheduler config.
- `400` for validation/domain failures such as insufficient funds.
- `502` for Kraken API or network failures.
- `500` for unexpected runtime failures.

Runner result contract:

```json
{
  "pair": "XETHZEUR",
  "status": "completed",
  "reason": null,
  "started_at": "2026-07-21T10:00:00Z",
  "finished_at": "2026-07-21T10:00:03Z",
  "order_txid": "OCYS4K-OILOE-36HPAE",
  "message": "Order submitted and saved."
}
```

Runner result rules:

- `runner` performs balance checks, duplicate-order checks, max-price checks, order submission, and order history persistence.
- `scheduler` performs per-pair locking and decides whether a run can start.
- API routes map `RunResult` to HTTP responses without duplicating trading safety logic.
- Scheduled jobs log `RunResult` and do not expose it over HTTP unless scheduler history is added later.

## Authentication

Protect the web UI with a single password from `WEB_UI_PASSWORD`.

Use session-cookie authentication:

- In web mode, the app fails startup if `WEB_UI_PASSWORD` is missing or empty.
- Login compares the supplied password with `WEB_UI_PASSWORD` using constant-time comparison.
- Successful login sets a signed `HttpOnly`, `SameSite=Strict` cookie.
- The cookie expires after 12 hours of inactivity.
- Cookie signing uses `WEB_UI_SESSION_SECRET` when set, otherwise `WEB_UI_PASSWORD`.
- The cookie is named `kraken_dca_session`.
- `Secure` is disabled by default for local Docker HTTP and enabled when `WEB_UI_COOKIE_SECURE=true`.
- Login returns a CSRF token in the JSON response.
- `GET /api/session` returns a fresh CSRF token after page refresh when the session cookie is valid.
- Unsafe API methods require `X-CSRF-Token` matching the authenticated session.
- Static UI routes require authentication except the login screen and static assets needed to render it.
- All `/api/*` endpoints require authentication except `POST /api/session`.
- `GET /api/config` requires authentication because it exposes trading configuration.
- Config-writing and scheduler-control endpoints require an authenticated session.

Basic Auth is intentionally not used because session auth gives better UI behavior and supports logout while remaining lightweight.

## Configuration Model

Add a new per-pair schedule object:

```yaml
dca_pairs:
  - pair: "XETHZEUR"
    amount: 15
    schedule:
      enabled: true
      cron: "0 9 * * *"
      timezone: "Europe/Prague"
    limit_factor: 0.985
    max_price: 2900.10
```

Keep `delay` as a legacy fallback for existing configurations:

- If `schedule` is present, use cron scheduling.
- If `schedule` is absent and `delay` is present, preserve the existing behavior.

Do not use `delay` to block every cron-scheduled run. Cron scheduling and duplicate-order safety must be separate concerns.

`krakendca.config.Config` should delegate parsing and validation to `krakendca.config_store`. The CLI and web runtime must not maintain separate config validation rules.

Pair identity rules for v1:

- Duplicate `pair` values are not allowed.
- API paths can use the pair name as the stable identifier.
- Reordering pairs in YAML does not affect scheduler job identity.
- Add and remove pair operations are allowed through full config save, not separate pair-specific CRUD endpoints.

Credential handling:

- The redaction sentinel is `__KRADCA_SECRET_REDACTED__`.
- `GET /api/config` returns `api.public_key` and `api.private_key` as `__KRADCA_SECRET_REDACTED__` when present in `config.yaml`.
- Redacted values must not be written back as literal secrets.
- `PUT /api/config` preserves existing secrets when the submitted value is redacted.
- Users can replace credentials by submitting non-redacted values.
- If credentials are omitted from the file and provided through environment variables, `GET /api/config` returns `null` for the file value and reports that env credentials are configured.
- On `PUT /api/config`, `null` means omit that credential from the written file.
- If a credential is omitted from the file, the runtime may still use the corresponding environment variable.
- Empty strings are invalid credentials.
- A saved config is valid only when each credential is available either from file value preservation, a new submitted value, or environment variable.

Secret metadata response shape:

```json
{
  "secrets": {
    "public_key": {"configured": true, "source": "file"},
    "private_key": {"configured": true, "source": "env"}
  }
}
```

Configuration mode matrix:

| Pair config | Scheduler behavior | CLI behavior |
| --- | --- | --- |
| `schedule.enabled: true` with valid `cron` | Register `dca:<pair>` cron job | Skip with a clear error that cron schedules require web mode |
| `schedule` present without `enabled` | Treat as enabled | Skip with the same web-mode error |
| `schedule.enabled: false` | Do not register a scheduled job; authenticated manual run is still allowed | Skip pair |
| Both enabled `schedule` and `delay` present | Use `schedule`; keep `delay` in file only as legacy metadata | Skip with the same web-mode error |
| No `schedule`, valid `delay` present | Register `legacy-delay:<pair>` hourly fallback job | Preserve current CLI behavior |
| No `schedule`, no valid `delay` | Invalid config | Invalid config |

The Vue UI should always write explicit `schedule.enabled` for cron-managed pairs.

If `schedule` is present, it takes precedence over `delay`. A disabled schedule disables scheduled execution even when `delay` is also present.

Schedule validation rules:

- Cron expressions must use standard five-field Unix cron format: minute, hour, day of month, month, day of week.
- Seconds and Quartz-style cron expressions are rejected.
- Day-of-week uses standard Unix cron semantics: `0` and `7` mean Sunday, `1` means Monday, and names `sun` through `sat` are accepted.
- UI-generated cron should use weekday names instead of numbers to avoid scheduler-version differences.
- Backend cron parsing must normalize Unix day-of-week semantics before creating APScheduler triggers.
- If `schedule.timezone` is omitted for an enabled schedule, default to `UTC`.
- Timezones must be valid IANA timezone names.
- Disabled schedules do not require `cron` or `timezone`.
- If disabled schedules include `cron` or `timezone`, provided values must still be valid.
- `min_order_interval_minutes` must be an integer from `0` through `525600`.
- The default `min_order_interval_minutes` is `30`.
- Preset "every X minutes" allows only values that a single cron expression can represent exactly within each hour: `5`, `10`, `15`, `20`, and `30`.
- Preset "every X hours" allows only values that divide a day evenly: `1`, `2`, `3`, `4`, `6`, `8`, `12`, and `24`.
- Monthly presets allow day `1` through `28` to avoid skipped months.
- Advanced cron mode can express schedules outside preset ranges if the cron validates.

## Duplicate-Order Safety

The current `delay` behavior prevents duplicate orders by checking open and closed orders in a day-based lookback window. With cron schedules this must be separated, otherwise schedules such as every 6 hours would not work.

For cron-enabled pairs:

- Always check open orders for the same pair before placing a new order.
- Add an optional `min_order_interval_minutes` field for closed-order lookback protection.
- If omitted, default to `30`.
- If set to `0`, skip closed-order lookback and rely on open-order checks only.
- The UI must show a warning when the configured cron can run more frequently than `min_order_interval_minutes`.

Safety rules:

- `ignore_differing_orders` applies to both open-order checks and closed-order lookback.
- If `ignore_differing_orders` is false, any same-pair open order blocks execution.
- If `ignore_differing_orders` is true, same-pair orders differing by more than 1% from the configured amount are ignored.
- Manual runs use the same duplicate-order safety as scheduled runs.
- There is no force-run override in v1.
- Cron timezone only controls trigger calculation.
- `min_order_interval_minutes` uses absolute UTC timestamps, not local day boundaries.
- Legacy `delay` configs keep the existing UTC day-window behavior.

Example:

```yaml
dca_pairs:
  - pair: "XXBTZEUR"
    amount: 20
    schedule:
      enabled: true
      cron: "0 */6 * * *"
      timezone: "Europe/Prague"
    min_order_interval_minutes: 30
```

## Scheduler Behavior

On app startup:

1. Load and validate `config.yaml`.
2. Create one scheduler job per enabled cron-scheduled pair.
3. For legacy delay-only pairs, create a fallback hourly scheduler job that preserves the current behavior by invoking the existing delay-based DCA logic.
4. Start APScheduler.

On config save:

1. Validate all submitted data.
2. Build scheduler job definitions from the submitted config without mutating active jobs.
3. Write a backup of the previous config.
4. Write the new config to a temporary file.
5. Atomically replace `config.yaml`.
6. Reload scheduler jobs from the saved config.

If scheduler reload fails after the file is saved:

- Keep the previous active scheduler jobs running.
- Return `500` with `config_saved: true` and `scheduler_reloaded: false`.
- Store the reload error in scheduler status.
- Let the user retry through `POST /api/scheduler/reload` after correcting the issue.
- Mark scheduler status as `config_applied: false`.
- Track `saved_config_fingerprint` and `active_config_fingerprint`.
- `GET /api/config` always returns the saved desired config.
- `GET /api/scheduler` reports whether the active scheduler jobs match the saved desired config.
- Manual runs are rejected with `409 config_not_applied` until the scheduler successfully reloads the saved config.

Invalid schedule data such as invalid cron or timezone is rejected before save. Post-save reload failures are reserved for runtime failures such as APScheduler replacement errors after successful validation.

Backup and fingerprint rules:

- Config backups are stored next to the config file as `config.yaml.bak.<YYYYmmddTHHMMSSZ>`.
- Keep the 10 newest backups and delete older backup files after a successful save.
- Config fingerprints are SHA-256 hashes of canonical normalized config data after defaults are applied.
- Credential values are replaced with stable redaction markers before fingerprinting so fingerprints do not expose secret material.
- Credential source and presence are included in the fingerprint.

Scheduler mismatch response shape:

```json
{
  "running": true,
  "config_applied": false,
  "saved_config_fingerprint": "sha256:abc123",
  "active_config_fingerprint": "sha256:def456",
  "reload_error": "Failed to replace APScheduler jobs: scheduler unavailable",
  "jobs": []
}
```

Job IDs should be deterministic:

- Cron-enabled pair: `dca:<pair>`.
- Legacy delay-only pair: `legacy-delay:<pair>`.

Because duplicate pair names are rejected, the pair name is sufficient for v1.

Concurrency rules:

- Each pair has a per-pair execution lock.
- A scheduled run is skipped with a warning if the same pair is already running.
- A manual run returns `409` if the same pair is already running.
- APScheduler jobs use `max_instances=1`.
- Missed runs are coalesced so only one catch-up execution can run after downtime.
- Misfires older than 5 minutes are skipped by default.

## Docker Runtime

Replace the default `cron -f` command with the web app process, for example:

```text
uvicorn krakendca.web.app:app --host 0.0.0.0 --port 8080 --workers 1
```

The container should expose port `8080`.

The mounted `config.yaml` must be writable if the UI is expected to save changes. Documentation should call this out explicitly because the previous hardening recommended read-only mounts for config.

The runtime must use exactly one Uvicorn worker in v1. Multiple workers would start multiple in-process schedulers and could duplicate trades.

Order history persistence:

- `orders.csv` remains the default order history path.
- Docker examples should mount a writable order history file or writable data directory.
- Scheduled and manual runs fail with a clear error if order history cannot be written.
- If Kraken order submission succeeds but order history persistence fails, return/log a `history_persistence_failed` result that explicitly says the order may already have been placed.

Use a multi-stage Docker build:

- Node stage builds the Vue/Vite frontend into static assets.
- Python runtime stage installs Python dependencies and copies the built frontend assets.
- Do not require Node in the final runtime image.

## Error Handling

Validation errors should return structured API responses that the frontend can attach to fields.

Important validation cases:

- Missing or invalid `WEB_UI_PASSWORD` behavior.
- Invalid cron expression.
- Cron day-of-week normalization.
- Unsupported cron field count.
- Invalid timezone.
- Missing pair.
- Non-positive amount.
- Invalid optional numeric values.
- Config file not writable.
- Order history file not writable.
- Scheduler reload failure after config save.

If config save succeeds but scheduler reload fails, the API should report the reload failure clearly and keep the saved file intact.

Startup behavior:

- Missing or empty `WEB_UI_PASSWORD` fails startup in web mode.
- Missing `config.yaml` starts setup mode with no scheduler jobs.
- Invalid YAML or invalid config starts degraded mode with no scheduler jobs.
- In degraded mode, authenticated users can view validation errors and save a corrected config.
- If YAML parses but semantic validation fails, `GET /api/config` returns the redacted structured config plus `config_valid: false` and `validation_errors`.
- If YAML parsing fails, `GET /api/config` returns `raw_yaml: null` by default to avoid leaking secrets from malformed files.
- Users can still replace malformed config by submitting a complete valid config through `PUT /api/config`.
- Scheduler status reports `running: false` and the config error until a valid config is saved or reloaded.

## Testing

Backend tests:

- Config accepts valid schedule objects.
- Config keeps legacy `delay` behavior.
- Invalid cron is rejected.
- Invalid timezone is rejected.
- Config writes are atomic and create backups.
- Auth protects write endpoints.
- Auth protects config reads.
- Login/logout and CSRF enforcement work.
- `GET /api/session` restores CSRF after refresh.
- API responses follow the standard `ok/data/error` shape.
- Redacted secrets are preserved on save.
- `krakendca.config.Config` and web config loading share `config_store` validation.
- Scheduler registers expected jobs from config.
- Scheduler registers fallback jobs for delay-only legacy pairs.
- Concurrent manual/scheduled runs do not overlap for the same pair.
- Startup with invalid config enters degraded mode.
- Reload failure preserves previous active scheduler jobs.
- Manual runs are rejected while saved config differs from active scheduler config.
- Disabled schedules validate according to the schedule validation rules.
- `schedule.enabled: false` takes precedence over `delay`.
- Malformed YAML degraded mode does not return raw secrets.
- Order history write failure is reported explicitly.
- History persistence failure after order submission is distinguishable from order submission failure.
- Docker image starts the web process and serves the built frontend.
- Docker image uses a single web worker.

Frontend tests:

- Preset selections generate expected cron strings.
- Every-X presets only expose values representable by one cron expression.
- Advanced cron validation shows errors.
- Scheduler status and reload mismatch states render.
- Manual run outcomes render.
- Setup/degraded config mode renders.
- Config save sends expected payload.
- Next-run preview handles timezone.
- Redacted secrets round-trip without replacing saved credentials.

Integration smoke test:

- Build frontend.
- Start backend app.
- Load `/`.
- Read config through API after login.
