"""FastAPI application factory for web mode."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from yaml import YAMLError

from krakendca import config_store
from krakendca.scheduler import SchedulerService
from krakendca.web import auth
from krakendca.web.routes_config import router as config_router
from krakendca.web.routes_scheduler import router as scheduler_router
from krakendca.web.routes_session import router as session_router
from krakendca.web.schemas import ApiException, error_response
from krakendca.web.static import static_response


def create_app(
    config_path: str = "/app/config.yaml",
    static_dir: str = "/app/frontend",
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        password = auth.require_web_password()
        app.state.web_ui_password = password
        app.state.session_serializer = auth.serializer(auth.session_secret(password))
        app.state.cookie_secure = auth.cookie_secure()
        app.state.scheduler = None
        app.state.config_response = _build_config_response(config_path)
        app.state.build_config_response = lambda: _build_config_response(config_path)
        app.state.reload_scheduler = lambda config: _reload_scheduler(app, config)

        if app.state.config_response["config_valid"]:
            scheduler = SchedulerService(config_path)
            scheduler.start()
            app.state.scheduler = scheduler

        try:
            yield
        finally:
            scheduler = app.state.scheduler
            if scheduler is not None:
                scheduler.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.state.config_path = config_path
    app.state.static_dir = static_dir

    app.add_exception_handler(ApiException, _api_exception_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)

    app.include_router(session_router)
    app.include_router(config_router)
    app.include_router(scheduler_router)

    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def unknown_api(path: str, request: Request):
        del path
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            auth.require_csrf(request)
        else:
            auth.require_authenticated_session(request)
        return error_response(404, "not_found", "API endpoint not found.")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str, request: Request):
        return static_response(path, request)

    return app


def _build_config_response(config_path: str) -> dict[str, Any]:
    try:
        loaded = config_store.load_config(config_path)
    except FileNotFoundError:
        return {
            "config": {},
            "secrets": _empty_secrets(),
            "config_valid": False,
            "validation_errors": {"config": "Config file not found."},
            "raw_yaml": None,
        }
    except YAMLError as exc:
        return {
            "config": {},
            "secrets": _empty_secrets(),
            "config_valid": False,
            "validation_errors": {"config": str(exc)},
            "raw_yaml": None,
        }

    try:
        normalized = config_store.validate_config(loaded)
    except config_store.ConfigValidationError as exc:
        redacted = config_store.redact_config(loaded)
        return {
            "config": redacted["config"],
            "secrets": redacted["secrets"],
            "config_valid": False,
            "validation_errors": exc.fields,
            "raw_yaml": None,
        }

    redacted = config_store.redact_config(normalized)
    return {
        "config": redacted["config"],
        "secrets": redacted["secrets"],
        "config_valid": True,
        "validation_errors": {},
        "raw_yaml": None,
    }


def _reload_scheduler(app: FastAPI, config: dict) -> dict:
    scheduler = app.state.scheduler
    if scheduler is None:
        scheduler = SchedulerService(app.state.config_path)
        scheduler.start()
        app.state.scheduler = scheduler
        status = scheduler.status()
    else:
        status = scheduler.reload(config)

    if not status.get("config_applied", False) or status.get("reload_error"):
        raise RuntimeError("Scheduler did not apply the saved config.")
    return status


def _empty_secrets() -> dict:
    return {
        "public_key": {"configured": False, "source": None},
        "private_key": {"configured": False, "source": None},
    }


async def _api_exception_handler(
    _request: Request,
    exc: ApiException,
) -> JSONResponse:
    return error_response(
        exc.status_code,
        exc.code,
        exc.message,
        fields=exc.fields,
        details=exc.details,
    )


async def _http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    return error_response(exc.status_code, "http_error", str(exc.detail))


async def _validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return error_response(400, "validation_error", str(exc))


app = create_app()
