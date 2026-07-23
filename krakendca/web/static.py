"""Static SPA route helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from krakendca.web import auth

FALLBACK_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Kraken DCA</title></head>
<body><main id="root"><h1>Kraken DCA</h1></main></body>
</html>
"""


def static_response(path: str, request: Request) -> Response:
    static_dir = Path(request.app.state.static_dir)
    normalized = path.strip("/")

    if _is_public_path(normalized):
        return _file_or_fallback(static_dir, normalized)

    if auth.decode_session(request) is None:
        return RedirectResponse("/login")
    return _file_or_fallback(static_dir, normalized)


def _is_public_path(path: str) -> bool:
    return path in {"login", "favicon.ico"} or path.startswith("assets/")


def _file_or_fallback(static_dir: Path, path: str) -> Response:
    target = static_dir / path if path else static_dir / "index.html"
    if target.is_file() and _inside_static_dir(static_dir, target):
        return FileResponse(target)

    index = static_dir / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse(FALLBACK_HTML)


def _inside_static_dir(static_dir: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(static_dir.resolve())
    except ValueError:
        return False
    return True
