# Operations Runbook

## Overview
This pipeline receives PDFs, extracts financial schedules, and exports an Excel workbook.

### Storage (R2 / S3)
- Buckets/prefixes:
  - `incoming/` – raw uploaded PDFs
  - `processed/` – intermediate metadata
  - `exports/` – final Excel workbooks
- Prefer Cloudflare R2 via S3-compatible endpoint. Fallback to AWS S3 by omitting `R2_S3_ENDPOINT`.

### Error Codes
- `SIZE_LIMIT`: upload exceeds `PDF_MAX_MB`
- `NOT_PDF`: magic-bytes sniff failed (expected `%PDF-`)
- `NO_SCHEDULES`: parser did not find a schedule
- `EXTRACT_FAIL`: unhandled error

### Retry Policy
- Client retries uploads per part.
- Server-side fetches use exponential backoff (`fetchSafe`).

### Background Jobs
- `parse-and-extract-background` runs up to 15 minutes on Netlify. It updates job JSON (`jobs/<id>.json`).

### Security
- No PII or document contents logged.
- Object keys are redacted in logs.
- Enforce file-type sniffing; encrypted PDFs are rejected at parse stage.

### Observability
- Correlation ID: `x-correlation-id` header propagates into job docs.
- Logs are stored in job doc for quick inspection.
