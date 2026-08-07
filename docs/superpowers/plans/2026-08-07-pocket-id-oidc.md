# Pocket ID OIDC Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Linkding-style app-level Pocket ID OIDC login and make it the only production web UI authentication mode.

**Architecture:** Introduce an explicit auth mode configuration layer, keep existing `itsdangerous` app sessions as the authorization boundary for internal APIs, and add focused OIDC start/callback routes that create those sessions after provider validation. Password login remains available only when `WEB_UI_AUTH_MODE=password` is explicitly selected for local development and tests.

**Tech Stack:** Python 3.12, FastAPI/Starlette, `httpx`, `itsdangerous`, OIDC/JWT validation helper to be selected during implementation, Vue 3, Vitest, pytest, Coolify.

---

## Chunk 1: Runtime Audit and Auth Mode Contract

### Task 1: Audit Dependencies and Runtime Surface

**Files:**
- Modify: `tests/test_requirements.py`
- Modify: `README.md`
- Do not modify production auth code in this task.

- [ ] **Step 1: Add or update dependency guard tests**

Update `tests/test_requirements.py` so it documents the current intentional runtime packages and catches accidental OIDC dependency sprawl. Keep `httpx` in runtime because it is already used by Kraken REST and can support OIDC HTTP calls.

- [ ] **Step 2: Run requirement tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_requirements.py -q
```

Expected: PASS before and after documentation-only changes.

- [ ] **Step 3: Document audit result**

Update README maintenance notes to say that OIDC should reuse `httpx` and add only a narrow JWT/OIDC validation dependency if required.

- [ ] **Step 4: Commit**

Run:

```bash
git add README.md tests/test_requirements.py
git commit -m "document oidc dependency guardrails"
```

### Task 2: Add Explicit Auth Mode Startup Contract

**Files:**
- Modify: `krakendca/web/auth.py`
- Modify: `krakendca/web/app.py`
- Modify: `tests/test_web_auth.py`

- [ ] **Step 1: Write failing startup tests**

Add tests showing:

```python
def test_startup_requires_web_ui_auth_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("WEB_UI_AUTH_MODE", raising=False)
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="WEB_UI_AUTH_MODE"):
        with TestClient(app, base_url="https://testserver"):
            pass


def test_password_mode_requires_web_ui_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_UI_AUTH_MODE", "password")
    monkeypatch.delenv("WEB_UI_PASSWORD", raising=False)
    monkeypatch.setenv("WEB_UI_SESSION_SECRET", TEST_SESSION_SECRET)
    app = create_app(config_path=str(tmp_path / "missing.yaml"), static_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="WEB_UI_PASSWORD"):
        with TestClient(app, base_url="https://testserver"):
            pass
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py::test_startup_requires_web_ui_auth_mode tests/test_web_auth.py::test_password_mode_requires_web_ui_password -q
```

Expected: first test fails because current startup has no auth mode contract.

- [ ] **Step 3: Implement minimal auth mode parsing**

Add `require_auth_mode(env=None) -> Literal["password", "oidc"]` in `krakendca/web/auth.py`. In `lifespan`, load `app.state.auth_mode`; require `WEB_UI_PASSWORD` only in password mode. OIDC mode configuration can still fail in the next task.

- [ ] **Step 4: Update test helpers**

Update `_set_web_auth_env()` to set `WEB_UI_AUTH_MODE=password` for existing password-mode tests.

- [ ] **Step 5: Run targeted auth tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py -q
```

Expected: PASS.

## Chunk 2: OIDC Configuration and Backend Routes

### Task 3: Add OIDC Configuration Validation

**Files:**
- Create: `krakendca/web/oidc.py`
- Modify: `krakendca/web/app.py`
- Modify: `tests/test_web_auth.py`

- [ ] **Step 1: Write failing OIDC config tests**

Add tests for OIDC mode missing each required value:

```python
WEB_UI_OIDC_ISSUER
WEB_UI_OIDC_CLIENT_ID
WEB_UI_OIDC_CLIENT_SECRET
WEB_UI_OIDC_REDIRECT_URL
WEB_UI_OIDC_ALLOWED_GROUP
```

Expected: startup raises `RuntimeError` naming the missing variable.

- [ ] **Step 2: Implement `OidcConfig`**

Create a small dataclass:

```python
@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_url: str
    allowed_group: str
    scopes: tuple[str, ...] = ("openid", "email", "profile", "groups")
```

Add `require_oidc_config(env=None) -> OidcConfig` that strips trailing slash from issuer and rejects missing values.

- [ ] **Step 3: Store config on app state**

In OIDC mode, set `app.state.oidc_config = require_oidc_config()`. In password mode, set it to `None`.

- [ ] **Step 4: Verify startup tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py -q
```

Expected: PASS.

### Task 4: Add OIDC Start Route

**Files:**
- Create: `krakendca/web/routes_oidc.py`
- Modify: `krakendca/web/app.py`
- Modify: `krakendca/web/oidc.py`
- Modify: `tests/test_web_auth.py`

- [ ] **Step 1: Write failing start-route test**

Test that `GET /api/auth/oidc/start` in OIDC mode:

- returns `307` or `302`
- redirects to Pocket ID authorization endpoint
- includes `client_id`, `redirect_uri`, `response_type=code`, `scope`, `state`, and `nonce`
- sets an HTTP-only, Secure, SameSite=Lax temporary OIDC state cookie

- [ ] **Step 2: Implement signed temporary OIDC state cookie**

Use the existing session serializer secret or a dedicated serializer salt:

```python
OIDC_STATE_COOKIE_NAME = "kraken_dca_oidc_state"
OIDC_STATE_MAX_AGE_SECONDS = 10 * 60
OIDC_STATE_SALT = "kraken-dca-oidc-state"
```

Store `state`, `nonce`, and `next_path` if needed. Use `secrets.token_urlsafe(32)`.

Set the temporary OIDC state cookie with `Path=/api/auth/oidc`, `HttpOnly`, `Secure`, and `SameSite=Lax`. The callback comes from Pocket ID as a top-level cross-site navigation, so `SameSite=Strict` would be too strict for this cookie.

- [ ] **Step 3: Implement route and include router**

Add router prefix `/api/auth/oidc`; include it in `create_app()`. Reject start route with `404` or `400` when not in OIDC mode.

- [ ] **Step 4: Verify targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py -q
```

Expected: PASS.

### Task 5: Add OIDC Callback Validation

**Files:**
- Modify: `krakendca/web/routes_oidc.py`
- Modify: `krakendca/web/oidc.py`
- Modify: `tests/test_web_auth.py`

- [ ] **Step 1: Write failing state validation tests**

Add tests for:

- missing state cookie
- tampered state cookie
- callback `state` mismatch
- callback `error` parameter from provider

Expected: no app session cookie is set; temporary state cookie is cleared.

- [ ] **Step 2: Implement state validation and controlled failure response**

Use existing `ApiException` for API-style failures or redirect to `/login?error=oidc`. Keep behavior consistent and covered by tests.

- [ ] **Step 3: Write failing successful callback test with mocked provider**

Mock token exchange/userinfo using `httpx.MockTransport` or an injectable OIDC client. The accepted identity must contain `groups=["kraken-dca-admins"]`.

Expected after callback:

- app session cookie is set
- state cookie is cleared
- response redirects to `/`
- `/api/session` returns authenticated with a fresh CSRF token
- app session payload contains no access token, refresh token, or raw ID token

- [ ] **Step 4: Write failing unauthorized group test**

Mock valid identity without the allowed group. Expected: reject callback, clear temporary cookie, do not set app session.

- [ ] **Step 5: Implement minimal OIDC client**

Implement token exchange and identity validation through a small `OidcClient` abstraction. It should make the validation dependency explicit and easy to test. Do not log token values.

- [ ] **Step 6: Add OIDC session freshness tests**

Add tests proving that OIDC-created app sessions carry an absolute freshness timestamp and that session restore rejects a locally valid cookie once that timestamp has passed. Password-mode local sessions can keep the existing behavior.

- [ ] **Step 7: Implement OIDC session freshness**

Extend the existing session payload for OIDC-created sessions with low-risk metadata only:

```python
{
    "authenticated": True,
    "csrf_token": csrf_token,
    "auth_mode": "oidc",
    "sub": subject,
    "email": email,
    "groups": groups,
    "created_at": now,
    "reauth_after": now + OIDC_SESSION_MAX_AGE_SECONDS,
}
```

Do not store OIDC access tokens, refresh tokens, or raw ID tokens in the signed app cookie.

- [ ] **Step 8: Verify callback tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py -q
```

Expected: PASS.

### Task 6: Disable Password Login in OIDC Mode

**Files:**
- Modify: `krakendca/web/routes_session.py`
- Modify: `tests/test_web_auth.py`

- [ ] **Step 1: Write failing test**

Add:

```python
def test_password_login_is_disabled_in_oidc_mode(...):
    response = client.post("/api/session", json={"password": "secret"})
    assert response.status_code in {400, 404}
```

- [ ] **Step 2: Implement route guard**

At the top of password login route, reject when `request.app.state.auth_mode != "password"`. Keep `GET /api/session` and `DELETE /api/session` auth-mode agnostic.

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py -q
```

Expected: PASS.

## Chunk 3: Frontend Login Modes

### Task 7: Expose Auth Capabilities

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/authStore.ts`
- Modify: `tests/test_web_auth.py`
- Modify or create frontend tests under `frontend/src/__tests__/`

- [ ] **Step 1: Write failing backend/current-session test**

Extend `GET /api/session` response to include auth mode/capabilities for unauthenticated users:

```json
{"authenticated": false, "auth_mode": "oidc", "oidc_login_url": "/api/auth/oidc/start"}
```

- [ ] **Step 2: Implement response fields**

Keep backwards compatibility for authenticated response by including the same fields plus `csrf_token`.

- [ ] **Step 3: Update TypeScript types/store**

Add `auth_mode` and `oidc_login_url` to `SessionResponse`; store it in auth state.

- [ ] **Step 4: Verify backend and frontend tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_auth.py -q
npm test -- --run
```

Expected: PASS after frontend updates.

### Task 8: Render OIDC-Only Login Page in OIDC Mode

**Files:**
- Modify: `frontend/src/components/LoginView.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/__tests__/loginView.test.ts`
- Modify: `frontend/src/__tests__/app.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Test OIDC mode renders only `Sign in with Pocket ID` and no password input. Test password mode still renders password input for local/test mode.

- [ ] **Step 2: Implement OIDC button behavior**

On click, set `window.location.href` to `oidc_login_url`.

- [ ] **Step 3: Verify frontend**

Run:

```bash
npm test -- --run
npm run build
```

Expected: PASS.

## Chunk 4: Docker/Runtime Hardening and Docs

### Task 9: Docker Runtime Hardening

**Files:**
- Modify: `Dockerfile`
- Modify: `tests/test_docker_runtime.py`
- Modify: `README.md`

- [ ] **Step 1: Audit current Dockerfile**

Confirm final image runs as non-root, includes only runtime dependencies, and does not contain frontend build tooling. Keep `curl` only if it is still needed for Docker/Coolify health checks.

- [ ] **Step 2: Add tests for OIDC docs/env**

Update Docker runtime tests so README documents required production OIDC env vars and `WEB_UI_AUTH_MODE=oidc`.

- [ ] **Step 3: Add optional healthcheck only if appropriate**

If adding a Docker `HEALTHCHECK`, use a low-risk endpoint such as `/login`. If Coolify already supplies health checks and `curl` exists only for health checks, keep the change small and document the rationale.

- [ ] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_docker_runtime.py tests/test_requirements.py -q
```

Expected: PASS.

### Task 10: README Pocket ID Setup

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document Pocket ID client setup**

Add callback URL:

```text
https://<kraken-dca-host>/api/auth/oidc/callback
```

Document required scopes: `openid email profile groups`.

- [ ] **Step 2: Document Coolify env vars**

Show placeholders only. Do not include real secrets.

- [ ] **Step 3: Document local password mode**

Make clear that password mode is for local development/tests, not production.

## Chunk 5: Verification, Review, Deploy

### Task 11: Full Verification

- [ ] **Step 1: Run backend**

```bash
.venv/bin/python -m pytest -W default
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend**

```bash
npm test -- --run
npm run build
```

Expected: all tests pass and production build succeeds.

- [ ] **Step 3: Run style checks on touched files**

```bash
.venv/bin/python -m flake8 krakendca/web/auth.py krakendca/web/app.py krakendca/web/routes_session.py krakendca/web/routes_oidc.py krakendca/web/oidc.py tests/test_web_auth.py tests/test_docker_runtime.py tests/test_requirements.py
git diff --check
```

Expected: PASS. Do not claim repo-wide `black` or repo-wide `flake8` are clean unless they are explicitly run and pass.

- [ ] **Step 4: Run GitNexus impact/detect**

Use GitNexus on changed auth/session symbols before commit:

```text
mcp__gitnexus.detect_changes(scope="all", repo="kraken-dca")
```

Expected: impacted flows are auth/session/web APIs; no unrelated areas.

### Task 12: Commit, Configure Coolify, Deploy

- [ ] **Step 1: Commit implementation**

Use one or more focused commits. Suggested final implementation commit:

```bash
git add README.md Dockerfile requirements.txt tests krakendca frontend
git commit -m "add pocket id oidc web auth"
```

- [ ] **Step 2: Push deploy branch**

```bash
git push origin HEAD:feature/web-ui-cron-scheduler
```

- [ ] **Step 3: Set Coolify runtime env vars**

Set masked runtime values:

```env
WEB_UI_AUTH_MODE=oidc
WEB_UI_OIDC_ISSUER=...
WEB_UI_OIDC_CLIENT_ID=...
WEB_UI_OIDC_CLIENT_SECRET=...
WEB_UI_OIDC_REDIRECT_URL=https://ypg4i75g0i9l3x3pcf5f1w14.cool.saola.cz/api/auth/oidc/callback
WEB_UI_OIDC_ALLOWED_GROUP=kraken-dca-admins
WEB_UI_SESSION_SECRET=...
WEB_UI_COOKIE_SECURE=true
```

Do not reveal secrets in logs or final messages.

- [ ] **Step 4: Deploy and verify**

Deploy Coolify app `ypg4i75g0i9l3x3pcf5f1w14`, wait for `finished`, then verify:

```bash
curl -sS -o /tmp/kraken-dca-login.html -w "%{http_code} %{content_type}\n" https://ypg4i75g0i9l3x3pcf5f1w14.cool.saola.cz/login
curl -sS -o /tmp/kraken-dca-session.json -w "%{http_code} %{content_type}\n" https://ypg4i75g0i9l3x3pcf5f1w14.cool.saola.cz/api/session
```

Expected:

- `/login`: `200 text/html`
- `/api/session`: `200 application/json`
- login page shows Pocket ID-only action

Manual browser validation is required for the final Pocket ID passkey flow because it leaves the application and returns through Pocket ID.
