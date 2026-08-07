# Pocket ID OIDC Design

**Goal:** Make Pocket ID the only production web UI login method while keeping the existing signed application session cookie for authenticated requests.

**Scope:** This design covers app-level OpenID Connect login, production password-login disablement, group-based authorization, and the surrounding dependency/runtime hardening checks needed before deployment.

## Current State

The web UI currently authenticates with `WEB_UI_PASSWORD` through `POST /api/session`. A successful login creates a signed `kraken_dca_session` cookie with `itsdangerous`; API writes require the CSRF token stored in that cookie. Session cookie security has already been hardened: `WEB_UI_SESSION_SECRET` is required, weak secrets are rejected, cookies default to `Secure`, and the cookie path is explicit.

The runtime dependency surface is currently small:

- `PyYAML`
- `APScheduler`
- `croniter`
- `fastapi`
- `httpx`
- `itsdangerous`
- `uvicorn`

The frontend login page currently renders a password form only.

## Target Behavior

Production authentication uses Pocket ID through app-level OIDC authorization code flow. The login page shows one primary action, `Sign in with Pocket ID`, and does not show a password field when `WEB_UI_AUTH_MODE=oidc`.

The application handles the OIDC flow itself:

1. User opens `/login`.
2. Frontend sends the browser to `/api/auth/oidc/start`.
3. Backend creates a signed temporary OIDC state cookie containing `state`, `nonce`, and optional PKCE verifier.
4. Backend redirects to Pocket ID authorization endpoint.
5. Pocket ID redirects back to `/api/auth/oidc/callback`.
6. Backend validates state, exchanges the code for tokens, validates the ID token or userinfo response, checks the allowed group, creates the existing application session cookie, clears the temporary OIDC state cookie, and redirects to `/`.

The temporary OIDC state cookie must use `HttpOnly`, `Secure`, `SameSite=Lax`, a short max age, and `Path=/api/auth/oidc`. It must not use the existing `SameSite=Strict` application session cookie semantics because the Pocket ID callback is a cross-site navigation and needs the state cookie to be sent back to the application.

Existing protected APIs continue to use `auth.require_authenticated_session()` and `auth.require_csrf()`. The rest of the application should not need to know whether the session came from password auth or OIDC auth.

## Configuration

Production uses:

```env
WEB_UI_AUTH_MODE=oidc
WEB_UI_OIDC_ISSUER=https://pocketid.example.com
WEB_UI_OIDC_CLIENT_ID=...
WEB_UI_OIDC_CLIENT_SECRET=...
WEB_UI_OIDC_REDIRECT_URL=https://kraken-dca.example.com/api/auth/oidc/callback
WEB_UI_OIDC_ALLOWED_GROUP=kraken-dca-admins
WEB_UI_SESSION_SECRET=...
WEB_UI_COOKIE_SECURE=true
```

Local development and tests may use:

```env
WEB_UI_AUTH_MODE=password
WEB_UI_PASSWORD=secret
WEB_UI_SESSION_SECRET=...
WEB_UI_COOKIE_SECURE=false
```

`password` mode must not be the production default. If `WEB_UI_AUTH_MODE` is omitted, startup should fail with a clear error rather than silently falling back to password auth. This prevents accidental production deployment with password login.

## Authorization

The first production authorization rule is group-based:

- Required claim: `groups`
- Required value: `kraken-dca-admins`

Users missing the group are rejected during callback and do not receive an application session cookie. The callback should return a controlled error/redirect, not a traceback, and it should clear the temporary OIDC state cookie.

The implementation should avoid auto-provisioning local users. Kraken DCA currently has no user database, so the only durable authorization boundary is the Pocket ID group claim plus the app session cookie.

## Dependency Approach

Do not hand-roll JWT/OIDC validation. OIDC validation must verify at least:

- issuer (`iss`)
- audience (`aud`)
- expiration (`exp`)
- nonce
- signature via Pocket ID JWKS
- allowed group claim

Use a maintained OIDC/JWT helper library if needed, but keep the addition narrow and documented. `httpx` already exists in runtime and can be reused for discovery, token exchange, JWKS/userinfo fetches, and tests with `MockTransport`.

Do not store OIDC tokens in the `itsdangerous` application cookie. The cookie is signed but not encrypted. The app session may store only low-risk identity metadata needed for authorization and debugging, such as `sub`, `email`, `groups`, `auth_mode`, `csrf_token`, `created_at`, and `reauth_after`.

## Error Handling

Startup errors should be explicit:

- missing or unknown `WEB_UI_AUTH_MODE`
- missing OIDC issuer/client/secret/redirect/group when OIDC mode is selected
- password mode missing `WEB_UI_PASSWORD` when password mode is selected

Runtime OIDC errors should not leak tokens or provider responses. Callback failures should clear the OIDC temporary state cookie and redirect to `/login?error=oidc` or return the existing JSON error envelope for API callers.

OIDC sessions need an absolute freshness boundary. The current middleware refreshes app cookies on successful authenticated requests, so the OIDC session payload must carry a `created_at` or `reauth_after` timestamp. Once expired, the app should require a fresh Pocket ID login instead of extending the local session forever. This keeps group removals in Pocket ID from being bypassed indefinitely by the app's sliding cookie refresh.

## Testing

Backend tests must cover:

- OIDC mode does not require `WEB_UI_PASSWORD`
- password login endpoint is disabled in OIDC mode
- password mode still works for tests/local development
- `/api/auth/oidc/start` redirects to provider and sets signed temporary state
- callback rejects missing/tampered state
- callback rejects token/userinfo without allowed group
- callback accepts valid OIDC identity with allowed group and creates the existing session cookie
- callback and session restore reject expired OIDC local session freshness
- logout clears both app session and temporary OIDC cookies

Frontend tests must cover:

- OIDC mode login screen shows only the Pocket ID button
- password mode login screen still supports the password form for local/test mode

Runtime verification must include:

- full backend test suite
- frontend tests and build
- Docker/runtime dependency guard tests
- GitNexus impact/detect before commit
- Coolify deployment with masked OIDC secret values
- external `GET /login` and `GET /api/session`

## Deployment Notes

Pocket ID must have an OIDC client configured with callback:

```text
https://kraken-dca.example.com/api/auth/oidc/callback
```

The app must be served over HTTPS in production. Keep `WEB_UI_COOKIE_SECURE=true` behind Coolify/Traefik. The Pocket ID client secret and app session secret must be configured in Coolify as runtime secrets, not build-time values.

## References

- Pocket ID is an OIDC provider focused on passkey authentication.
- Pocket ID OIDC clients provide client ID, client secret, and callback configuration.
- Linkding's OIDC model uses an app-level OIDC button and can disable the password login form for OIDC-only authentication.

Reference URLs:

- https://pocket-id.org/docs/introduction
- https://pocket-id.org/docs/guides/oidc-client-authentication
- https://pocket-id.org/docs/client-examples/linkding
- https://linkding.link/options/
