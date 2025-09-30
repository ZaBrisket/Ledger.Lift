import json

from apps.api.app.jobs import JobPayload, SCHEMA_VERSION, JOB_VERSION
from apps.api.app.progress import PROGRESS_KEY_TEMPLATE, write_progress_snapshot
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

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self._store[key] = value.encode()

    def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))

    def get(self, key: str):
        return self._store.get(key)


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
        {"state": "queued", "document_id": payload.document_id},
        connection=connection,
    )

    stored = connection.get(key)
    assert stored is not None
    assert json.loads(stored.decode())["state"] == "queued"
    assert snapshot["state"] == "queued"
    assert _metric_value(JOB_PROGRESS_UPDATES, state="queued") == before + 1
    assert connection.published  # ensure publish called


def test_enqueue_metrics_increment():
    before_success = _metric_value(JOB_ENQUEUED, queue="default", priority="default")
    before_failure = _metric_value(JOB_ENQUEUE_FAILURES, queue="default")

    record_enqueue("default", "default")
    record_enqueue_failure("default")

    assert _metric_value(JOB_ENQUEUED, queue="default", priority="default") == before_success + 1
    assert _metric_value(JOB_ENQUEUE_FAILURES, queue="default") == before_failure + 1
