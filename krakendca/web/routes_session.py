"""Session API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from krakendca.web import auth
from krakendca.web import oidc
from krakendca.web.schemas import ApiException, json_object_body, ok

router = APIRouter(prefix="/api/session", tags=["session"])


@router.post("")
async def login(request: Request):
    if request.app.state.auth_mode != "password":
        raise ApiException(404, "not_found", "Password login is not enabled.")

    auth.require_login_allowed(request)
    try:
        payload = await json_object_body(request)
        password = payload.get("password")
        expected = request.app.state.web_ui_password
        if not isinstance(password, str) or not auth.verify_password(
            password, expected
        ):
            auth.record_login_failure(request)
            raise ApiException(401, "unauthenticated", "Invalid password.")

        auth.record_login_success(request)
    finally:
        auth.release_login_attempt(request)

    csrf_token = auth.new_csrf_token()
    response = ok({"authenticated": True, "csrf_token": csrf_token})
    auth.set_session_cookie(
        request,
        response,
        csrf_token,
    )
    return response


@router.get("")
async def current_session(request: Request):
    session = auth.decode_session(request)
    if session is None:
        return ok(_session_response(request, authenticated=False))

    csrf_token = auth.new_csrf_token()
    response = ok(
        _session_response(
            request,
            authenticated=True,
            csrf_token=csrf_token,
        )
    )
    auth.set_session_cookie(
        request,
        response,
        csrf_token,
        oidc.session_refresh_payload(session),
    )
    return response


@router.delete("")
async def logout(request: Request):
    auth.require_csrf(request)
    response = ok({"authenticated": False})
    response.delete_cookie(
        auth.COOKIE_NAME,
        httponly=True,
        path="/",
        samesite="strict",
        secure=request.app.state.cookie_secure,
    )
    return response


def _session_response(
    request: Request,
    authenticated: bool,
    csrf_token: str | None = None,
) -> dict:
    data = {
        "authenticated": authenticated,
        "auth_mode": request.app.state.auth_mode,
    }
    if request.app.state.auth_mode == "oidc":
        data["oidc_login_url"] = "/api/auth/oidc/start"
    if csrf_token is not None:
        data["csrf_token"] = csrf_token
    return data
