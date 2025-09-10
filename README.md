# Ledger Lift — Monorepo (v0.1.0)

A production‑grade scaffold for **PDF→Excel data book** extraction workflows.

## Quickstart (Local Dev)

```bash
# 1) Infra: Postgres, MinIO, LocalStack
docker-compose up -d

# 2) Install JS deps
pnpm -w install

# 3) API
cd apps/api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4) Web
cd ../../apps/web && pnpm dev
```

API: http://localhost:8000  
Web: http://localhost:3000

## Environments

Copy env samples and adjust as needed:

```
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env
cp apps/worker/.env.example apps/worker/.env
```

### Netlify

#### Production Deployment

1. Connect repo to Netlify
2. Set build:
   - **Base directory**: `.`
   - **Build command**: `pnpm -w install && pnpm --filter web build`
   - **Publish directory**: `apps/web/.next`
3. Set environment variables:
   - `NEXT_PUBLIC_API_URL=https://<your-api-domain>`
   - `NETLIFY_AUTH_TOKEN` (for GitHub Actions)
   - `NETLIFY_SITE_ID` (for GitHub Actions)

#### PR Preview Deployments

The repository includes automatic PR preview deployments via GitHub Actions:

1. **Required Secrets** (set in GitHub repository settings):
   - `NETLIFY_AUTH_TOKEN` - Your Netlify personal access token
   - `NETLIFY_SITE_ID` - Your Netlify site ID
   - `NEXT_PUBLIC_API_URL` - API URL for previews (optional)

2. **How it works**:
   - Every PR automatically triggers a preview deployment
   - Preview URL is commented on the PR
   - Previews are updated when new commits are pushed
   - Previews are cleaned up when PR is closed

3. **Branch Protection** (recommended):
   - Enable "Require status checks to pass before merging"
   - Add required checks: `Web CI`, `Python CI`, `E2E` (optional)
   - Enable "Require branches to be up to date before merging"

### GitHub

```bash
git init
git remote add origin https://github.com/ZaBrisket/Ledger.Lift
git add .
git commit -m "chore: seed ledger-lift v0.1.0"
git branch -M main
git push -u origin main
```

## Services

- **Web**: Next.js 14 (App Router) + TypeScript + React Query + MUI Data Grid
- **API**: FastAPI (Python 3.11). Endpoints:
  - `GET /healthz`
  - `POST /v1/uploads/presign` → returns S3 (MinIO) pre‑signed PUT URL (local dev)
  - `POST /v1/documents` → persists a document record
  - `GET /v1/documents` → list documents with pagination
  - `GET /v1/documents/{id}/artifacts` → get document artifacts
  - `GET /v1/documents/{id}/previews` → get document preview images
  - `GET /v1/documents/{id}/export.xlsx` → export document to Excel
  - `DELETE /v1/documents/{id}` → delete document and all S3 objects
- **Worker**: Typer CLI with PyMuPDF, OCR, and table extraction pipelines

## Database Migrations

The API uses Alembic for database schema management.

### Development Commands

```bash
# Create a new migration
cd apps/api
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>

# Show current revision
alembic current

# Show migration history
alembic history
```

### Production Deployment

Migrations are automatically applied when the API container starts:

```bash
docker-compose up api
```

This runs `alembic upgrade head` before starting the API server.

## AWS Configuration

The application supports both local development (MinIO/LocalStack) and production AWS services via the `USE_AWS` environment flag.

### Local Development (Default)
- Uses MinIO for S3-compatible storage
- Uses LocalStack for SQS
- No AWS credentials required

### Production AWS
Set `USE_AWS=true` and configure AWS credentials:

```bash
# Required AWS credentials
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Optional: SQS queue name
SQS_QUEUE_NAME=ledger-lift-prod
```

The application will automatically use the appropriate S3 and SQS endpoints based on the `USE_AWS` setting.

## Observability (OpenTelemetry)

The application includes OpenTelemetry instrumentation for tracing and metrics collection.

### Setup

Set the following environment variables to enable telemetry:

```bash
# Required for telemetry
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=ledger-lift-api  # or ledger-lift-worker
OTEL_TRACES_SAMPLER=parentbased_always_on
```

### Local Development with Grafana/Tempo

For local development, you can use the provided docker-compose snippet:

```yaml
# Add to docker-compose.yml for local observability
services:
  tempo:
    image: grafana/tempo:latest
    ports:
      - "3200:3200"  # tempo
      - "4317:4317"  # otlp grpc
    command: [ "-config.file=/etc/tempo.yaml" ]
    volumes:
      - ./tempo.yaml:/etc/tempo.yaml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"  # grafana (different port to avoid conflict with web)
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-storage:/var/lib/grafana

volumes:
  grafana-storage:
```

### Metrics

The application exposes the following custom metrics:

**API Metrics:**
- `api_requests_total` - Total API requests
- `api_request_duration_ms` - Request duration histogram
- `api_errors_total` - Total API errors

**Worker Metrics:**
- `worker_documents_processed_total` - Documents processed
- `worker_render_time_ms` - Document rendering time
- `worker_extract_time_ms` - Table extraction time
- `worker_ocr_pages_processed_total` - Pages processed with OCR
- `worker_ocr_mean_confidence` - OCR confidence scores

### Traces

All major operations are traced with spans for:
- API request handling
- Database operations
- S3 operations
- Worker document processing
- Table extraction
- OCR processing

## Security & Ops (baseline)

- CORS restricted via env, least‑privileged S3 creds
- Structured logging, basic health checks
- CI: GitHub Actions (Node + Python), caches deps
- Dockerized local dev: Postgres, MinIO, LocalStack (SQS stub)

### Security Features

**Data Protection:**
- Optional KMS encryption for S3 uploads (`S3_KMS_KEY_ID`)
- Configurable presigned URL TTL (`PRESIGN_TTL_SECONDS`, default 900s)
- Document purge endpoint (`DELETE /v1/documents/{id}`) for compliance

**Access Control:**
- CORS restrictions via environment configuration
- Least-privileged S3 credentials
- Signed URLs with expiration for secure access

**Data Retention:**
- Complete document deletion removes all S3 objects and database records
- Cascade deletion handles artifacts and related data
- Best-effort cleanup with error logging

**Threat Model:**
- **Data at Rest**: Protected by S3 encryption (AES-256 or KMS)
- **Data in Transit**: HTTPS/TLS for all API communications
- **Access Control**: Time-limited presigned URLs prevent unauthorized access
- **Data Lifecycle**: Complete purge capability for compliance requirements

Apache‑2.0 License.
