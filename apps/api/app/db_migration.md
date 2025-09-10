# Database Migration Steps

## Manual Migration for Artifacts Table

Until Alembic is set up (T-113), run these SQL commands manually:

```sql
-- Create artifacts table
CREATE TABLE artifacts (
    id VARCHAR NOT NULL PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    page INTEGER NOT NULL,
    engine VARCHAR NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

-- Create index for faster queries
CREATE INDEX ix_artifacts_document_id ON artifacts(document_id);
CREATE INDEX ix_artifacts_kind ON artifacts(kind);
```

## How to Apply

1. Connect to your PostgreSQL database
2. Run the SQL commands above
3. Verify tables exist: `\dt` in psql

## Rollback

```sql
DROP TABLE IF EXISTS artifacts;
```