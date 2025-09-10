# Production-Grade Infrastructure Setup

This document describes the production-ready infrastructure components implemented for Ledger Lift.

## Overview

The production infrastructure includes:

- **S3 Client Abstraction**: Seamless switching between AWS S3 and MinIO
- **Enhanced Data Models**: Full audit trail and processing status tracking
- **Service Layer**: Structured error handling and logging
- **Database Migrations**: Alembic-based schema management
- **Worker Integration**: Document processing with database and S3 integration
- **Comprehensive Testing**: End-to-end integration tests

## Architecture Components

### 1. S3 Client Abstraction Layer

**File**: `apps/api/app/aws.py`

- **S3ClientFactory**: Creates S3 clients for AWS or MinIO based on configuration
- **Environment Toggle**: Use `USE_AWS=true` for production AWS, `USE_AWS=false` for local MinIO
- **Built-in Retry Logic**: Automatic retry with exponential backoff
- **Connection Pooling**: Optimized for high-throughput operations

```python
# Automatic client creation based on environment
client = S3ClientFactory.create_client()

# Generate presigned URLs with validation
url = generate_presigned_url(key, content_type, file_size, expires_in)
```

### 2. Enhanced Data Models

**File**: `apps/api/app/models.py`

#### Document Model
- **Processing Status**: `UPLOADED`, `PROCESSING`, `COMPLETED`, `FAILED`, `RETRYING`
- **Audit Fields**: Created/updated timestamps, error messages
- **File Metadata**: Content type, file size, SHA256 hash
- **Relationships**: Pages, processing events, artifacts

#### ProcessingEvent Model
- **Event Types**: Document lifecycle events for full audit trail
- **Metadata**: JSON storage for event-specific data
- **Timestamps**: Precise event timing

#### Artifact Model
- **Extracted Content**: Tables, figures, text with bounding boxes
- **Confidence Scores**: ML extraction confidence levels
- **Engine Tracking**: Which extraction engine was used

### 3. Service Layer

**File**: `apps/api/app/services.py`

#### DocumentService
- **Transactional Operations**: Database consistency with automatic rollback
- **Audit Trail**: Every status change logged as ProcessingEvent
- **Error Handling**: Structured exceptions with context
- **Status Management**: Safe state transitions

```python
# Create document with automatic audit logging
doc = DocumentService.create_document(s3_key, filename, content_type, file_size)

# Update status with audit trail
DocumentService.update_processing_status(doc_id, ProcessingStatus.PROCESSING)
```

### 4. Worker Integration

**Files**: `apps/worker/worker/`

#### DocumentProcessor
- **Database Integration**: Full CRUD operations on documents
- **S3 Operations**: Download, process, upload artifacts
- **Error Recovery**: Automatic retry with exponential backoff
- **Progress Tracking**: Real-time status updates

#### CLI Interface
```bash
# Process document from database
python -m worker.cli process-document <doc_id>

# Process local file (testing)
python -m worker.cli process-file <pdf_path>
```

### 5. Database Migrations

**Directory**: `apps/api/migrations/`

- **Alembic Integration**: Version-controlled schema changes
- **Automatic Migration**: Runs on container startup
- **Rollback Support**: Safe schema downgrades
- **Environment Isolation**: Separate migration state per environment

```bash
# Generate new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Environment Configuration

### Local Development (.env)
```env
USE_AWS=false
S3_ENDPOINT=http://localhost:9000
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ledgerlift
```

### Production (.env.production)
```env
USE_AWS=true
AWS_ACCESS_KEY_ID=<production_key>
AWS_SECRET_ACCESS_KEY=<production_secret>
DATABASE_URL=postgresql+psycopg://user:pass@prod-db:5432/ledgerlift
```

## Deployment

### Local Development
```bash
# Start all services
docker-compose up -d

# Check service health
curl http://localhost:8000/health

# Process a document
docker-compose exec worker python -m worker.cli process-document <doc_id>
```

### Production Deployment

1. **Environment Setup**:
   ```bash
   cp .env.example .env.production
   # Edit .env.production with production values
   ```

2. **Database Migration**:
   ```bash
   # Migrations run automatically on container startup
   # Manual migration if needed:
   docker-compose exec api alembic upgrade head
   ```

3. **Health Checks**:
   ```bash
   # API health
   curl https://api.yourdomain.com/health
   
   # Database connectivity
   docker-compose exec api python -c "from app.db import engine; print(engine.execute('SELECT 1').scalar())"
   ```

## Monitoring and Observability

### Audit Trail Queries
```sql
-- View document processing timeline
SELECT d.id, d.original_filename, d.processing_status, 
       e.event_type, e.message, e.created_at
FROM documents d
LEFT JOIN processing_events e ON d.id = e.document_id
WHERE d.id = '<doc_id>'
ORDER BY e.created_at;

-- Processing performance metrics
SELECT 
    processing_status,
    COUNT(*) as count,
    AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_processing_time
FROM documents 
GROUP BY processing_status;
```

### Health Monitoring
- **API Health**: `GET /health` - Returns service status
- **Database Health**: Connection pool monitoring
- **S3 Health**: Presigned URL generation success rate
- **Worker Health**: Processing queue depth and error rates

## Security Considerations

### File Upload Security
- **Content Type Validation**: Only PDF and DOCX allowed
- **File Size Limits**: Configurable maximum file size (default 100MB)
- **Filename Sanitization**: Path traversal attack prevention
- **Presigned URL TTL**: Short-lived URLs (default 15 minutes)

### Database Security
- **Connection Encryption**: TLS-encrypted database connections
- **Parameter Sanitization**: SQLAlchemy ORM prevents SQL injection
- **Audit Logging**: Complete operation trail for compliance

### S3 Security
- **IAM Roles**: Least-privilege access policies
- **Bucket Policies**: Restricted access patterns
- **Encryption**: Server-side encryption for stored files

## Performance Optimization

### Database
- **Connection Pooling**: Configurable pool size
- **Query Optimization**: Indexed foreign keys and lookups
- **Batch Operations**: Bulk processing for large datasets

### S3 Operations
- **Multipart Upload**: Large file handling
- **Connection Reuse**: HTTP connection pooling
- **Retry Logic**: Exponential backoff for transient failures

### Worker Processing
- **Concurrent Processing**: Configurable worker pool size
- **Memory Management**: Cleanup of temporary files
- **Resource Limits**: CPU and memory constraints

## Troubleshooting

### Common Issues

1. **Database Connection Errors**:
   ```bash
   # Check database connectivity
   docker-compose exec api python -c "from app.db import engine; engine.execute('SELECT 1')"
   ```

2. **S3 Connection Errors**:
   ```bash
   # Test S3 connectivity
   docker-compose exec api python -c "from app.aws import S3ClientFactory; S3ClientFactory.create_client().list_buckets()"
   ```

3. **Migration Errors**:
   ```bash
   # Check migration status
   docker-compose exec api alembic current
   
   # Reset to clean state
   docker-compose exec api alembic downgrade base
   docker-compose exec api alembic upgrade head
   ```

### Logging

- **Structured Logging**: JSON format for production
- **Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Context**: Request IDs, user IDs, document IDs in all log entries
- **Centralized**: ELK stack or similar for log aggregation

## Testing

### Integration Tests
```bash
# Run full test suite
cd apps/api && python -m pytest tests/test_integration.py -v

# Test specific functionality
python -m pytest tests/test_integration.py::test_full_upload_flow -v
```

### Load Testing
```bash
# Simulate concurrent uploads
ab -n 100 -c 10 -H "Content-Type: application/json" \
   -p presign_request.json http://localhost:8000/v1/uploads/presign
```

## Maintenance

### Regular Tasks
- **Database Backups**: Automated daily backups
- **Log Rotation**: Weekly log archival
- **Certificate Renewal**: Automated SSL certificate updates
- **Dependency Updates**: Monthly security updates

### Scaling Considerations
- **Horizontal Scaling**: Load balancer + multiple API instances
- **Database Scaling**: Read replicas for query performance
- **Worker Scaling**: Queue-based processing with auto-scaling
- **Storage Scaling**: S3 provides unlimited storage capacity

This production setup provides a robust, scalable, and maintainable foundation for financial document processing with full audit capabilities and error recovery.