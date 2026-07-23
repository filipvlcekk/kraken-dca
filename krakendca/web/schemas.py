"""Small response helpers for the web API."""

from __future__ import annotations

from datetime import datetime
from json import JSONDecodeError
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiException(Exception):
    """Exception converted to the API error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        fields: dict[str, str] | None = None,
        details: Any | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.details = details


def ok(data: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data}, status_code=status_code)


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    fields: dict[str, str] | None = None,
    details: Any | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if fields is not None:
        error["fields"] = fields
    if details is not None:
        error["details"] = details
    return JSONResponse({"ok": False, "error": error}, status_code=status_code)


async def json_object_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except JSONDecodeError as exc:
        raise ApiException(
            400,
            "validation_error",
            "Request body must be valid JSON.",
            fields={"body": "Request body must be valid JSON."},
        ) from exc

    if not isinstance(payload, dict):
        raise ApiException(
            400,
            "validation_error",
            "Request body must be a JSON object.",
            fields={"body": "Request body must be a JSON object."},
        )
    return payload


def serialize_run_result(result: Any) -> dict[str, Any]:
    return {
        "pair": result.pair,
        "status": result.status,
        "reason": result.reason,
        "started_at": _serialize_datetime(result.started_at),
        "finished_at": _serialize_datetime(result.finished_at),
        "order_txid": result.order_txid,
        "message": result.message,
    }


def serialize_scheduler_status(status: dict[str, Any] | None) -> dict[str, Any]:
    normalized = {
        "running": False,
        "config_applied": False,
        "saved_config_fingerprint": None,
        "active_config_fingerprint": None,
        "reload_error": None,
        "last_reload_at": None,
        "jobs": [],
    }
    if status:
        normalized.update(status)
    if normalized["jobs"] is None:
        normalized["jobs"] = []
    return _serialize_value(normalized)


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value
