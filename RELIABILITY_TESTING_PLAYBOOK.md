# Reliability & Testing Playbook

This playbook provides patterns and guidelines for maintaining and extending the reliability improvements in the Ledger Lift codebase.

## Guard Patterns

### 1. Input Validation at Module Boundaries

Always validate inputs at the entry point of public functions:

```python
def process_document(doc_id: str, options: Dict[str, Any] = None):
    # Guard clauses first
    if not doc_id or not isinstance(doc_id, str):
        raise ValueError("Document ID must be a non-empty string")
    
    if options and not isinstance(options, dict):
        raise TypeError("Options must be a dictionary")
    
    # Sanitize inputs
    doc_id = doc_id.strip()
    options = options or {}
    
    # Proceed with logic...
```

### 2. Timeout Configuration

All external operations should have configurable timeouts:

```python
# Connection timeout: Time to establish connection
# Read timeout: Time to receive response
# Total timeout: Overall operation limit

@retry_with_exponential_backoff(max_attempts=3)
def fetch_external_data(url: str, timeout: Optional[Tuple[float, float]] = None):
    timeout = timeout or (30.0, 60.0)  # (connect, read)
    response = requests.get(url, timeout=timeout)
    return response.json()
```

### 3. Retry Logic with Jitter

Use exponential backoff with jitter to avoid thundering herd:

```python
def exponential_backoff_with_jitter(attempt: int, base_delay: float = 1.0, 
                                  max_delay: float = 60.0, jitter: float = 0.1):
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter_range = delay * jitter
    actual_delay = delay + random.uniform(-jitter_range, jitter_range)
    return max(0, actual_delay)
```

### 4. Circuit Breaker Pattern

Implement circuit breakers for external dependencies:

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60, success_threshold=2):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  
        self.success_threshold = success_threshold
        self.state = 'closed'  # closed, open, half-open
        
    def call(self, func, *args, **kwargs):
        if not self.can_execute():
            raise CircuitBreakerOpen("Service unavailable")
        
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise
```

### 5. Structured Error Handling

Use structured errors with stable error codes:

```python
class ServiceError(Exception):
    def __init__(self, message: str, error_code: str, details: Dict = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = time.time()

# Usage
raise ServiceError(
    "Failed to process document",
    "DOC_PROCESSING_FAILED",
    {"document_id": doc_id, "stage": "validation"}
)
```

## Testing Patterns

### 1. Deterministic Tests

Make tests deterministic by controlling time and randomness:

```python
@pytest.fixture
def fixed_time():
    with patch('time.time', return_value=1234567890):
        yield

@pytest.fixture
def seeded_random():
    random.seed(42)
    yield
    random.seed()  # Reset

def test_with_controlled_environment(fixed_time, seeded_random):
    result = function_under_test()
    assert result.timestamp == 1234567890
```

### 2. Parameterized Edge Case Testing

Use parameterized tests for comprehensive edge case coverage:

```python
@pytest.mark.parametrize("input_value,expected_error", [
    ("", ValueError),  # Empty string
    (None, ValueError),  # None
    ("../../../etc/passwd", ValueError),  # Path traversal
    ("a" * 256, ValueError),  # Too long
    (" spaces ", ValueError),  # Leading/trailing spaces
    ("special@char", ValueError),  # Invalid characters
])
def test_input_validation(input_value, expected_error):
    with pytest.raises(expected_error):
        validate_input(input_value)
```

### 3. Concurrency Testing

Test thread safety and race conditions:

```python
def test_concurrent_access():
    manager = ResourceManager()
    results = []
    errors = []
    
    def access_resource():
        try:
            with manager.get_resource() as resource:
                results.append(resource.id)
        except Exception as e:
            errors.append(e)
    
    threads = [threading.Thread(target=access_resource) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0
    assert len(set(results)) == len(results)  # All unique
```

### 4. Timeout Testing

Test timeout behavior without waiting:

```python
@patch('requests.get')
def test_timeout_handling(mock_get):
    mock_get.side_effect = requests.Timeout("Connection timed out")
    
    with pytest.raises(ServiceError) as exc_info:
        fetch_data_with_timeout("http://example.com", timeout=1)
    
    assert exc_info.value.error_code == "TIMEOUT_ERROR"
```

### 5. Health Check Testing

Ensure health checks are comprehensive:

```python
def test_health_check_degraded_state():
    service = MyService()
    
    # Simulate high error rate
    for _ in range(10):
        service.record_error()
    
    health = service.health_check()
    assert health['status'] == 'degraded'
    assert 'error_rate' in health['metrics']
    assert health['metrics']['error_rate'] > 0.1
```

## Adding a New Hardened Module

When adding reliability to a new module:

1. **Identify Failure Modes**
   - List all external dependencies
   - Identify all user inputs
   - Consider concurrency issues
   - Think about resource limits

2. **Add Guard Clauses**
   ```python
   def new_function(param1: str, param2: int):
       # Validate inputs
       if not param1:
           raise ValueError("param1 required")
       if param2 < 0:
           raise ValueError("param2 must be non-negative")
   ```

3. **Add Timeouts**
   ```python
   # For HTTP calls
   response = session.get(url, timeout=(5, 30))
   
   # For database operations  
   with db.get_session() as session:
       session.execute("SET LOCAL statement_timeout = 30000")
   ```

4. **Add Retry Logic**
   ```python
   @retry_with_exponential_backoff(
       max_attempts=3,
       retriable_exceptions=(NetworkError, TimeoutError)
   )
   def external_operation():
       # Implementation
   ```

5. **Add Observability**
   ```python
   logger.info("Operation started", extra={
       "request_id": request_id,
       "parameters": sanitized_params
   })
   
   try:
       result = perform_operation()
       logger.info("Operation completed", extra={
           "request_id": request_id,
           "duration_ms": duration
       })
   except Exception as e:
       logger.error("Operation failed", extra={
           "request_id": request_id,
           "error": str(e),
           "error_type": type(e).__name__
       })
   ```

6. **Write Tests**
   - Happy path
   - Each validation rule
   - Each error condition
   - Timeout scenarios
   - Concurrent access
   - Health checks

## Monitoring and Alerting

Key metrics to monitor:

1. **Error Rates**
   - Overall error rate > 5%
   - Specific error types trending up
   - Circuit breaker state changes

2. **Performance**
   - P95 response time > SLA
   - Slow query rate > 1%
   - Connection pool utilization > 80%

3. **Availability**
   - Health check failures
   - Dependency unavailable
   - Resource exhaustion

## Common Pitfalls to Avoid

1. **Don't retry non-idempotent operations**
   ```python
   # Bad: Retrying charge operation
   @retry_on_failure
   def charge_customer(amount):
       # This could charge multiple times!
   
   # Good: Make it idempotent first
   def charge_customer(charge_id, amount):
       # Use charge_id to ensure single execution
   ```

2. **Don't catch and suppress all exceptions**
   ```python
   # Bad
   try:
       risky_operation()
   except Exception:
       pass  # Silent failure
   
   # Good
   except SpecificError as e:
       logger.error(f"Known error: {e}")
       raise ServiceError("User-friendly message", "ERROR_CODE")
   ```

3. **Don't use unbounded retries**
   ```python
   # Bad
   while True:
       try:
           return operation()
       except:
           time.sleep(1)
   
   # Good
   @retry_with_exponential_backoff(max_attempts=3)
   def operation():
       # Implementation
   ```

4. **Don't forget about cleanup**
   ```python
   # Always use context managers or try/finally
   resource = acquire_resource()
   try:
       use_resource(resource)
   finally:
       resource.release()
   ```

## Appendix: Error Codes

Standard error codes for consistency:

- `VALIDATION_ERROR`: Input validation failed
- `NOT_FOUND`: Resource not found  
- `TIMEOUT_ERROR`: Operation timed out
- `RATE_LIMIT_ERROR`: Rate limit exceeded
- `SERVICE_UNAVAILABLE`: External service down
- `INTERNAL_ERROR`: Unexpected error
- `PERMISSION_DENIED`: Authorization failed
- `CONFLICT_ERROR`: Resource conflict
- `QUOTA_EXCEEDED`: Resource limit hit