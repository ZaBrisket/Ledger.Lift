import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api.app.jobs import JobPayload, SCHEMA_VERSION, JOB_VERSION
from apps.api.app.main import app
from apps.api.app.progress import PROGRESS_KEY_TEMPLATE, write_progress_snapshot
from apps.api.config import settings as api_settings
from apps.api.metrics import (
    JOB_ENQUEUED,
    JOB_ENQUEUE_FAILURES,
    JOB_PROGRESS_UPDATES,
    record_enqueue,
    record_enqueue_failure,
)


class InMemoryRedis:
    def __init__(self):
        self._store: dict[str, bytes] = {}
        self.published: list[tuple[str, str]] = []
        self._flags: set[str] = set()

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self._store[key] = value.encode()

    def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))

    def get(self, key: str):
        return self._store.get(key)

    def exists(self, key: str) -> bool:
        return key in self._flags

    def set_flag(self, key: str) -> None:
        self._flags.add(key)


def _metric_value(metric, **labels):
    for sample in metric.collect()[0].samples:
        if all(sample.labels.get(k) == v for k, v in labels.items()):
            return sample.value
    return 0


def test_job_payload_structure_contains_versions():
    payload = JobPayload(document_id="doc-123", priority="high", user_id="alice")
    data = payload.to_dict()

    assert data["schema_version"] == SCHEMA_VERSION
    assert data["version"] == JOB_VERSION
    assert data["priority"] == "high"
    assert data["user_id"] == "alice"
    assert "created_at" in data

    meta = payload.redis_metadata()
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["version"] == JOB_VERSION


def test_progress_snapshot_persists_and_publishes():
    connection = InMemoryRedis()
    payload = JobPayload(document_id="doc-456", priority="default", user_id=None)
    key = PROGRESS_KEY_TEMPLATE.format(job_id=payload.job_id)

    before = _metric_value(JOB_PROGRESS_UPDATES, state="queued")
    snapshot = write_progress_snapshot(
        payload.job_id,
        {
            "state": "queued",
            "status": "queued",
            "document_id": payload.document_id,
            "progress": 0,
        },
        connection=connection,
    )

    stored = connection.get(key)
    assert stored is not None
    payload_json = json.loads(stored.decode())
    assert payload_json["state"] == "queued"
    assert payload_json["progress"] == 0
    assert snapshot["state"] == "queued"
    assert snapshot["status"] == "queued"
    assert _metric_value(JOB_PROGRESS_UPDATES, state="queued") == before + 1
    assert connection.published  # ensure publish called


def test_enqueue_metrics_increment():
    before_success = _metric_value(JOB_ENQUEUED, queue="default", priority="default")
    before_failure = _metric_value(JOB_ENQUEUE_FAILURES, queue="default")

    record_enqueue("default", "default")
    record_enqueue_failure("default")

    assert _metric_value(JOB_ENQUEUED, queue="default", priority="default") == before_success + 1
    assert _metric_value(JOB_ENQUEUE_FAILURES, queue="default") == before_failure + 1


@pytest.fixture
def api_client():
    return TestClient(app)


def test_trigger_document_processing_enqueues_job(monkeypatch, api_client):
    redis = InMemoryRedis()

    def stub_get_document(doc_id: str):
        return SimpleNamespace(success=True, data=object())

    class StubJob:
        def __init__(self, job_id: str, origin: str):
            self.id = job_id
            self.origin = origin

    def stub_enqueue(*args, **kwargs):
        metadata = kwargs.get("metadata") or {}
        assert metadata.get("schema_version") == SCHEMA_VERSION
        assert metadata.get("version") == JOB_VERSION
        return StubJob(kwargs.get("job_id", "job-1"), "default")

    for target in (
        "apps.api.infra.redis.get_redis_connection",
        "apps.api.app.routes.processing.get_redis_connection",
    ):
        monkeypatch.setattr(target, lambda: redis)

    for target in (
        "apps.api.infra.redis.is_emergency_stopped",
        "apps.api.app.routes.processing.is_emergency_stopped",
    ):
        monkeypatch.setattr(target, lambda *_: False)

    monkeypatch.setattr(
        "apps.api.app.routes.processing.DocumentService.get_document",
        lambda doc_id: stub_get_document(doc_id),
    )
    monkeypatch.setattr("apps.worker.queues.enqueue_with_retry", stub_enqueue)
    monkeypatch.setattr(
        "apps.api.app.routes.processing.enqueue_with_retry", stub_enqueue
    )

    before = _metric_value(JOB_ENQUEUED, queue="default", priority="default")

    response = api_client.post("/v1/documents/doc-123/process")

    assert response.status_code == 200
    key = PROGRESS_KEY_TEMPLATE.format(job_id=response.json()["task_id"])
    stored = redis.get(key)
    assert stored is not None
    progress_data = json.loads(stored.decode())
    assert progress_data["progress"] == 0
    assert progress_data["status"] == "queued"
    assert _metric_value(JOB_ENQUEUED, queue="default", priority="default") == before + 1


def test_trigger_document_processing_emergency_stop(monkeypatch, api_client):
    redis = InMemoryRedis()
    redis.set_flag(api_settings.emergency_stop_key)

    def stub_get_document(doc_id: str):
        return SimpleNamespace(success=True, data=object())

    for target in (
        "apps.api.infra.redis.get_redis_connection",
        "apps.api.app.routes.processing.get_redis_connection",
    ):
        monkeypatch.setattr(target, lambda: redis)

    for target in (
        "apps.api.infra.redis.is_emergency_stopped",
        "apps.api.app.routes.processing.is_emergency_stopped",
    ):
        monkeypatch.setattr(target, lambda *_: True)

    monkeypatch.setattr(
        "apps.api.app.routes.processing.DocumentService.get_document",
        lambda doc_id: stub_get_document(doc_id),
    )

    response = api_client.post("/v1/documents/doc-123/process")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "EMERGENCY_STOP"
