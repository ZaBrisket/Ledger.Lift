# 🛡️ Reliability & Testing Playbook

This document outlines the reliability patterns, testing standards, and best practices for the Ledger Lift codebase. Following these guidelines ensures robust, maintainable, and production-ready code.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Reliability Principles](#reliability-principles)
- [Hardening Patterns](#hardening-patterns)
- [Testing Standards](#testing-standards)
- [CI/CD Pipeline](#cicd-pipeline)
- [Development Workflow](#development-workflow)
- [Troubleshooting](#troubleshooting)

## 🚀 Quick Start

### Prerequisites
```bash
# Install dependencies
make install

# Run reliability checks
make reliability-check

# Run full CI pipeline locally
make ci-local
```

### Pre-commit Setup
```bash
# Install pre-commit hooks
make install-hooks

# Run hooks manually
make pre-commit
```

## 🎯 Reliability Principles

### 1. **Fail Fast, Fail Safe**
- Validate inputs at module boundaries
- Return structured errors with actionable messages
- Use circuit breakers to prevent cascade failures
- Implement graceful degradation for non-critical features

### 2. **Timeout Everything**
- Set explicit timeouts on all external calls
- Use bounded retries with exponential backoff + jitter
- Implement operation-level timeouts for long-running processes
- Fail fast with clear timeout messages

### 3. **Resource Management**
- Use context managers for resource cleanup
- Ensure cleanup happens even during exceptions
- Track and monitor resource usage
- Implement graceful shutdown procedures

### 4. **Observability First**
- Log at appropriate levels (DEBUG, INFO, WARN, ERROR)
- Include correlation IDs for request tracing
- Record operation metrics (timing, success/failure rates)
- Structure logs for easy parsing and alerting

### 5. **Deterministic Testing**
- Mock external dependencies
- Use fixed time/randomness in tests
- Avoid sleeps - use deterministic timing
- Test failure scenarios extensively

## 🔧 Hardening Patterns

### Input Validation Pattern
```python
def process_document(doc_id: str, timeout_seconds: int = 300) -> ServiceResult[Document]:
    """Process document with comprehensive validation."""
    # 1. Input validation
    if not doc_id or not doc_id.strip():
        return ServiceResult.error_result(
            "Document ID cannot be empty",
            "INVALID_INPUT"
        )
    
    doc_id = doc_id.strip()
    if len(doc_id) > 100:
        return ServiceResult.error_result(
            "Document ID too long",
            "INVALID_INPUT"
        )
    
    # 2. Processing with timeout
    try:
        with timeout_context(timeout_seconds):
            # ... processing logic
            pass
    except TimeoutError as e:
        return ServiceResult.error_result(
            f"Processing timed out: {e}",
            "TIMEOUT_ERROR"
        )
```

### Circuit Breaker Pattern
```python
class CircuitBreaker:
    """Prevents cascade failures by failing fast when error threshold is reached."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = 'closed'  # closed, open, half-open
    
    def execute(self, operation):
        if not self.can_execute():
            raise CircuitBreakerOpenError("Circuit breaker is open")
        
        try:
            result = operation()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise
```

### Retry with Backoff Pattern
```python
@contextmanager
def retry_on_failure(max_retries: int = 3, backoff_factor: float = 1.0):
    """Retry operations with exponential backoff."""
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            yield attempt
            return  # Success
        except (RetryableError, TransientError) as e:
            last_exception = e
            if attempt < max_retries - 1:
                sleep_time = backoff_factor * (2 ** attempt)
                logger.warning(f"Retry {attempt + 1}/{max_retries} in {sleep_time}s: {e}")
                time.sleep(sleep_time)
                continue
            break
        except Exception as e:
            # Don't retry on non-retryable errors
            raise
    
    raise last_exception
```

### Resource Management Pattern
```python
class ResourceManager:
    """Ensures cleanup of temporary resources."""
    
    def __init__(self):
        self.resources = []
    
    def create_temp_file(self, suffix: str = '') -> str:
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self.resources.append(path)
        return path
    
    def cleanup(self):
        for resource in self.resources:
            try:
                if os.path.exists(resource):
                    os.unlink(resource)
            except Exception as e:
                logger.warning(f"Cleanup failed for {resource}: {e}")
        self.resources.clear()

@contextmanager
def managed_resources():
    """Context manager for automatic resource cleanup."""
    manager = ResourceManager()
    try:
        yield manager
    finally:
        manager.cleanup()
```

### Structured Error Handling
```python
@dataclass
class ServiceResult(Generic[T]):
    """Standardized result wrapper for service operations."""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @classmethod
    def success_result(cls, data: T, metadata: Optional[Dict[str, Any]] = None):
        return cls(success=True, data=data, metadata=metadata)
    
    @classmethod
    def error_result(cls, error: str, error_code: str, metadata: Optional[Dict[str, Any]] = None):
        return cls(success=False, error=error, error_code=error_code, metadata=metadata)

# Usage in API routes
@router.post("/documents", response_model=DocumentOut)
def create_document(payload: DocumentCreate):
    result = DocumentService.create_document(**payload.dict())
    
    if not result.success:
        status_code = 500
        if result.error_code == "DUPLICATE_DOCUMENT":
            status_code = 409
        elif result.error_code == "DATABASE_ERROR":
            status_code = 503
            
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": result.error_code,
                "message": result.error,
                "details": result.metadata
            }
        )
    
    return result.data
```

## 🧪 Testing Standards

### Test Structure
```python
class TestDocumentService:
    """Test class following reliability patterns."""
    
    @pytest.fixture
    def fixed_time(self):
        """Fixed time for deterministic testing."""
        with patch('time.time', return_value=1609459200.0):
            yield 1609459200.0
    
    @pytest.fixture
    def mock_s3_healthy(self):
        """Mock S3 in healthy state."""
        with patch('app.services.s3_manager') as mock_s3:
            mock_s3.health_check.return_value = {'status': 'healthy'}
            yield mock_s3
    
    def test_create_document_success(self, fixed_time, mock_s3_healthy):
        """Test successful document creation with deterministic inputs."""
        # Arrange
        payload = {
            "s3_key": "test/file.pdf",
            "filename": "file.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        # Act
        result = DocumentService.create_document(**payload)
        
        # Assert
        assert result.success is True
        assert result.data.s3_key == payload["s3_key"]
        assert result.metadata["processing_time_ms"] > 0
    
    @pytest.mark.parametrize("field,value,expected_error", [
        ("s3_key", "", "S3 key cannot be empty"),
        ("file_size", 0, "File size must be positive"),
        ("file_size", -1, "File size must be positive"),
    ])
    def test_create_document_validation(self, field, value, expected_error):
        """Test input validation with edge cases."""
        payload = {
            "s3_key": "test/file.pdf",
            "filename": "file.pdf", 
            "content_type": "application/pdf",
            "file_size": 1024
        }
        payload[field] = value
        
        result = DocumentService.create_document(**payload)
        
        assert result.success is False
        assert expected_error in result.error
        assert result.error_code == "INVALID_INPUT"
```

### Test Categories

#### 1. **Unit Tests**
- Test individual functions/methods in isolation
- Mock all external dependencies
- Cover happy path + edge cases + error conditions
- Must be deterministic and fast (<1s each)

#### 2. **Integration Tests**
- Test component interactions
- Use real databases/services in controlled environment
- Test critical user journeys end-to-end
- Include failure scenario testing

#### 3. **Contract Tests**
- Test external API integrations
- Verify request/response formats
- Test error handling for external failures
- Mock external services by default

### Test Requirements

✅ **MUST HAVE:**
- Input validation tests for all edge cases
- Error handling tests for all failure modes
- Resource cleanup verification
- Timeout behavior testing
- Deterministic behavior (no flakiness)

❌ **MUST AVOID:**
- `time.sleep()` calls in tests
- Uncontrolled randomness
- Shared mutable state between tests
- Dependencies on external services (except integration tests)
- Tests that can pass or fail based on timing

## 🔄 CI/CD Pipeline

### Pipeline Stages

1. **Static Analysis**
   - Ruff linting and formatting
   - Security scanning (Bandit, Safety)
   - Reliability pattern checking

2. **Unit Testing**
   - Coverage ≥85% required
   - Test timeout: 30s max per test
   - Parallel execution by component

3. **Flakiness Detection**
   - Critical tests run 3x
   - Must have 0 non-deterministic failures
   - Automatic failure on flaky tests

4. **Integration Testing**
   - Full system with real services
   - Database migrations
   - API health checks

5. **Security & Performance**
   - Dependency vulnerability scan
   - Basic performance baseline
   - Load testing on main branch

### Quality Gates

All PRs must pass:
- ✅ Static analysis (linting, formatting, security)
- ✅ Unit tests with ≥85% coverage
- ✅ Flakiness check (0 non-deterministic failures)
- ✅ Integration tests
- ✅ Reliability pattern compliance

### Branch Protection

```yaml
# Required for main branch
required_status_checks:
  - Static Analysis
  - Unit Tests (api)
  - Unit Tests (worker)
  - Flakiness Detection
  - Integration Tests
  - Security Scan

# Additional requirements
require_code_owner_reviews: true
dismiss_stale_reviews: true
restrict_pushes: true
```

## 🔄 Development Workflow

### 1. **Before You Code**
```bash
# Set up environment
make install

# Create feature branch
git checkout -b feature/your-feature
```

### 2. **During Development**
```bash
# Run quality checks frequently
make quality-check

# Run specific tests
make test-api
make test-worker

# Check for flakiness
make flakiness-check
```

### 3. **Before Committing**
```bash
# Pre-commit hooks run automatically, or manually:
make pre-commit

# Full reliability check
make reliability-check
```

### 4. **Before Pushing**
```bash
# Run full local CI
make ci-local

# Verify no TODOs without issue numbers
make release-check
```

### 5. **Code Review Checklist**

**Reliability:**
- [ ] Input validation at module boundaries
- [ ] Proper error handling with structured errors
- [ ] Timeouts on external operations
- [ ] Resource cleanup in finally blocks
- [ ] Circuit breaker pattern for external services

**Testing:**
- [ ] Tests cover happy path + edge cases + errors
- [ ] No flaky tests (deterministic behavior)
- [ ] Mocked external dependencies
- [ ] Test coverage ≥85%
- [ ] Integration tests for critical paths

**Code Quality:**
- [ ] Clear, actionable error messages
- [ ] Structured logging with correlation IDs
- [ ] Configuration values externalized
- [ ] No hardcoded timeouts or magic numbers
- [ ] Proper documentation for public APIs

## 🚨 Troubleshooting

### Common Issues

#### **Flaky Tests**
```bash
# Identify flaky tests
make flakiness-check

# Common causes:
# - Race conditions
# - Uncontrolled randomness
# - Time-dependent assertions
# - Shared mutable state
```

**Solutions:**
- Use `fixed_time` fixtures for time-dependent tests
- Mock random number generation
- Use `pytest-timeout` to catch hanging tests
- Isolate test state with proper setup/teardown

#### **Low Test Coverage**
```bash
# Generate coverage report
make coverage

# View detailed report
open apps/api/htmlcov/index.html
```

**Solutions:**
- Add tests for uncovered branches
- Test error handling paths
- Use parametrized tests for edge cases
- Mock external dependencies to reach error paths

#### **Reliability Pattern Violations**
```bash
# Check patterns
python scripts/check_reliability_patterns.py apps/api/app/*.py

# Common violations:
# - Missing input validation
# - Bare except clauses
# - Missing timeouts
# - Print statements instead of logging
```

**Solutions:**
- Add input validation to public functions
- Use specific exception types
- Add timeout parameters to long-running operations
- Replace print with structured logging

#### **CI Pipeline Failures**

**Static Analysis Failures:**
```bash
# Fix linting issues
make lint
make format
```

**Security Scan Issues:**
```bash
# Check security reports
make security
cat apps/*/bandit-report.json
```

**Integration Test Failures:**
```bash
# Test with services locally
make dev-services
make test-integration
make dev-stop
```

### Performance Issues

#### **Slow Tests**
- Tests taking >30s will timeout in CI
- Use mocking to avoid real I/O
- Parallelize independent tests
- Use `pytest-benchmark` for performance tests

#### **Memory Leaks**
- Ensure proper resource cleanup
- Use context managers
- Monitor test memory usage
- Check for circular references

### Getting Help

1. **Check this playbook** for patterns and solutions
2. **Run diagnostics**: `make ci-local` to reproduce CI issues
3. **Review logs**: Check GitHub Actions logs for detailed errors
4. **Ask for review**: Tag reliability-focused team members

## 📚 Additional Resources

- [GitHub Actions Workflow](.github/workflows/reliability-ci.yml)
- [Pre-commit Configuration](.pre-commit-config.yaml)
- [Reliability Pattern Checker](scripts/check_reliability_patterns.py)
- [Makefile Commands](Makefile)

## 🔄 Continuous Improvement

This playbook is a living document. When you discover new reliability patterns or testing techniques:

1. **Document the pattern** in this playbook
2. **Add checks** to the reliability pattern checker
3. **Update CI pipeline** if needed
4. **Share learnings** with the team

Remember: **Reliability is everyone's responsibility**. Every line of code is an opportunity to make the system more robust and maintainable.