import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.routes import ops


class StubQueue:
    def __init__(self, name: str, connection=None):
        self.name = name
        self._count = 3

    def count(self) -> int:  # pragma: no cover - invoked indirectly
        return self._count


class StubRegistry:
    def __init__(self, *_args, **_kwargs):
        self._count = 1

    def count(self) -> int:  # pragma: no cover - invoked indirectly
        return self._count


def test_ops_queues_returns_snapshot(monkeypatch):
    monkeypatch.setattr(ops.settings, "enable_ops_endpoints", True)
    monkeypatch.setattr(ops, "Queue", StubQueue)
    monkeypatch.setattr(ops, "StartedJobRegistry", StubRegistry)
    monkeypatch.setattr(ops, "ScheduledJobRegistry", StubRegistry)
    monkeypatch.setattr(ops, "FailedJobRegistry", StubRegistry)
    monkeypatch.setattr(ops, "FinishedJobRegistry", StubRegistry)
    monkeypatch.setattr(ops, "DeferredJobRegistry", StubRegistry)
    monkeypatch.setattr(ops, "get_redis_connection", lambda: object())
    monkeypatch.setattr(ops, "is_emergency_stopped", lambda _conn: False)

    client = TestClient(app)
    response = client.get("/ops/queues")

    assert response.status_code == 200
    body = response.json()
    assert "queues" in body
    assert len(body["queues"]) == 4
    assert body["queues"][0]["size"] == 3
    assert body["emergency_stop"] is False
    assert "timestamp" in body


def test_ops_queues_returns_403_when_disabled(monkeypatch):
    monkeypatch.setattr(ops.settings, "enable_ops_endpoints", False)

    client = TestClient(app)
    response = client.get("/ops/queues")

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "OPS_ACCESS_FORBIDDEN"
