"""Configuration API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from yaml import YAMLError

from krakendca import config_store
from krakendca.web import auth
from krakendca.web.schemas import ApiException, ok

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config(request: Request):
    auth.require_authenticated_session(request)
    return ok(request.app.state.config_response)


@router.put("")
async def put_config(request: Request):
    auth.require_csrf(request)
    payload = await request.json()
    submitted = payload.get("config") if isinstance(payload, dict) else None
    if not isinstance(submitted, dict):
        raise ApiException(
            400,
            "validation_error",
            "Submitted config must be an object.",
            fields={"config": "Submitted config must be an object."},
        )

    try:
        saved = config_store.save_config(request.app.state.config_path, submitted)
    except config_store.ConfigValidationError as exc:
        raise ApiException(
            400,
            "validation_error",
            str(exc),
            fields=exc.fields,
        ) from exc
    except YAMLError as exc:
        raise ApiException(
            400,
            "validation_error",
            "Existing config YAML is malformed.",
            fields={"config": str(exc)},
        ) from exc

    try:
        scheduler_status = request.app.state.reload_scheduler(saved)
    except Exception as exc:
        request.app.state.config_response = request.app.state.build_config_response()
        raise ApiException(
            500,
            "scheduler_reload_failed",
            str(exc),
            details={"config_saved": True, "scheduler_reloaded": False},
        ) from exc

    request.app.state.config_response = request.app.state.build_config_response()
    redacted = config_store.redact_config(saved)
    return ok(
        {
            "config": redacted["config"],
            "secrets": redacted["secrets"],
            "config_valid": True,
            "validation_errors": {},
            "scheduler_status": scheduler_status,
        }
    )
