"""Scheduler API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from yaml import YAMLError

from krakendca import config_store
from krakendca.web import auth
from krakendca.web.schemas import (
    ApiException,
    ok,
    serialize_run_result,
    serialize_scheduler_status,
)

router = APIRouter(tags=["scheduler"])


@router.get("/api/scheduler")
async def get_scheduler(request: Request):
    auth.require_authenticated_session(request)
    scheduler = request.app.state.scheduler
    if scheduler is None:
        return ok(serialize_scheduler_status(None))
    return ok(serialize_scheduler_status(scheduler.status()))


@router.post("/api/scheduler/reload")
async def reload_scheduler(request: Request):
    auth.require_csrf(request)
    try:
        config = config_store.load_config(request.app.state.config_path)
        normalized = config_store.validate_config(config)
    except FileNotFoundError as exc:
        raise ApiException(
            400,
            "validation_error",
            "Config file not found.",
            fields={"config": "Config file not found."},
        ) from exc
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
            "Config YAML is malformed.",
            fields={"config": str(exc)},
        ) from exc

    try:
        status = request.app.state.reload_scheduler(normalized)
    except Exception as exc:
        raise ApiException(
            500,
            "scheduler_reload_failed",
            str(exc),
        ) from exc
    request.app.state.config_response = request.app.state.build_config_response()
    return ok({"scheduler": serialize_scheduler_status(status)})


@router.post("/api/pairs/{pair}/run")
async def run_pair(pair: str, request: Request):
    auth.require_csrf(request)
    scheduler = request.app.state.scheduler
    if scheduler is None:
        raise ApiException(
            409,
            "config_not_applied",
            "Scheduler config has not been applied.",
        )

    try:
        result = scheduler.run_pair_now(pair)
    except Exception as exc:
        raise ApiException(500, "scheduler_error", str(exc)) from exc
    serialized = serialize_run_result(result)
    if result.status in {"completed", "skipped", "success"}:
        return ok(serialized)

    reason = result.reason or result.status or "run_failed"
    raise ApiException(
        _status_for_reason(reason),
        reason,
        result.message,
        details={"result": serialized},
    )

def _status_for_reason(reason: str) -> int:
    if reason in {"conflict", "config_not_applied"}:
        return 409
    if reason in {
        "domain",
        "domain_error",
        "insufficient_funds",
        "pair_not_found",
        "duplicate_pair_config",
    }:
        return 400
    if reason in {"kraken_error", "network_error"}:
        return 502
    return 500
