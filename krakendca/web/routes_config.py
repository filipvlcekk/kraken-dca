"""Configuration API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from yaml import YAMLError

from krakendca import config_store
from krakendca.web import auth
from krakendca.web.schemas import (
    ApiException,
    json_object_body,
    ok,
    serialize_scheduler_status,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config(request: Request):
    auth.require_authenticated_session(request)
    return ok(request.app.state.config_response)


@router.put("")
async def put_config(request: Request):
    auth.require_csrf(request)
    payload = await json_object_body(request)
    submitted = payload.get("config")
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
            fields={"config": "Existing config YAML is malformed."},
        ) from exc
    except OSError as exc:
        raise ApiException(
            500,
            "config_persistence_failed",
            "Config could not be saved.",
            details={"config_saved": False, "scheduler_reloaded": False},
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
            "scheduler": serialize_scheduler_status(scheduler_status),
        }
    )
