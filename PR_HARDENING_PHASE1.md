# Hardening + Tests: API Infrastructure Modules

## Summary

This PR implements comprehensive reliability hardening for three critical infrastructure modules in the Ledger Lift API:
- **uploads.py**: File upload endpoint with external user input
- **aws.py**: S3 operations with circuit breaker 
- **db.py**: Database connection and session management

## Failure Modes Addressed

### uploads.py
- **Path traversal attacks**: Added strict filename validation with regex pattern matching
- **Invalid file types**: Enforced content-type whitelist with extension verification
- **Large file DoS**: Added file size validation (configurable limits)
- **Missing error context**: Added request IDs and structured error responses
- **Service unavailability**: Check S3 health before generating presigned URLs

### aws.py  
- **Cascading S3 failures**: Enhanced circuit breaker with thread safety and success thresholds
- **Transient errors**: Added exponential backoff with jitter (avoids thundering herd)
- **Connection exhaustion**: Added connection pooling with TTL
- **Silent failures**: Comprehensive operation statistics and health monitoring
- **Non-idempotent retries**: Separate retry logic for idempotent vs non-idempotent operations

### db.py
- **Connection failures**: Retry decorator with exponential backoff for transient errors
- **Pool exhaustion**: Enhanced pool monitoring with utilization warnings
- **Slow queries**: Configurable slow query detection and logging
- **Statement timeouts**: Added per-query timeout support
- **Validation failures**: Connection validation on init and health checks

## Before/After Behavior

### uploads.py
**Before**: 
- Basic validation, generic 500 errors
- No request tracking or S3 health checks

**After**:
- Comprehensive input validation with specific error codes
- Request ID tracking for debugging
- S3 health check before operations
- Structured error responses with timestamps

### aws.py
**Before**:
- Basic circuit breaker without thread safety
- Built-in boto3 retries without jitter
- Limited health monitoring

**After**:
- Thread-safe circuit breaker with half-open state
- Custom retry logic with exponential backoff + jitter
- Detailed operation statistics and health checks
- Idempotency-aware retry strategies

### db.py
**Before**:
- Basic retry on disconnect
- Limited connection monitoring
- No slow query detection

**After**:
- Comprehensive retry logic for transient errors
- Detailed connection pool statistics
- Slow query detection and logging
- Per-query timeout support
- Thread-safe statistics tracking

## Test Coverage

Added comprehensive test suites for each module:
- **test_uploads_hardened.py**: 150+ test cases covering validation, errors, concurrency
- **test_aws_hardened.py**: 100+ test cases for circuit breaker, retries, thread safety
- **test_db_hardened.py**: 80+ test cases for retry logic, health checks, statistics

Key test categories:
- Input validation edge cases
- Error handling and retry scenarios
- Concurrent access patterns
- Performance characteristics
- Health check functionality

## Configuration

New configuration options added (all have sensible defaults):
```python
# S3 Settings
s3_failure_threshold = 5  # Circuit breaker opens after N failures
s3_recovery_timeout = 60  # Seconds before circuit breaker tries half-open
s3_success_threshold = 2  # Successes needed to close from half-open
s3_max_retries = 3
s3_retry_base_delay = 1.0
s3_retry_max_delay = 30.0
s3_retry_jitter = 0.2

# Database Settings  
db_pool_size = 20
db_max_overflow = 30
db_pool_timeout = 30
db_pool_recycle = 3600
db_connect_timeout = 30
db_slow_query_threshold = 5.0  # Seconds
```

## Observability Improvements

All modules now provide:
- Structured logging with request IDs
- Operation timing metrics
- Success/failure counters
- Health check endpoints
- Detailed error context

## Known Follow-ups

1. Add rate limiting to upload endpoint (tracked separately)
2. Implement request signing for additional security
3. Add metrics export for monitoring systems
4. Create alerting rules based on new health checks

## Breaking Changes

None - all changes maintain backward compatibility. The only visible changes are:
- More specific error messages (still use same HTTP status codes)
- Additional fields in responses (request_id, timestamps)
- Health endpoints return more detailed information