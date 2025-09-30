# Ledger Lift — PDF → Excel Schedules (Beta)

This PR adds an end-to-end pipeline to upload PDFs, parse schedules, and download an Excel workbook. It targets **Netlify** and **Cloudflare R2 (S3-compatible)** storage by default.

## Quick Start

```bash
# 1) Copy env
cp .env.example .env

# 2) Install (pnpm workspace)
pnpm -w install

# 3) Run unit+integration tests
pnpm test

# 4) Dev: functions + web
pnpm netlify:dev        # starts Netlify dev (functions on :9999)
pnpm --filter web dev   # starts Next.js on :3000

# 5) Visit
open http://localhost:3000/convert
```

## Configuration

Environment variables (see `.env.example`):

- `R2_S3_ENDPOINT` – Cloudflare R2 S3 endpoint (leave empty to use AWS S3)
- `R2_REGION` – region (e.g., `auto` or `us-east-1`)
- `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET` – bucket name
- `PDF_MAX_MB` – max upload size (MB), default 100
- `OCR_ENABLED` – enable OCR fallbacks (default `false`)
- `ALLOWED_ORIGINS` – CSV of allowed origins for CORS
- `SCALE` – parsing scale factor (heuristics), default 5
- `NEXT_PUBLIC_API_URL` – base path for functions (default `/api`)

## Functions

- `POST /api/initiate-upload` → plan multipart upload (`sourceKey`, `uploadId`, presigned part URLs)
- `POST /api/ingest-pdf` → finalize (optional MPU) and enqueue job → returns `jobId`
- `POST /api/parse-and-extract` (background) → parse/ocr/export
- `GET /api/get-job-status?jobId=...` → job JSON + `downloadUrl` if ready
- `GET /api/healthz` → 200 with version/time

See `netlify/functions/`.

## Frontend

- `apps/web/app/convert/page.tsx` – upload ➜ ingest ➜ poll ➜ download
- `apps/web/src/components/UploadPanel.tsx` – drag‑drop, multipart upload with pause/resume
- Add nav link via `apps/web/app/nav-instructions.md`

## Limits

- Uploads capped by `PDF_MAX_MB`
- Background processing up to Netlify limit (15 min)
- OCR is optional (WASM); keep pages and DPI constrained in config

## Local & Netlify

- Set Netlify site env `NEXT_PUBLIC_API_URL` to the functions base (e.g. `/api` in this setup).
- CORS restricted via `ALLOWED_ORIGINS`. Functions respond to `OPTIONS` preflight.

## CI

- Unit tests (Vitest)
- Integration: synthetic PDF (pdfkit)
- E2E: Playwright (upload ➜ status ➜ download).

Artifacts: Playwright report is uploaded in GitHub Actions.

## Storage Defaults

- Prefixes: `incoming/`, `processed/`, `exports/`
- Prefer **Cloudflare R2**; AWS S3 fallback when `R2_S3_ENDPOINT` is unset.
