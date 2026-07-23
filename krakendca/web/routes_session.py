"""Session API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from krakendca.web import auth
from krakendca.web.schemas import ApiException, json_object_body, ok

router = APIRouter(prefix="/api/session", tags=["session"])


@router.post("")
async def login(request: Request):
    payload = await json_object_body(request)
    password = payload.get("password")
    expected = request.app.state.web_ui_password
    if not isinstance(password, str) or not auth.verify_password(password, expected):
        raise ApiException(401, "unauthenticated", "Invalid password.")

    csrf_token = auth.new_csrf_token()
    response = ok({"authenticated": True, "csrf_token": csrf_token})
    auth.set_session_cookie(request, response, csrf_token)
    return response


@router.get("")
async def current_session(request: Request):
    session = auth.decode_session(request)
    if session is None:
        return ok({"authenticated": False})

    csrf_token = auth.new_csrf_token()
    response = ok({"authenticated": True, "csrf_token": csrf_token})
    auth.set_session_cookie(request, response, csrf_token)
    return response


@router.delete("")
async def logout(request: Request):
    auth.require_csrf(request)
    response = ok({"authenticated": False})
    response.delete_cookie(
        auth.COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=request.app.state.cookie_secure,
    )
    return response
