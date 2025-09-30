import base64

import pytest

from prometheus_client import CONTENT_TYPE_LATEST

from apps.worker.config import settings
from apps.worker.metrics_server import handle_metrics_request


def _header_dict(headers):
    return {name: value for name, value in headers}


def test_metrics_request_succeeds_without_auth(monkeypatch):
    original = settings.metrics_auth
    settings.metrics_auth = None
    try:
        status, headers, body = handle_metrics_request("GET", "/metrics", [])
    finally:
        settings.metrics_auth = original

    assert status == 200
    headers_dict = _header_dict(headers)
    assert headers_dict[b"content-type"] == CONTENT_TYPE_LATEST.encode("ascii")
    assert body.startswith(b"# HELP")


def test_metrics_request_requires_basic_auth(monkeypatch):
    original = settings.metrics_auth
    settings.metrics_auth = "user:pass"
    try:
        status, headers, body = handle_metrics_request("GET", "/metrics", [])
        assert status == 401
        headers_dict = _header_dict(headers)
        assert headers_dict[b"www-authenticate"] == b"Basic"

        token = base64.b64encode(b"user:pass").decode("ascii")
        status, headers, body = handle_metrics_request(
            "GET",
            "/metrics",
            [(b"authorization", f"Basic {token}".encode("ascii"))],
        )
    finally:
        settings.metrics_auth = original

    assert status == 200
    assert body.startswith(b"# HELP")


@pytest.mark.parametrize(
    "method, expected_status",
    [
        ("GET", 200),
        ("HEAD", 200),
        ("POST", 405),
    ],
)
def test_metrics_methods(method, expected_status):
    status, headers, body = handle_metrics_request(method, "/metrics", [])
    assert status == expected_status

    if method == "HEAD" and status == 200:
        assert body == b""


def test_metrics_path_not_found():
    status, headers, body = handle_metrics_request("GET", "/not-metrics", [])
    assert status == 404
    assert body == b"Not Found"
