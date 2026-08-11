"""OpenID Connect authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from krakendca.web import auth
from krakendca.web import oidc
from krakendca.web.schemas import ApiException

router = APIRouter(prefix="/api/auth/oidc", tags=["oidc"])

_OIDC_STATE_MAX_LENGTH = 256
_OIDC_CODE_MAX_LENGTH = 4096


@router.get("/start")
async def start(request: Request):
    if request.app.state.auth_mode != "oidc":
        raise ApiException(404, "not_found", "OIDC login is not enabled.")

    auth.require_oidc_start_allowed(request)
    auth.record_oidc_start(request)

    state = oidc.new_state()
    nonce = oidc.new_state()
    signer: URLSafeTimedSerializer = request.app.state.oidc_state_serializer
    cookie = signer.dumps({"state": state, "nonce": nonce})
    config: oidc.OidcConfig = request.app.state.oidc_config

    response = RedirectResponse(oidc.authorization_url(config, state, nonce))
    response.set_cookie(
        oidc.OIDC_STATE_COOKIE_NAME,
        cookie,
        max_age=oidc.OIDC_STATE_MAX_AGE_SECONDS,
        httponly=True,
        path="/api/auth/oidc",
        samesite="lax",
        secure=request.app.state.cookie_secure,
    )
    return response


@router.get("/callback")
async def callback(request: Request):
    if request.app.state.auth_mode != "oidc":
        raise ApiException(404, "not_found", "OIDC login is not enabled.")

    auth.require_oidc_attempt_allowed(request)

    submitted_state = request.query_params.get("state") or ""
    if not submitted_state or len(submitted_state) > _OIDC_STATE_MAX_LENGTH:
        return _failure_response(request, clear_state=False)

    pending = _pending_state(request)
    if pending is None or pending.get("state") != submitted_state:
        return _failure_response(request, clear_state=False)

    if request.query_params.get("error"):
        return _failure_response(request)

    code = request.query_params.get("code") or ""
    if not code or len(code) > _OIDC_CODE_MAX_LENGTH:
        return _failure_response(request)

    try:
        identity = await request.app.state.oidc_client.authenticate(
            code,
            str(pending["nonce"]),
        )
    except oidc.EXPECTED_AUTH_EXCEPTIONS:
        return _failure_response(request)

    config: oidc.OidcConfig = request.app.state.oidc_config
    if config.allowed_group not in identity.groups:
        return _failure_response(request)

    csrf_token = auth.new_csrf_token()
    response = RedirectResponse("/")
    auth.set_session_cookie(
        request,
        response,
        csrf_token,
        oidc.session_payload(identity),
    )
    _clear_state_cookie(request, response)
    auth.record_oidc_success(request)
    return response


def _pending_state(request: Request) -> dict | None:
    cookie = request.cookies.get(oidc.OIDC_STATE_COOKIE_NAME)
    if not cookie:
        return None

    signer: URLSafeTimedSerializer = request.app.state.oidc_state_serializer
    try:
        payload = signer.loads(
            cookie,
            max_age=oidc.OIDC_STATE_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return None

    if not payload.get("state") or not payload.get("nonce"):
        return None
    return payload


def _failure_response(
    request: Request,
    clear_state: bool = True,
) -> RedirectResponse:
    auth.record_oidc_failure(request)
    response = RedirectResponse("/login?error=oidc")
    if clear_state:
        _clear_state_cookie(request, response)
    return response


def _clear_state_cookie(request: Request, response: RedirectResponse) -> None:
    response.delete_cookie(
        oidc.OIDC_STATE_COOKIE_NAME,
        httponly=True,
        path="/api/auth/oidc",
        samesite="lax",
        secure=request.app.state.cookie_secure,
    )
