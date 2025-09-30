# Netlify Deployment Runbook

This checklist hardens the upload pipeline for Ledger Lift. Complete each step when deploying to Netlify so production single PUT and multipart uploads succeed.

## 1. Configure environment variables

Set the following variables for both **Site environment** and **Functions** contexts. Values must match the placeholders from `.env.example`.

| Variable | Notes |
| --- | --- |
| `ALLOWED_ORIGINS` | Comma-separated list including `https://ledgerlift1.netlify.app` and local development origins like `http://localhost:3000`. |
| `PDF_MAX_MB` / `NEXT_PUBLIC_PDF_MAX_MB` | Keep these in sync (default `100`). Controls validation on both the API and client. |
| `PRESIGN_TTL` | Seconds that presigned URLs remain valid (default `900`). |
| `NEXT_PUBLIC_API_URL` | Base URL for client requests (`https://ledgerlift1.netlify.app` in production, `http://localhost:8888` locally). |
| `REGION` | R2 or S3 region identifier. |
| `R2_S3_ENDPOINT` | Cloudflare R2 endpoint in the form `<accountid>.r2.cloudflarestorage.com`. |
| `R2_BUCKET` | Target bucket for uploads. |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | Credentials with permission to perform multipart uploads. |
| `R2_MULTIPART_THRESHOLD_MB` | Files larger than this use multipart (default `50`). |
| `NODE_ENV` | `production` on Netlify. |

> **Tip:** Keep the client and functions values aligned—mismatched thresholds or origins lead to preflight or upload failures.

## 2. Confirm build & functions configuration

- `netlify.toml` already proxies `/api/*` to `/.netlify/functions/:splat` and bundles functions with `esbuild`.
- Ensure the site uses the **monorepo** root (`base = "."`) so dependencies like `@aws-sdk/*`, `file-type`, and `zod` are available during bundling.

## 3. Deploy and verify uploads

1. Deploy the site.
2. Trigger the health check at `/api/healthz` to confirm functions respond with `X-Request-ID` headers.
3. Upload a small PDF (< `R2_MULTIPART_THRESHOLD_MB`). Confirm the Network tab shows a single `PUT` request with the `x-amz-checksum-sha256` header.
4. Upload a large PDF (> `R2_MULTIPART_THRESHOLD_MB`). Confirm:
   - Multiple part uploads complete despite transient failures (retry/backoff).
   - Final multipart completion succeeds and reported ETags match R2 objects (quotes removed client-side and server-side).
5. Inspect the resulting objects in R2:
   - Sizes match the source files.
   - ETags match the client logs and `complete-multipart` response.
6. Monitor server logs and `/metrics` for any queue or Redis regressions (T1a remains unchanged).

## 4. Troubleshooting quick checks

- Preflight errors: ensure `ALLOWED_ORIGINS` includes the requesting origin exactly (case-insensitive, no trailing slash).
- 403/Signature mismatch: verify `REGION`, credentials, and `R2_S3_ENDPOINT` align with the bucket.
- Multipart stalls: confirm `R2_MULTIPART_THRESHOLD_MB` isn’t set higher than the client build expects.

Document any deviations in the release notes before shipping.
