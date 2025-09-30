import random

from apps.worker.metrics import DEAD_LETTER_TOTAL, QUEUE_DEPTH, WORKERS_BUSY
from apps.worker.queues import JobRegistries, compute_backoff_intervals, enqueue_with_retry


def _metric_value(metric, **labels):
    for sample in metric.collect()[0].samples:
        if all(sample.labels.get(k) == v for k, v in labels.items()):
            return sample.value
    return 0


def test_compute_backoff_intervals_is_exponential():
    rng = random.Random(42)
    intervals = compute_backoff_intervals(3, base_seconds=5, jitter_ratio=0.0, rng=rng)
    assert intervals == [5, 10, 20]


class DummyConnection:
    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}
        self.exists_called = []

    def hset(self, key: str, name: str, value: str) -> None:
        self.hashes.setdefault(key, {})[name] = value

    def exists(self, key: str) -> bool:
        self.exists_called.append(key)
        return False


class DummyJob:
    def __init__(self, job_id: str, origin: str, connection: DummyConnection, retries_left: int = 0):
        self.id = job_id
        self.origin = origin
        self.connection = connection
        self.meta: dict[str, object] = {}
        self.args = ()
        self.kwargs = {}
        self.retries_left = retries_left

    def save_meta(self):
        return None


class DummyRegistry:
    def __init__(self, count: int = 0):
        self._count = count

    def count(self) -> int:
        return self._count


def _registries(started: int = 0) -> JobRegistries:
    reg = DummyRegistry(started)
    zero = DummyRegistry(0)
    return JobRegistries(started=reg, finished=zero, failed=zero, deferred=zero, scheduled=zero)


def test_enqueue_failure_moves_to_dead_letter_and_records_metrics(monkeypatch):
    connection = DummyConnection()

    class DummyQueue:
        def __init__(self, name: str, connection=None, default_timeout=None):
            self.name = name
            self.connection = connection
            self.default_timeout = default_timeout
            self.enqueued = None
            self.jobs = []

        def enqueue(self, func, args=(), kwargs=None, job_id=None, retry=None, failure_callback=None, meta=None, description=None, result_ttl=None):
            self.enqueued = {
                "func": func,
                "kwargs": kwargs or {},
                "retry": retry,
                "failure_callback": failure_callback,
                "meta": meta or {},
            }
            job = DummyJob(job_id or "job-id", self.name, connection)
            self.jobs.append(job)
            # Simulate immediate failure and invoke callback
            failure_callback(job, ValueError, ValueError("boom"), None)
            return job

        def count(self) -> int:
            return len(self.jobs)

    monkeypatch.setattr("apps.worker.queues.Queue", DummyQueue)
    monkeypatch.setattr("apps.worker.queues.get_redis_connection", lambda: connection)
    monkeypatch.setattr("apps.worker.queues.is_emergency_stopped", lambda *_: False)
    monkeypatch.setattr("apps.worker.queues.get_job_registries", lambda name, connection=None: _registries())

    before_dead = _metric_value(DEAD_LETTER_TOTAL, queue="default")

    job = enqueue_with_retry(lambda: None, priority="default", max_retries=1)

    assert job.meta["dead_letter"] is True
    assert connection.hashes.get("deadletter:dead", {}).get(job.id)
    assert _metric_value(DEAD_LETTER_TOTAL, queue="default") == before_dead + 1


def test_enqueue_updates_queue_depth_and_worker_gauge(monkeypatch):
    connection = DummyConnection()

    class SuccessfulQueue:
        def __init__(self, name: str, connection=None, default_timeout=None):
            self.name = name
            self.connection = connection
            self.default_timeout = default_timeout
            self.jobs: list[DummyJob] = []

        def enqueue(self, func, args=(), kwargs=None, job_id=None, retry=None, failure_callback=None, meta=None, description=None, result_ttl=None):
            job = DummyJob(job_id or "job-id", self.name, connection)
            self.jobs.append(job)
            return job

        def count(self) -> int:
            return len(self.jobs)

    monkeypatch.setattr("apps.worker.queues.Queue", SuccessfulQueue)
    monkeypatch.setattr("apps.worker.queues.get_redis_connection", lambda: connection)
    monkeypatch.setattr("apps.worker.queues.is_emergency_stopped", lambda *_: False)
    monkeypatch.setattr("apps.worker.queues.get_job_registries", lambda name, connection=None: _registries(started=3))

    enqueue_with_retry(lambda: None, priority="high", max_retries=1)

    assert _metric_value(QUEUE_DEPTH, queue="high") == 1
    assert _metric_value(WORKERS_BUSY, queue="high") == 3
