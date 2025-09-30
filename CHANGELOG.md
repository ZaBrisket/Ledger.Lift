# Changelog

## v0.2.0 - PDF → Excel Schedules (Beta)

- feat(functions): add Netlify Functions for PDF upload, ingest, parsing (background), job status, and health check
- feat(storage): S3/R2 client with multipart helpers and presigned URLs
- feat(pdf): glyph extraction, table detection, OCR utilities, schedule classification
- feat(excel): export workbook with _Summary and schedule sheets
- feat(web): UploadPanel and /convert flow; nav link
- chore(ci): add unit, integration, and e2e tests (Playwright)
- docs: README updates and ops runbook
