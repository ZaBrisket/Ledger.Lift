import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("rq")
fakeredis = pytest.importorskip("fakeredis")

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from apps.api.app.main import app
from apps.api.app.services import ServiceResult
from apps.api.config import get_api_settings, reset_api_settings_cache
from apps.api.infra import redis as api_redis
from rq.job import Job


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    reset_api_settings_cache()
    api_redis.reset_redis_cache()
    monkeypatch.setenv("FEATURES_T1_QUEUE", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    yield
    reset_api_settings_cache()
    api_redis.reset_redis_cache()


@pytest.fixture
def fake_redis(monkeypatch):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(api_redis, "get_redis_connection", lambda: client)
    return client


def _stub_document(monkeypatch, *, exists: bool = True):
    def _result(_: str) -> ServiceResult[Any]:
        if exists:
            return ServiceResult(success=True, data={"id": "doc"})
        return ServiceResult(success=False, data=None)

    monkeypatch.setattr("apps.api.app.services.DocumentService.get_document", _result)


def test_emergency_stop_blocks_processing(fake_redis, monkeypatch):
    fake_redis.set("EMERGENCY_STOP", 1)
    _stub_document(monkeypatch)

    client = TestClient(app)
    response = client.post("/v1/documents/test-doc/process")
    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "QUEUE_HALTED"


def test_enqueue_persists_metadata(fake_redis, monkeypatch):
    _stub_document(monkeypatch)

    client = TestClient(app)
    response = client.post("/v1/documents/test-doc/process")
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]

    job = Job.fetch(job_id, connection=fake_redis)
    assert job.meta["priority"] == "default"
    assert job.meta["schema_version"] == get_api_settings().schema_version
    assert job.meta["version"] == get_api_settings().work_version

    progress = fake_redis.get(f"job:{job_id}:progress")
    assert progress is not None
    payload = json.loads(progress)
    assert payload["status"] == "queued"
