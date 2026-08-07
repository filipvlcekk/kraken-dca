# Deprecation Cleanup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove project-owned Python `datetime` deprecation warnings and explicitly defer the Starlette TestClient warning without increasing runtime dependency surface.

**Architecture:** Keep behavior-compatible helper boundaries. `krakendca/utils.py` will continue returning naive UTC datetimes while using non-deprecated timezone-aware APIs internally. The Starlette TestClient warning will be documented as test-stack debt, not fixed by adding runtime dependencies.

**Tech Stack:** Python 3.12, pytest, freezegun, FastAPI/Starlette TestClient, Coolify.

---

## GitNexus Preflight

- [ ] **Step 1: Confirm GitNexus index status**

Run:

```bash
npx gitnexus status
```

Expected: repository `/Users/filip/Projects/github/kraken-dca` is indexed at the current commit.

- [ ] **Step 2: Use GitNexus MCP impact/detect when available**

If the MCP session lists `kraken-dca`, run:

```text
mcp__gitnexus.detect_changes(scope="all", repo="kraken-dca")
```

Expected: only the current plan/spec docs before implementation; later only the intended implementation files.

If MCP still does not list `kraken-dca`, continue with CLI `npx gitnexus status` evidence. The repository can be indexed while the already-running MCP server still has an older registry snapshot.

---

## Chunk 1: Datetime Deprecation Cleanup

### Task 1: Lock Existing Naive UTC Contract

**Files:**
- Modify: `tests/test_utils.py`

- [ ] **Step 1: Add focused contract assertions**

Update the existing utility tests to assert that `utc_unix_time_datetime()`, `current_utc_datetime()`, and `current_utc_day_datetime()` return naive UTC datetimes:

```python
assert utc_unix_time_datetime(1617721936).tzinfo is None
assert current_utc_datetime().tzinfo is None
assert current_utc_day_datetime().tzinfo is None
```

- [ ] **Step 2: Verify current behavior passes**

Run:

```bash
.venv/bin/python -m pytest tests/test_utils.py
```

Expected: PASS. These assertions document current behavior rather than forcing a behavior change.

### Task 2: Prove Deprecation Warning Failure

**Files:**
- Test: `tests/test_utils.py`
- Modify later: `krakendca/utils.py`

- [ ] **Step 1: Run warnings as errors before implementation**

Run:

```bash
.venv/bin/python -m pytest tests/test_utils.py -W error::DeprecationWarning:krakendca\\.utils
```

Expected: FAIL on `datetime.utcfromtimestamp()` or `datetime.utcnow()` from `krakendca/utils.py`.

### Task 3: Replace Deprecated Datetime APIs

**Files:**
- Modify: `krakendca/utils.py`

- [ ] **Step 1: Import `time`**

Add:

```python
import time
```

- [ ] **Step 2: Replace `utcfromtimestamp()`**

Use a small helper or inline expression:

```python
datetime.fromtimestamp(nix_time, timezone.utc).replace(tzinfo=None)
```

Keep the existing nanosecond fallback behavior:

```python
try:
    date = datetime.fromtimestamp(nix_time, timezone.utc).replace(tzinfo=None)
except OSError:
    date = datetime.fromtimestamp(nix_time / 1000000000, timezone.utc).replace(
        tzinfo=None
    )
return date
```

- [ ] **Step 3: Replace `utcnow()`**

Use:

```python
return datetime.fromtimestamp(time.time(), timezone.utc).replace(
    tzinfo=None,
    microsecond=0,
)
```

This keeps the existing naive UTC return contract and preserves `freezegun` behavior.

### Task 4: Verify Datetime Cleanup

- [ ] **Step 1: Run utility tests with warnings promoted**

Run:

```bash
.venv/bin/python -m pytest tests/test_utils.py -W error::DeprecationWarning:krakendca\\.utils
```

Expected: PASS.

- [ ] **Step 2: Run DCA/runner focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_dca.py tests/test_runner.py tests/test_krakendca.py -W error::DeprecationWarning:krakendca\\.utils
```

Expected: PASS.

- [ ] **Step 3: Run full backend warning scan**

Run:

```bash
.venv/bin/python -m pytest -W default
```

Expected: PASS. `krakendca.utils` datetime deprecation warnings should be gone. The Starlette TestClient warning may remain.

### Task 5: Commit and Deploy Datetime Cleanup

- [ ] **Step 1: Review diff**

Run:

```bash
git diff --stat
git diff -- krakendca/utils.py tests/test_utils.py
git diff --check
```

Expected: Only `krakendca/utils.py` and `tests/test_utils.py` changed; no whitespace errors.

- [ ] **Step 2: Run full verification**

Run:

```bash
.venv/bin/python -m pytest
npm test -- --run
npm run build
```

Expected: all pass.

- [ ] **Step 3: Commit**

Run:

```bash
git add krakendca/utils.py tests/test_utils.py
git commit -m "replace deprecated utc datetime helpers"
```

- [ ] **Step 4: Push and deploy**

Run:

```bash
git push origin HEAD:feature/web-ui-cron-scheduler
```

Then deploy Coolify app `ypg4i75g0i9l3x3pcf5f1w14`, wait for `finished`, and verify external:

```bash
curl -sS -o /tmp/kraken-dca-login.html -w "%{http_code}\n" https://ypg4i75g0i9l3x3pcf5f1w14.cool.saola.cz/login
```

Expected: `200`.

---

## Chunk 2: Starlette TestClient Warning Decision

### Task 6: Document Current Decision

**Files:**
- Modify: `docs/superpowers/specs/2026-08-07-deprecation-cleanup-design.md`
- Modify optionally: `README.md` only if user wants maintenance notes in public docs

- [ ] **Step 1: Confirm warning source**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py tests/test_web_api.py -q
```

Expected: PASS with one `StarletteDeprecationWarning`.

- [ ] **Step 2: Confirm warning can be promoted**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py tests/test_web_api.py -q -W error::starlette.exceptions.StarletteDeprecationWarning
```

Expected: FAIL while `httpx2` is not installed. This confirms the warning is isolated to test client setup.

- [ ] **Step 3: Do not add `httpx2` to runtime requirements**

Leave `requirements.txt` unchanged in this task. `httpx2` is test-only and should wait for a dedicated dev/test requirements split or explicit follow-up approval.

### Task 7: Optional Follow-Up Plan for Test Dependencies

**Files:**
- Create later: `requirements-dev.txt` or `requirements-test.txt`
- Modify later: `.github/workflows/main-unit-testing.yaml`
- Modify later: README test setup section

- [ ] **Step 1: Propose separate test dependency file**

If the user approves, create a separate plan to split runtime and test dependencies so `httpx2` can be installed for tests without bloating the Docker runtime image.

- [ ] **Step 2: Keep runtime `httpx`**

Do not replace `httpx==0.28.1`; `krakendca/kraken_client.py` depends on it and tests use `httpx.MockTransport`.

---

## Final Verification Before Completion

- [ ] Run:

```bash
.venv/bin/python -m pytest
npm test -- --run
npm run build
git diff --check
```

- [ ] Confirm Coolify deployment status is `finished`.
- [ ] Confirm external `GET /login` returns `200`.
- [ ] Report remaining known warning debt: Starlette TestClient prefers `httpx2`, but this should be handled through dev/test dependency separation.
