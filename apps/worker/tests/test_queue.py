import sys
from pathlib import Path

import pytest

pytest.importorskip("rq")
fakeredis = pytest.importorskip("fakeredis")

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from apps.worker.config import reset_worker_settings_cache
from apps.worker.infra import redis as worker_redis
from apps.worker import metrics
from apps.worker.queues import JobEnvelope, enqueue_with_retry, route_to_dlq


@pytest.fixture(autouse=True)
def reset_worker_env(monkeypatch):
    reset_worker_settings_cache()
    worker_redis.reset_worker_redis_cache()
    monkeypatch.setenv("FEATURES_T1_QUEUE", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    yield
    reset_worker_settings_cache()
    worker_redis.reset_worker_redis_cache()


@pytest.fixture
def fake_redis(monkeypatch):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(worker_redis, "get_redis_connection", lambda: client)
    return client


def test_enqueue_with_retry_sets_metadata(fake_redis, monkeypatch):
    monkeypatch.setattr("apps.worker.queues.random.randint", lambda *_: 0)

    envelope = JobEnvelope(
        job_id=None,
        priority="high",
        user_id="user-1",
        p95_hint_ms=1234,
        content_hashes=["hash"],
        payload={"document_id": "doc"},
    )

    job = enqueue_with_retry(
        "apps.worker.worker.rq_jobs.process_document_job",
        kwargs={"document_id": "doc", "payload": envelope.serialize()},
        priority="high",
        envelope=envelope,
        max_retries=2,
    )

    assert job.meta["priority"] == "high"
    assert job.meta["max_retries"] == 2
    assert job.retry.interval == [15, 30]

    counter_value = metrics.QUEUE_ENQUEUED_TOTAL.labels(queue=job.origin)._value.get()
    assert counter_value >= 1


def test_route_to_dlq_enqueue(fake_redis, monkeypatch):
    monkeypatch.setattr("apps.worker.queues.random.randint", lambda *_: 0)

    envelope = JobEnvelope(
        job_id="job-1",
        priority="default",
        user_id=None,
        p95_hint_ms=None,
        content_hashes=[],
        payload={"document_id": "doc"},
    )

    job = enqueue_with_retry(
        "apps.worker.worker.rq_jobs.process_document_job",
        kwargs={"document_id": "doc", "payload": envelope.serialize()},
        priority="default",
        envelope=envelope,
        max_retries=1,
    )

    dead_job = route_to_dlq(job, reason="boom")
    assert dead_job.origin.endswith("dead")
    assert dead_job.meta["failed_reason"] == "boom"

    gauge_value = metrics.QUEUE_DEPTH_GAUGE.labels(queue=dead_job.origin)._value.get()
    assert gauge_value >= 1
