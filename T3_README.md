# T3 Enhancement Files - LedgerLift

## 📋 Overview

This directory contains all the T3 (Tier 3) enhancement files for the LedgerLift project. These files implement:

1. **Audit Logging** - Batched audit event tracking with idempotency
2. **Cost Tracking** - OCR cost attribution and reconciliation
3. **GDPR Compliance** - Right-to-deletion with manifests
4. **Schedule Detection** - Data schedule extraction and export
5. **Worker Enhancements** - Cancellation support and tracing

## 📁 File Structure

```
C:\Users\zabriskiem\Ledger.Lift\
├── .env                              # Environment variables
├── netlify.toml                      # Netlify configuration with redirects
│
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── models/
│   │   │   │   ├── __init__.py       # Model imports
│   │   │   │   ├── audit.py          # AuditEvent model
│   │   │   │   ├── costs.py          # CostRecord model
│   │   │   │   └── schedules.py      # JobSchedule model
│   │   │   │
│   │   │   ├── services/
│   │   │   │   ├── audit.py          # Audit batching service
│   │   │   │   ├── costs.py          # Cost tracking service
│   │   │   │   └── gdpr.py           # GDPR deletion service
│   │   │   │
│   │   │   ├── middleware/
│   │   │   │   └── tracing.py        # Request tracing middleware
│   │   │   │
│   │   │   ├── routes/
│   │   │   │   └── schedules.py      # Schedule API endpoints
│   │   │   │
│   │   │   ├── config_t3.py          # T3 configuration
│   │   │   ├── scheduler.py          # APScheduler setup
│   │   │   └── rate_limit.py         # Rate limiting setup
│   │   │
│   │   └── migrations/
│   │       └── versions/
│   │           └── t3_001_audit_costs_schedules.py  # Alembic migration
│   │
│   └── worker/
│       └── worker/
│           ├── database.py           # Database session
│           ├── services.py           # Job CRUD operations
│           ├── cancellation.py       # Cancellation checks
│           ├── processor.py          # Job processor with checkpoints
│           ├── ocr.py                # OCR stub functions
│           └── costs.py              # Cost recording
│
├── netlify/
│   └── functions/
│       ├── package.json              # Netlify function dependencies
│       ├── _database.ts              # PostgreSQL connection pool
│       ├── _utils.ts                 # Handler utilities
│       ├── get-audit-trail.ts        # Audit retrieval endpoint
│       ├── delete-job.ts             # Deletion initiation endpoint
│       ├── get-job-schedules.ts      # Schedules retrieval endpoint
│       └── export-job.ts             # CSV export endpoint
│
└── tests/
    ├── conftest.py                   # Pytest fixtures
    ├── test_audit.py                 # Audit idempotency tests
    ├── test_costs.py                 # Cost flow tests
    ├── test_deletion.py              # GDPR deletion tests
    └── integration/
        └── test_t3_workflow.py       # End-to-end test skeleton
```

## ✨ Key Features

### 1. Audit Logging (`apps/api/app/services/audit.py`)
- **Batching**: Configurable batch size (default 50) and flush interval (default 1000ms)
- **Idempotency**: SHA-256 hash of job_id + event_type + trace_id + user_id + IP + metadata + timestamp
- **Durable Mode**: Optional Redis Streams support for persistence
- **ON CONFLICT DO NOTHING**: PostgreSQL prevents duplicate events

### 2. Cost Tracking (`apps/api/app/services/costs.py`)
- **Attribution**: Cost per page (default 12 cents)
- **Max Cost**: Per-job limit (default $240 = 24000 cents)
- **Status Transitions**: PENDING → COMPLETED/FAILED
- **Reconciliation**: Background job detects stale PENDING records

### 3. GDPR Compliance (`apps/api/app/services/gdpr.py`)
- **Deletion Manifests**: Track deletion status (PENDING/DELETING/COMPLETED/FAILED)
- **Artifact Cleanup**: Deletes MinIO objects before database records
- **Retry Logic**: Exponential backoff (max 3 attempts)
- **Background Sweep**: Periodic cleanup of stale deletions (default 300s)

### 4. Schedule Detection (`apps/api/app/routes/schedules.py`)
- **GET /v1/jobs/{job_id}/schedules**: Returns detected schedules with confidence scores
- **POST /v1/jobs/{job_id}/export**: Generates Excel export using openpyxl

### 5. Worker Cancellation (`apps/worker/worker/cancellation.py`)
- **Checkpoints**: Context manager for cancellation checks
- **JobCancelledException**: Raised when job is cancelled
- **Graceful Shutdown**: Marks job as cancelled and updates cost status

## 🔧 Configuration

All settings are in `apps/api/app/config_t3.py` and can be overridden via `.env`:

```bash
# Feature Flags
FEATURES_T3_AUDIT=true
FEATURES_T3_COSTS=true
FEATURES_T3_GDPR=true

# Audit Settings
AUDIT_BATCH_SIZE=50                    # 1-1000
AUDIT_FLUSH_INTERVAL_MS=1000           # 50-60000
AUDIT_DURABLE_MODE=memory              # memory|redis
REDIS_URL=redis://localhost:6379

# Cost Settings
COST_PER_PAGE_CENTS=12                 # Default OCR cost
MAX_JOB_COST_CENTS=24000               # Max $240 per job

# GDPR Settings
DELETION_SWEEP_INTERVAL_SECONDS=300    # 5 minutes

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ledgerlift
```

## 🚀 Integration Steps

### 1. Install Dependencies

**Backend (FastAPI)**
```powershell
cd apps/api
pip install sqlalchemy[asyncio] alembic pydantic-settings redis openpyxl slowapi apscheduler
```

**Netlify Functions**
```powershell
cd netlify/functions
npm install
```

### 2. Run Migration

```powershell
cd apps/api
alembic upgrade head
```

This creates:
- `audit_events` table with BRIN index
- `cost_records` table
- `job_schedules` table
- New columns on `jobs`: `trace_id`, `schema_version`, `cancellation_requested`, `selected_schedule_ids`, `deletion_manifest`

### 3. Update Main App

**apps/api/app/main.py**
```python
from apps.api.app.middleware.tracing import TracingMiddleware
from apps.api.app.routes.schedules import router as schedules_router
from apps.api.app.scheduler import start_schedulers
from apps.api.app.rate_limit import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

app = FastAPI()

# Add tracing middleware
app.add_middleware(TracingMiddleware)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include schedules router
app.include_router(schedules_router, prefix="/v1", tags=["schedules"])

# Start background schedulers on startup
@app.on_event("startup")
async def startup():
    start_schedulers()
```

### 4. Integrate Audit Events

Wherever you want to log audit events:

```python
from apps.api.app.services.audit import audit_batcher

await audit_batcher.add_event(
    job_id="job-123",
    event_type="job.started",
    user_id="user-456",
    ip_address=request.client.host,
    trace_id=request.state.trace_id,
    metadata={"source": "api"}
)
```

### 5. Integrate Cost Tracking

In your worker's job processor:

```python
from apps.worker.worker.processor import process_job

# This already includes cost tracking
await process_job(job_id="job-123")
```

### 6. Deploy Netlify Functions

```powershell
# From project root
netlify deploy --prod
```

Endpoints will be available at:
- `/api/jobs/:jobId/audit` - Get audit trail
- `/api/jobs/:jobId/delete` - Initiate GDPR deletion
- `/api/jobs/:jobId/schedules` - Get detected schedules
- `/api/jobs/:jobId/export` - Export schedules to CSV

## 🧪 Testing

```powershell
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_audit.py -v

# Run integration tests
pytest tests/integration/ -v
```

## 📊 Database Schema

### audit_events
- `id` (UUID, PK)
- `job_id` (String, indexed)
- `event_type` (String)
- `user_id` (String, indexed)
- `ip_address` (String)
- `trace_id` (String, indexed)
- `idempotency_key` (String, unique)
- `metadata` (JSONB)
- `created_at` (Timestamp with TZ, BRIN indexed)

### cost_records
- `id` (Integer, PK)
- `job_id` (String, indexed)
- `user_id` (String, indexed)
- `provider` (String)
- `pages` (Integer)
- `cost_cents` (Integer)
- `status` (String: PENDING/COMPLETED/FAILED)
- `created_at` (Timestamp)
- `completed_at` (Timestamp, nullable)

### job_schedules
- `id` (Integer, PK)
- `job_id` (String, indexed)
- `name` (String)
- `confidence` (Float)
- `row_count` (Integer)
- `col_count` (Integer)
- `created_at` (Timestamp)

## 🎯 Next Steps

1. **Install dependencies** in both apps/api and netlify/functions
2. **Run Alembic migration** to create tables
3. **Update main.py** to integrate middleware and routes
4. **Test locally** with pytest
5. **Deploy to Netlify** with environment variables
6. **Monitor audit logs** and cost records in production

## 📝 Notes

- All import errors are expected until dependencies are installed
- Worker OCR functions (`ocr.py`) are stubs and need integration with PyMuPDF
- Netlify export function uses CSV for simplicity - upgrade to exceljs for XLSX
- Redis is optional for audit durability - defaults to in-memory batching
- Scheduler runs cost reconciliation every 5 minutes and deletion sweep per config

## 🔗 Related Documentation

- Original Build Scripts: `T3_BUILD_GUIDE.md`
- Quick Start: `QUICK_START.md`
- Easiest Path: `EASIEST_PATH.md`

---

**Created**: 2024-01-15
**Author**: GitHub Copilot
**Status**: Ready for Integration
