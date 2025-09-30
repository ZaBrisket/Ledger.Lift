import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[2]))
sys.path.append(str(Path(__file__).resolve().parents[3]))

"""SSE streaming tests."""
import asyncio
import json
from collections import defaultdict, deque

import pytest
from fastapi import HTTPException

from app.progress import PROGRESS_CHANNEL, PROGRESS_KEY_TEMPLATE
from apps.api.config import settings
from apps.api.app.routes.jobs_events import job_events
from apps.api.services.progress_pubsub import stream_job_events


class FakePubSub:
    def __init__(self, redis):
        self._redis = redis
        self._queue = deque()
        self._channel = None

    def subscribe(self, channel):
        self._channel = channel
        self._redis.register_subscriber(channel, self._queue)

    def get_message(self, ignore_subscribe_messages=True):
        if self._queue:
            data = self._queue.popleft()
            return {"type": "message", "data": data}
        return None

    def close(self):
        if self._channel:
            self._redis.unregister_subscriber(self._channel, self._queue)


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.lists = defaultdict(deque)
        self.channels = defaultdict(list)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def publish(self, channel, message):
        for queue in list(self.channels[channel]):
            queue.append(message)

    def lpush(self, key, value):
        self.lists[key].appendleft(str(value))

    def ltrim(self, key, start, end):
        sliced = deque()
        for idx, value in enumerate(self.lists[key]):
            if start <= idx <= end:
                sliced.append(value)
        self.lists[key] = sliced

    def lrange(self, key, start, end):
        values = list(self.lists[key])
        if end == -1:
            end = len(values) - 1
        return values[start : end + 1]

    def pubsub(self, ignore_subscribe_messages=True):
        return FakePubSub(self)

    def register_subscriber(self, channel, queue):
        self.channels[channel].append(queue)

    def unregister_subscriber(self, channel, queue):
        if queue in self.channels[channel]:
            self.channels[channel].remove(queue)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("apps.api.infra.redis.get_redis_connection", lambda url=None: fake)
    monkeypatch.setattr("apps.api.services.progress_pubsub.get_redis_connection", lambda url=None: fake)
    return fake


@pytest.mark.anyio("asyncio")
async def test_sse_streams_progress_events(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "features_t1_sse", True)
    job_id = "job-123"
    key = PROGRESS_KEY_TEMPLATE.format(job_id=job_id)
    initial = json.dumps({"job_id": job_id, "state": "queued"})
    fake_redis.setex(key, 60, initial)

    class DummyRequest:
        async def is_disconnected(self):
            return False

    response = await stream_job_events(DummyRequest(), job_id)
    assert response.headers["X-P95-JOB-MS"] == str(settings.sse_edge_budget_ms)

    iterator = response.body_iterator
    first_chunk = await asyncio.wait_for(iterator.__anext__(), timeout=1.0)
    assert b"event: progress" in first_chunk
    assert b"queued" in first_chunk

    payload = json.dumps({"job_id": job_id, "state": "completed", "duration": 1.5})
    fake_redis.publish(PROGRESS_CHANNEL, payload)

    chunk = await asyncio.wait_for(iterator.__anext__(), timeout=1.0)
    assert b"completed" in chunk
    await iterator.aclose()


@pytest.mark.anyio("asyncio")
async def test_sse_disabled_returns_404(monkeypatch):
    monkeypatch.setattr(settings, "features_t1_sse", False)

    class DummyRequest:
        pass

    with pytest.raises(HTTPException) as exc:
        await job_events(DummyRequest(), "foo")
    assert exc.value.status_code == 404
