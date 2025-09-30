# PDF → Excel Schedules (Beta)

Implements: A–L of the spec in one PR to `main`.

## Summary
- Netlify Functions for upload, ingest, background parsing, status, health
- R2/S3 storage client with multipart helpers & presign
- PDF parsing (pdfjs-dist), table detection & OCR fallbacks
- Excel export (exceljs)
- Frontend flow (/convert) + UploadPanel with multipart + pause/resume
- CORS & env validation with Zod, structured logs, correlation IDs
- Netlify config (functions, headers, redirects, background)
- Tests: unit, integration (pdfkit), e2e (Playwright)

## Docs
- `README.md` (setup, env, run locally/Netlify, limits)
- `docs/ops.md` (runbook, error codes, retry policy)
- `CHANGELOG.md`

## Acceptance
- Uploads up to `PDF_MAX_MB`
- End-to-end export with ≥1 worksheet
- `/healthz` returns 200
- CI green: typecheck, unit, integration, e2e

## Notes
- Function responses set CORS headers (Netlify headers in TOML are not applied to function responses per docs).
- Background function name uses `-background` suffix per Netlify convention.
