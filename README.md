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
cp apps/worker/.env.example apps/worker/.env
cp apps/web/.env.example apps/web/.env
```

## AWS Configuration

For production deployment, set `USE_AWS=true` and configure:

### Required AWS Environment Variables

```bash
# API and Worker
USE_AWS=true
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name

# Optional: KMS encryption
S3_KMS_KEY_ID=arn:aws:kms:region:account:key/key-id

# Optional: Custom TTL for presigned URLs (default 900 seconds)
PRESIGN_TTL_SECONDS=900
```

### AWS Permissions Required

The IAM user/role needs these permissions:

- `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on your bucket
- `s3:ListBucket` on your bucket
- `sqs:SendMessage`, `sqs:ReceiveMessage` on your queue (if using SQS)
- `kms:Decrypt`, `kms:GenerateDataKey` on your KMS key (if using encryption)

## Database Migrations

The project uses Alembic for database schema management:

```bash
# Run migrations (automatically done in docker-compose)
cd apps/api && alembic upgrade head

# Create new migration
cd apps/api && alembic revision --autogenerate -m "description"

# Downgrade one migration
cd apps/api && alembic downgrade -1
```

## Observability

The project includes OpenTelemetry instrumentation for traces and metrics.

### Environment Variables

```bash
# Optional: Enable OpenTelemetry
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=ledger-lift-api  # or ledger-lift-worker
OTEL_TRACES_SAMPLER=parentbased_always_on
```

### Example Observability Stack

Add this to your `docker-compose.yml` for local development:

```yaml
# Uncomment for observability stack
# tempo:
#   image: grafana/tempo:2.3.0
#   command: [ "-config.file=/etc/tempo.yaml" ]
#   volumes:
#     - ./tempo.yaml:/etc/tempo.yaml
#   ports:
#     - "3200:3200"   # tempo
#     - "4317:4317"   # otlp grpc

# grafana:
#   image: grafana/grafana:10.2.0
#   ports:
#     - "3001:3000"
#   environment:
#     - GF_SECURITY_ADMIN_PASSWORD=admin
```

### Metrics Available

- `adapter_s3_used_total`: S3 adapter usage counter
- `api_request_latency_ms`: API request duration histogram
- `artifacts_emitted_total`: Artifacts created counter
- `render_pages_processed_total`: Pages rendered counter (worker)
- `ocr_pages_processed_total`: OCR pages processed counter (worker)

## Deployment

### Netlify Setup

1. **Connect Repository to Netlify**
   - Go to [Netlify](https://netlify.com) and connect your GitHub repository
   - Set build command: `cd apps/web && npm ci && npm run build`
   - Set publish directory: `apps/web/out`

2. **Environment Variables**
   
   Required secrets in GitHub repository settings:
   ```bash
   NETLIFY_AUTH_TOKEN=your_netlify_personal_access_token
   NETLIFY_SITE_ID=your_netlify_site_id
   ```

3. **Automatic Deployments**
   - Main branch deploys to production
   - Pull requests create preview deployments with comment links

### GitHub Branch Protection

Set up branch protection for `main` branch:

1. Go to **Settings** → **Branches** → **Add rule**
2. Branch name pattern: `main`
3. Enable these protections:
   - ✅ Require a pull request before merging
   - ✅ Require status checks to pass before merging
   - ✅ Require branches to be up to date before merging
   - ✅ Required status checks:
     - `Web CI`
     - `Python CI`
     - `E2E Tests`
     - `Netlify Preview` (optional)

### CI/CD Pipeline

The repository includes GitHub Actions workflows:

- **`ci.yml`**: Runs tests for web, API, worker, and E2E tests
- **`netlify-preview.yml`**: Deploys preview builds on pull requests

### Production Environment Variables

For production deployment, configure these environment variables:

```bash
# API Production
USE_AWS=true
AWS_ACCESS_KEY_ID=your_production_key
AWS_SECRET_ACCESS_KEY=your_production_secret
S3_BUCKET=your-production-bucket
DATABASE_URL=your_production_db_url

# Optional: KMS encryption
S3_KMS_KEY_ID=arn:aws:kms:region:account:key/key-id

# Optional: Observability
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-otlp-endpoint
```

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
- **Worker**: Typer CLI stubs + PyMuPDF placeholder for future pipelines

## Security & Ops (baseline)

- CORS restricted via env, least‑privileged S3 creds
- Structured logging, basic health checks
- CI: GitHub Actions (Node + Python), caches deps
- Dockerized local dev: Postgres, MinIO, LocalStack (SQS stub)

Apache‑2.0 License.
