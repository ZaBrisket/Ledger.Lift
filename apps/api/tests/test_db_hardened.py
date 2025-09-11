"""
Comprehensive tests for hardened database module.
Tests retry logic, timeouts, connection pooling, and error handling.
"""
import pytest
import time
import threading
from unittest.mock import patch, MagicMock, PropertyMock
from sqlalchemy import create_engine, event
from sqlalchemy.exc import (
    DisconnectionError, OperationalError, TimeoutError,
    InterfaceError, DatabaseError, IntegrityError
)
from sqlalchemy.pool import QueuePool, NullPool, StaticPool
from app.db import (
    DatabaseManager, is_retriable_error, exponential_backoff_with_jitter,
    retry_database_operation, db_manager
)

class TestRetriableErrors:
    """Test suite for retriable error detection."""
    
    @pytest.mark.parametrize("error,expected", [
        # Retriable exceptions
        (DisconnectionError("Connection lost", None, None), True),
        (OperationalError("Connection timeout", None, None), True),
        (TimeoutError(), True),
        (InterfaceError("Interface error", None, None), True),
        
        # Retriable error patterns
        (DatabaseError("Connection refused", None, None), True),
        (DatabaseError("Too many connections", None, None), True),
        (DatabaseError("Database is locked", None, None), True),
        (DatabaseError("Could not connect to server", None, None), True),
        (DatabaseError("Server closed the connection", None, None), True),
        (DatabaseError("Connection reset by peer", None, None), True),
        (DatabaseError("Broken pipe", None, None), True),
        
        # Non-retriable errors
        (IntegrityError("Unique constraint violation", None, None), False),
        (DatabaseError("Syntax error", None, None), False),
        (ValueError("Invalid value"), False),
        (TypeError("Type error"), False),
    ])
    def test_is_retriable_error(self, error, expected):
        """Test retriable error detection."""
        assert is_retriable_error(error) == expected

class TestExponentialBackoff:
    """Test suite for exponential backoff calculation."""
    
    def test_exponential_growth(self):
        """Test exponential growth of delays."""
        # No jitter for predictable testing
        assert exponential_backoff_with_jitter(0, base_delay=0.1, jitter=0) == 0.1
        assert exponential_backoff_with_jitter(1, base_delay=0.1, jitter=0) == 0.2
        assert exponential_backoff_with_jitter(2, base_delay=0.1, jitter=0) == 0.4
        assert exponential_backoff_with_jitter(3, base_delay=0.1, jitter=0) == 0.8
    
    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        delay = exponential_backoff_with_jitter(10, base_delay=1.0, max_delay=5.0, jitter=0)
        assert delay == 5.0
    
    def test_jitter_application(self):
        """Test jitter adds randomness to delay."""
        delays = []
        for _ in range(10):
            delay = exponential_backoff_with_jitter(2, base_delay=1.0, jitter=0.5)
            delays.append(delay)
        
        # Base delay for attempt 2 is 4.0
        # With 50% jitter, should be between 2.0 and 6.0
        assert all(2.0 <= d <= 6.0 for d in delays)
        # Should have variation
        assert len(set(delays)) > 1

class TestRetryDecorator:
    """Test suite for retry decorator."""
    
    def test_successful_first_attempt(self):
        """Test function succeeds on first attempt."""
        mock_func = MagicMock(return_value="success")
        
        @retry_database_operation(max_attempts=3)
        def test_func():
            return mock_func()
        
        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 1
    
    def test_retry_on_disconnection(self):
        """Test retry on disconnection errors."""
        mock_func = MagicMock(side_effect=[
            DisconnectionError("Lost connection", None, None),
            DisconnectionError("Lost connection", None, None),
            "success"
        ])
        
        @retry_database_operation(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()
        
        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 3
    
    def test_no_retry_on_non_retriable(self):
        """Test no retry on non-retriable errors."""
        mock_func = MagicMock(side_effect=IntegrityError("Constraint violation", None, None))
        
        @retry_database_operation(max_attempts=3)
        def test_func():
            return mock_func()
        
        with pytest.raises(IntegrityError):
            test_func()
        
        assert mock_func.call_count == 1
    
    def test_max_attempts_exceeded(self):
        """Test failure after max attempts."""
        mock_func = MagicMock(side_effect=TimeoutError())
        
        @retry_database_operation(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()
        
        with pytest.raises(TimeoutError):
            test_func()
        
        assert mock_func.call_count == 3

class TestDatabaseManager:
    """Test suite for enhanced database manager."""
    
    @patch('app.db.create_engine')
    def test_initialization_with_retry(self, mock_create_engine):
        """Test database initialization with retry on failure."""
        # First attempt fails, second succeeds
        mock_engine = MagicMock()
        mock_create_engine.side_effect = [
            OperationalError("Connection failed", None, None),
            mock_engine
        ]
        
        manager = DatabaseManager()
        assert manager.engine == mock_engine
        assert mock_create_engine.call_count == 2
    
    def test_pool_class_selection(self):
        """Test correct pool class selection based on database URL."""
        with patch('app.db.settings') as mock_settings:
            # SQLite memory
            mock_settings.database_url = "sqlite:///:memory:"
            manager = DatabaseManager()
            assert isinstance(manager.engine.pool, StaticPool)
            
            # SQLite file
            mock_settings.database_url = "sqlite:///test.db"
            manager = DatabaseManager()
            assert isinstance(manager.engine.pool, NullPool)
            
            # PostgreSQL
            mock_settings.database_url = "postgresql://user:pass@localhost/db"
            manager = DatabaseManager()
            assert isinstance(manager.engine.pool, QueuePool)
    
    @patch('app.db.create_engine')
    def test_connection_validation(self, mock_create_engine):
        """Test connection validation on initialization."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine
        
        manager = DatabaseManager()
        
        # Verify validation query was executed
        mock_conn.execute.assert_called()
        call_args = mock_conn.execute.call_args[0][0]
        assert "SELECT 1" in str(call_args)
    
    def test_session_context_manager_success(self):
        """Test successful session context manager."""
        manager = DatabaseManager()
        
        with manager.get_session() as session:
            # Simulate query execution
            result = session.execute("SELECT 1")
            assert result is not None
        
        # Check statistics updated
        stats = manager.get_statistics()
        assert stats['total_queries'] >= 1
        assert stats['successful_queries'] >= 1
    
    def test_session_context_manager_rollback(self):
        """Test session rollback on error."""
        manager = DatabaseManager()
        
        with pytest.raises(DatabaseError):
            with manager.get_session() as session:
                # Simulate error
                raise DatabaseError("Test error", None, None)
        
        # Check statistics updated
        stats = manager.get_statistics()
        assert stats['failed_queries'] >= 1
    
    @patch('app.db.time.time')
    def test_slow_query_detection(self, mock_time):
        """Test slow query detection."""
        manager = DatabaseManager()
        manager._slow_query_threshold = 1.0  # 1 second threshold
        
        # Simulate slow query
        mock_time.side_effect = [0, 2.0]  # 2 second duration
        
        with manager.get_session() as session:
            pass
        
        stats = manager.get_statistics()
        assert stats['slow_queries'] >= 1
    
    def test_health_check_caching(self):
        """Test health check result caching."""
        manager = DatabaseManager()
        manager._health_cache_ttl = 1  # 1 second cache
        
        # First call
        health1 = manager.health_check()
        assert health1['status'] in ['healthy', 'degraded', 'unhealthy']
        
        # Second call should return cached result
        health2 = manager.health_check()
        assert health1 == health2
        
        # Wait for cache expiry
        time.sleep(1.1)
        
        # Third call should be fresh
        health3 = manager.health_check()
        assert health3['timestamp'] > health2['timestamp']
    
    def test_health_check_comprehensive(self):
        """Test comprehensive health check."""
        manager = DatabaseManager()
        health = manager.health_check()
        
        # Check structure
        assert 'status' in health
        assert 'timestamp' in health
        assert 'checks' in health
        
        # Check individual checks
        assert 'connectivity' in health['checks']
        assert 'session' in health['checks']
        assert 'connection_pool' in health['checks']
        
        # Check statistics
        assert 'statistics' in health
        assert 'pool_status' in health
    
    @patch('app.db.DatabaseManager._get_pool_status')
    def test_health_check_degraded_pool(self, mock_pool_status):
        """Test health check shows degraded when pool utilization is high."""
        manager = DatabaseManager()
        
        # Mock high pool utilization
        mock_pool_status.return_value = {
            'pool_size': 10,
            'checked_out': 9,
            'utilization': 0.9
        }
        
        health = manager.health_check()
        assert health['status'] == 'degraded'
        assert 'pool utilization high' in health.get('message', '')
    
    def test_execute_with_timeout(self):
        """Test query execution with timeout."""
        manager = DatabaseManager()
        
        # Should succeed with reasonable timeout
        result = manager.execute_with_timeout("SELECT 1", timeout=5)
        assert result.scalar() == 1
        
        # Note: Actually testing timeout behavior would require a slow query
    
    def test_statistics_tracking(self):
        """Test statistics tracking."""
        manager = DatabaseManager()
        manager.reset_statistics()
        
        # Execute some operations
        with manager.get_session() as session:
            session.execute("SELECT 1")
        
        stats = manager.get_statistics()
        assert stats['total_queries'] == 1
        assert stats['successful_queries'] == 1
        assert stats['success_rate'] == 1.0
        assert stats['error_rate'] == 0.0
    
    def test_connection_validation(self):
        """Test connection validation method."""
        manager = DatabaseManager()
        
        # Should return True for valid connection
        assert manager.validate_connection(timeout=5) is True
        
        # Test with closed engine
        manager.engine.dispose()
        assert manager.validate_connection(timeout=1) is False
    
    def test_context_manager_support(self):
        """Test DatabaseManager as context manager."""
        with DatabaseManager() as manager:
            assert manager.engine is not None
            assert manager.SessionLocal is not None
        
        # Engine should be disposed after exit
        assert manager.engine.pool.checkedout() == 0

class TestConcurrency:
    """Test suite for concurrent access."""
    
    def test_concurrent_session_creation(self):
        """Test concurrent session creation is thread-safe."""
        manager = DatabaseManager()
        results = []
        
        def create_sessions():
            for _ in range(10):
                with manager.get_session() as session:
                    result = session.execute("SELECT 1").scalar()
                    results.append(result)
        
        threads = []
        for _ in range(5):
            t = threading.Thread(target=create_sessions)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All queries should succeed
        assert len(results) == 50
        assert all(r == 1 for r in results)
        
        # Statistics should be consistent
        stats = manager.get_statistics()
        assert stats['total_queries'] == 50
        assert stats['successful_queries'] == 50
    
    def test_statistics_thread_safety(self):
        """Test statistics updates are thread-safe."""
        manager = DatabaseManager()
        manager.reset_statistics()
        
        def perform_operations():
            for _ in range(100):
                with manager._stats_lock:
                    manager._stats['total_queries'] += 1
                    manager._stats['successful_queries'] += 1
        
        threads = []
        for _ in range(10):
            t = threading.Thread(target=perform_operations)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        stats = manager.get_statistics()
        assert stats['total_queries'] == 1000
        assert stats['successful_queries'] == 1000

class TestEdgeCases:
    """Test suite for edge cases and error conditions."""
    
    def test_uninitialized_session_factory(self):
        """Test error when SessionLocal is not initialized."""
        manager = DatabaseManager()
        manager.SessionLocal = None
        
        with pytest.raises(RuntimeError, match="Database not initialized"):
            with manager.get_session():
                pass
    
    @patch('app.db.DatabaseManager._validate_connection')
    def test_validation_failure_on_init(self, mock_validate):
        """Test handling of validation failure during initialization."""
        mock_validate.side_effect = DatabaseError("Validation failed", None, None)
        
        with pytest.raises(DatabaseError):
            DatabaseManager()
    
    def test_pool_status_error_handling(self):
        """Test pool status handles errors gracefully."""
        manager = DatabaseManager()
        
        # Mock engine with no pool
        manager.engine = MagicMock()
        manager.engine.pool = None
        
        status = manager._get_pool_status()
        assert 'error' in status