"""Small response helpers for the web API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
