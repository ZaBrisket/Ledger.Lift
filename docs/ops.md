# Operations Guide

## Queue Configuration

Ledger Lift uses Redis and RQ for durable work queues. Configure the following environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `FEATURES_T1_QUEUE` | `true` | Enable the durable queue path in the API. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string used by API and worker. |
| `RQ_HIGH_QUEUE` | `high` | Queue name for priority jobs. |
| `RQ_DEFAULT_QUEUE` | `default` | Queue name for normal jobs. |
| `RQ_LOW_QUEUE` | `low` | Queue name for low-priority jobs. |
| `RQ_DLQ` | `dead` | Dead letter queue hash prefix. |
| `WORKER_CONCURRENCY` | `2` | Number of worker processes to run. |
| `REDIS_MAX_RETRIES` | `3` | Default retry count for failed jobs. |
| `PARSE_TIMEOUT_MS` | `300000` | Maximum processing time for a job. |
| `METRICS_AUTH` | unset | Optional `user:password` basic auth string for `/metrics`. |
| `EMERGENCY_STOP_KEY` | `EMERGENCY_STOP` | Redis key used to halt new work. |

## Running Workers

Install dependencies from `apps/worker/pyproject.toml` and start one RQ worker per priority:

```bash
export REDIS_URL=redis://localhost:6379/0
cd apps/worker
python -m rq worker high default low --url "$REDIS_URL"
```

Set `WORKER_CONCURRENCY` to control how many worker processes you run. Jobs are durable and respect priority ordering (high → default → low).

## Dead Letter Queue

Failed jobs that exhaust retries are stored under the Redis hash `deadletter:<RQ_DLQ>`. Each entry contains job metadata and the last exception raised. Use `redis-cli HGETALL deadletter:dead` to inspect permanently failing jobs.

## Metrics

Both API and worker expose Prometheus metrics at `/metrics`. Configure `METRICS_AUTH` to protect the endpoint using HTTP basic authentication. Key metrics include:

- `ledger_lift_api_jobs_enqueued_total`
- `ledger_lift_worker_job_retries_scheduled_total`
- `ledger_lift_job_duration_seconds`
- `ledger_lift_queue_depth`

To run the worker metrics endpoint locally you can serve the lightweight ASGI app with uvicorn:

```bash
cd apps/worker
uvicorn apps.worker.metrics_server:app --host 0.0.0.0 --port 8000
```

Prometheus scrapes the worker on the configured port (default `8000` in the provided docker compose file).

## Emergency Stop

Create the Redis key defined by `EMERGENCY_STOP_KEY` to prevent new work from being accepted. Workers check the key between pipeline stages and exit gracefully when set.

## Progress Streaming

The API writes progress snapshots for each job to `job:<id>:progress` with a default TTL of one hour and publishes updates on the `jobs:progress` pub/sub channel. Downstream consumers can subscribe to provide SSE updates to clients.
