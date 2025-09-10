# Database Migration Guide

## Manual Migration Steps

This document outlines the manual steps to create the `artifacts` table in the database.

### Prerequisites

- PostgreSQL database running
- Database connection configured in `DATABASE_URL`

### Migration Steps

1. **Connect to your PostgreSQL database:**
   ```bash
   psql -h localhost -U postgres -d ledgerlift
   ```

2. **Create the artifacts table:**
   ```sql
   CREATE TABLE artifacts (
       id VARCHAR PRIMARY KEY,
       document_id VARCHAR NOT NULL REFERENCES documents(id),
       kind VARCHAR NOT NULL,
       page INTEGER NOT NULL,
       engine VARCHAR NOT NULL,
       payload JSONB NOT NULL,
       status VARCHAR DEFAULT 'pending',
       created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
   );

   -- Create indexes for better performance
   CREATE INDEX idx_artifacts_document_id ON artifacts(document_id);
   CREATE INDEX idx_artifacts_kind ON artifacts(kind);
   CREATE INDEX idx_artifacts_status ON artifacts(status);
   ```

3. **Verify the table was created:**
   ```sql
   \d artifacts
   ```

4. **Test the API endpoints:**
   - `GET /v1/documents/{id}/artifacts` - should return empty array for existing documents
   - `POST /v1/artifacts` - should create new artifacts
   - `PATCH /v1/artifacts/{id}` - should update existing artifacts

### Rollback (if needed)

To rollback this migration:

```sql
DROP TABLE IF EXISTS artifacts;
```

### Future Migrations

This manual migration is temporary. Future schema changes should use Alembic migrations (see T-113).

### Notes

- The `payload` column uses PostgreSQL's `JSONB` type for efficient JSON storage and querying
- Foreign key constraint ensures data integrity with the `documents` table
- Timestamps are automatically managed by PostgreSQL
- Indexes are created for common query patterns