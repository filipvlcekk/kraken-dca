# web-ui-cron-scheduler

## What this codebase does

Kraken-DCA is a Python/FastAPI and Vue app for configuring Kraken DCA
pairs, writing `config.yaml`, scheduling per-pair cron jobs, and manually
running trades. Docker web mode serves static Vue assets from `/app/frontend`
and an API under `/api`; legacy CLI delay mode still exists for non-web use.

## Auth shape

- `require_web_password` fails app startup unless `WEB_UI_PASSWORD` is set.
- `verify_password` compares submitted login passwords with `hmac.compare_digest`.
- `decode_session` verifies the signed `kraken_dca_session` cookie and attaches
  `request.state.authenticated_session`.
- `require_authenticated_session` gates safe API reads; `require_csrf` gates
  POST, PUT, PATCH, and DELETE requests through `X-CSRF-Token`.
- `set_session_cookie` issues httponly, `SameSite=Strict` cookies; the Secure
  flag is controlled by `WEB_UI_COOKIE_SECURE`.

## Threat model

The highest-impact attack is unauthorized config changes or manual scheduler
triggers that could submit Kraken orders. Attackers may also try to steal or
overwrite Kraken API credentials, bypass CSRF/session checks, abuse static path
handling, or corrupt persistent files such as `config.yaml` and `orders.csv`.

## Project-specific patterns to flag

- Any `/api/*` route missing `require_authenticated_session` for reads or
  `require_csrf` for unsafe methods.
- Config save paths that write submitted YAML or secrets without
  `merge_redacted_config`, `validate_config`, redaction, atomic replace, or
  backup behavior.
- Manual run and scheduler reload paths that call `SchedulerService` or
  `run_pair_now` without an authenticated CSRF-protected request flow.
- Static file handlers that serve user-controlled paths without
  `_inside_static_dir` containment.
- Any response that returns raw `api.public_key` or `api.private_key` instead
  of `REDACTED_SECRET` plus secret metadata.

## Known false-positives

- `tests/fixtures/vcr_cassettes/**` contains recorded third-party HTTP data,
  not live request handling.
- `config-sample.yaml` and `tests/fixtures/config.yaml` use placeholder Kraken
  credentials, not real secrets.
- `/login`, `/favicon.ico`, and `/assets/*` are intentionally public SPA/static
  paths.
- `FALLBACK_HTML` is intentional minimal HTML when built frontend assets are
  absent.
- Legacy CLI `delay` mode rejects enabled cron schedules by design via
  `get_cli_dca_pairs`.
