# Netlify Deployment Checklist

This runbook summarizes the required configuration to ship the upload hotfix (T0 + T0.1).
Follow these steps in the Netlify UI before promoting to production.

## Environment variables

Set the following variables for both **Site** and **Functions** contexts. Values must match between
frontend and backend to avoid desynchronised validation.

| Variable | Recommended value | Notes |
| --- | --- | --- |
| `ALLOWED_ORIGINS` | `https://ledgerlift1.netlify.app, http://localhost:3000` | Comma-separated list of trusted origins. Keep whitespace-free. |
| `PDF_MAX_MB` / `NEXT_PUBLIC_PDF_MAX_MB` | `100` | UI and API enforce the same upper bound. |
| `PRESIGN_TTL` | `900` | Seconds a presigned URL remains valid. |
| `REGION` | `<r2-or-aws-region>` | Match the R2 bucket region (e.g. `auto` for Cloudflare R2). |
| `R2_S3_ENDPOINT` | `<accountid>.r2.cloudflarestorage.com` | Do **not** include the protocol. |
| `R2_BUCKET` | `<bucket>` | Target Cloudflare R2 bucket name. |
| `R2_ACCESS_KEY_ID` | `***` | Store in Netlify UI secrets manager. |
| `R2_SECRET_ACCESS_KEY` | `***` | Store in Netlify UI secrets manager. |
| `R2_MULTIPART_THRESHOLD_MB` | `50` | Files >= 50MB use multipart uploads. |
| `NEXT_PUBLIC_API_URL` | `https://ledgerlift1.netlify.app` (production) / `http://localhost:8888` (local CLI) | The frontend calls Functions through this base URL. |
| `NODE_ENV` | `production` (deploys) / `development` (local) | Required by Next.js. |

## Build settings

1. Confirm `netlify.toml` is committed with the `/api/* -> /.netlify/functions/:splat` redirect.
2. Ensure Functions use the `esbuild` bundler with `file-type` marked as external (avoids mixed ESM/CJS issues).
3. Install dependencies with `pnpm -w install` before building the Next.js app (`pnpm --filter web build`).

## Post-deploy verification

1. **Proxy check** – Hit `https://<site>.netlify.app/api/healthz` and confirm a `200 OK` with `X-Request-ID` header.
2. **Small upload (< threshold)** – Upload a ~1MB PDF. Observe:
   - Frontend progress bar reaches 100% without stalling.
   - Network tab shows `x-amz-checksum-sha256` header on the single PUT request.
3. **Large upload (> threshold)** – Upload a file larger than 50MB. Observe:
   - Multiple part PUTs with retries/backoff when transient errors occur.
   - Completion call succeeds with normalized ETags.
4. **Storage validation** – In Cloudflare R2, confirm uploaded object size matches expectation and ETag matches the client log (quotes removed).
5. **Metrics sanity** – Ensure `/metrics` endpoint (T1a) continues reporting Redis/RQ stats; no regressions expected.

Document any deviations and rollback if uploads fail in production.
