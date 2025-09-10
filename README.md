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

1. Connect repo to Netlify
2. Set build:
   - **Base directory**: `.`
   - **Build command**: `pnpm -w install && pnpm --filter web build`
   - **Publish directory**: `apps/web/.next`
3. Set environment variable:
   - `NEXT_PUBLIC_API_URL=https://<your-api-domain>` (or local default)

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
