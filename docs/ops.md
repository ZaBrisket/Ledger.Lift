# Ledger Lift Queue Operations

## Environment Flags

Set the following environment variables for both API and worker services:

| Variable | Default | Description |
| --- | --- | --- |
| `FEATURES_T1_QUEUE` | `true` | Enables the Redis/RQ based pipeline. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis instance used for queues, pub/sub, and metrics. |
| `RQ_HIGH_QUEUE`/`RQ_DEFAULT_QUEUE`/`RQ_LOW_QUEUE` | `high`/`default`/`low` | Priority queues. |
| `RQ_DLQ` | `dead` | Dead-letter queue name. |
| `WORKER_CONCURRENCY` | `2` | RQ worker concurrency hint. |
| `REDIS_MAX_RETRIES` | `3` | Maximum retry attempts per job. |
| `PARSE_TIMEOUT_MS` | `300000` | Parser timeout used by worker jobs. |
| `METRICS_AUTH` | _unset_ | Optional `user:password` for basic auth protecting `/metrics`. |

## Running RQ Workers

The worker CLI exposes helpers for launching workers and inspecting queues. A basic systemd unit or container entrypoint can run:

```bash
cd apps/worker
uvicorn apps.worker.worker.metrics_server:metrics_app --host 0.0.0.0 --port 9101 &
rq worker --url "$REDIS_URL" "$RQ_HIGH_QUEUE" "$RQ_DEFAULT_QUEUE" "$RQ_LOW_QUEUE"
```

Use the `queue-document` command for manual testing:

```bash
cd apps/worker
python -m worker.cli queue-document <document-id> --priority high
```

## Metrics

Both API and worker expose `/metrics` endpoints publishing Prometheus counters, gauges, and histograms for queue depth, worker utilisation, and job durations. Set `METRICS_AUTH="user:pass"` to require basic authentication.

## Emergency Stop

Creating the Redis key `EMERGENCY_STOP` halts new work immediately and causes workers to gracefully exit their next checkpoint. Remove the key to resume processing.

```bash
redis-cli set EMERGENCY_STOP 1
# ... later ...
redis-cli del EMERGENCY_STOP
```

## Dead Letter Queue

Jobs that exceed `REDIS_MAX_RETRIES` are re-published to the `RQ_DLQ` queue with the failure context stored in job metadata and published via the `jobs:progress` channel. Inspect the queue with:

```bash
rq info --url "$REDIS_URL" "$RQ_DLQ"
```
