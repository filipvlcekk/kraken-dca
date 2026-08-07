# Deprecation Cleanup Design

**Goal:** Remove actionable deprecation warnings after dependency modernization without changing runtime behavior or broadening dependency scope.

**Scope:** This design covers two follow-up tracks: Python `datetime` deprecation cleanup in project code, and Starlette `TestClient` warning handling after the FastAPI/Uvicorn upgrade.

## Current State

The dependency cleanup has already removed `krakenapi` and `pandas`, upgraded `APScheduler`, `croniter`, `FastAPI`, and `Uvicorn`, and deployed those changes through Coolify.

The remaining warning surface is:

- `datetime.utcfromtimestamp()` in `krakendca/utils.py`.
- `datetime.utcnow()` in `krakendca/utils.py`.
- `StarletteDeprecationWarning` from `fastapi.testclient.TestClient`, because Starlette now prefers `httpx2` for the test client.

## Approach

### 1. Datetime Cleanup

Keep the public helper contract unchanged: helpers return naive UTC `datetime` objects. This avoids changing DCA comparisons, CSV history behavior, and API serialization.

Replace deprecated APIs with timezone-aware construction internally, then strip `tzinfo` at the boundary:

- `datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)`
- `datetime.fromtimestamp(time.time(), timezone.utc).replace(tzinfo=None, microsecond=0)`

The `time.time()` form is preferred for `current_utc_datetime()` because the existing tests use `freezegun(..., tz_offset=...)`; this preserves current expectations better than switching directly to `datetime.now(timezone.utc)`.

Do not change `datetime_as_utc_unix()` in this pass. A true aware-UTC migration would be a separate behavior change because it can alter serialized API timestamps from `2021-05-03T00:00:00` to `2021-05-03T00:00:00+00:00`.

### 2. Starlette TestClient Warning

Do not add `httpx2` to runtime `requirements.txt` in this pass. The warning is test-only; adding `httpx2` to the single runtime requirements file would also install it in the Docker image.

Keep `httpx==0.28.1` because runtime Kraken REST code imports `httpx` and tests use `httpx.MockTransport`.

Defer an `httpx2` migration until the project has a separate test/dev dependency file or until Starlette removes the fallback. For now, document the warning and keep web/auth/static tests in the verification gate.

## Risks

- Returning aware datetimes from current helpers would break arithmetic between naive and aware datetimes in DCA code.
- Changing serialized `RunResult` timestamps would alter web API response shape.
- Replacing `httpx` with `httpx2` globally would break `krakendca/kraken_client.py`.
- Adding test-only dependencies to runtime requirements increases Docker image size and attack surface.

## Verification

Datetime cleanup should pass:

```bash
.venv/bin/python -m pytest tests/test_utils.py -W error::DeprecationWarning:krakendca\\.utils
.venv/bin/python -m pytest tests/test_dca.py tests/test_runner.py tests/test_krakendca.py -W error::DeprecationWarning:krakendca\\.utils
.venv/bin/python -m pytest -W default
```

TestClient warning evaluation should pass:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py tests/test_web_api.py tests/test_docker_runtime.py
.venv/bin/python -m pytest
npm test -- --run
npm run build
```

Coolify deployment healthcheck and external `GET /login` remain the runtime verification gates after each deployed change.
