# Ledger Lift Architecture Notes

## Financial Schedule Detection
- Worker now includes a structural scoring detector that combines column stability, numeric density gradients, indentation depth, periodized headers, and total-row recognition.
- Text markers (revenue, EBITDA, COGS, etc.) are blended with structural features for a composite score; low-confidence tables are tagged for manual review.
- Optional ML mode (`FEATURES_T1_FINANCIAL_ML`) will train a cached logistic regression model from fixtures when enabled.

## Streaming Progress Events
- FastAPI exposes `GET /api/jobs/{job_id}/events` for SSE-based progress updates.
- Redis pub/sub drives `event: progress` payloads with periodic keep-alives to avoid idle disconnects.
- `X-P95-JOB-MS` header advertises an adaptive long-poll fallback using recent job duration samples, capped by `SSE_EDGE_BUDGET_MS`.

## CAS Deduplication v1
- Worker computes both raw (`sha256_raw`) and canonical (`sha256_canonical`) hashes at ingest; canonical uses deterministic qpdf normalization when enabled (`CAS_NORMALIZE_PDF`).
- Document rows now persist both hashes; existing exports with matching hashes short-circuit processing and mark the job complete.
- CAS hits emit completion events and update processing metadata with deduplication context.
