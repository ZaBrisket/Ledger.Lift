"""Lightweight ASGI app that exposes worker Prometheus metrics."""
from __future__ import annotations

import base64
from typing import List, Sequence, Tuple

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from apps.worker.config import settings

HeaderList = Sequence[Tuple[bytes, bytes]]


def _parse_basic_auth(headers: HeaderList) -> str | None:
    """Return the decoded basic auth payload if provided."""

    for name, value in headers:
        if name.lower() == b"authorization" and value.startswith(b"Basic "):
            encoded = value.split(b" ", 1)[1]
            try:
                return base64.b64decode(encoded).decode("utf-8")
            except (ValueError, UnicodeDecodeError):  # pragma: no cover - defensive
                return None
    return None


def handle_metrics_request(
    method: str,
    path: str,
    headers: HeaderList,
) -> Tuple[int, List[Tuple[bytes, bytes]], bytes]:
    """Generate a Prometheus exposition response.

    This helper is kept separate from the ASGI app so that it can be unit tested
    without standing up an HTTP server.
    """

    method = method.upper()
    if path.rstrip("/") != "/metrics":
        return 404, [(b"content-type", b"text/plain; charset=utf-8")], b"Not Found"

    if method not in {"GET", "HEAD"}:
        return 405, [(b"allow", b"GET, HEAD")], b""

    if settings.metrics_auth:
        supplied = _parse_basic_auth(headers)
        if supplied != settings.metrics_auth:
            return (
                401,
                [
                    (b"www-authenticate", b"Basic"),
                    (b"content-type", b"text/plain; charset=utf-8"),
                ],
                b"Unauthorized",
            )

    payload = generate_latest()
    response_headers: List[Tuple[bytes, bytes]] = [
        (b"content-type", CONTENT_TYPE_LATEST.encode("ascii")),
        (b"content-length", str(len(payload)).encode("ascii")),
    ]
    body = payload if method == "GET" else b""
    return 200, response_headers, body


async def app(scope, receive, send):  # type: ignore[override]
    """Minimal ASGI application that serves metrics."""

    if scope["type"] != "http":  # pragma: no cover - ASGI protocol guard
        raise RuntimeError("Metrics app only handles HTTP requests")

    status, headers, body = handle_metrics_request(
        scope.get("method", "GET"),
        scope.get("path", "/"),
        scope.get("headers", ()),
    )

    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": list(headers),
        }
    )
    await send({"type": "http.response.body", "body": body})


__all__ = ["app", "handle_metrics_request"]
