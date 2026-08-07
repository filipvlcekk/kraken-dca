"""OpenID Connect authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer

from krakendca.web import oidc
from krakendca.web.schemas import ApiException

router = APIRouter(prefix="/api/auth/oidc", tags=["oidc"])


@router.get("/start")
async def start(request: Request):
    if request.app.state.auth_mode != "oidc":
        raise ApiException(404, "not_found", "OIDC login is not enabled.")

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
