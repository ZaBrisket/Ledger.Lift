"""
Tests for cross-platform, thread-safe timeout mechanism.
Ensures timeout functionality works on Windows, Linux, and macOS.
"""
import pytest
import time
import threading
from unittest.mock import Mock, patch
from concurrent.futures import TimeoutError as FuturesTimeoutError

from worker.services import (
    TimeoutManager, timeout_context, executor_timeout_context, 
    TimeoutError, _timeout_manager
)


class TestTimeoutManager:
    """Test the TimeoutManager class for thread safety and cross-platform compatibility."""
    
    def test_timeout_manager_initialization(self):
        """Test TimeoutManager initializes correctly."""
        tm = TimeoutManager()
        assert tm._timers == {}
        assert tm._lock is not None
    
    def test_create_and_cancel_timeout(self):
        """Test creating and canceling timeouts."""
        tm = TimeoutManager()
        callback = Mock()
        
        # Create timeout
        timer = tm.create_timeout("test1", 0.1, callback)
        assert "test1" in tm._timers
        assert timer is not None
        
        # Cancel timeout
        tm.cancel_timeout("test1")
        assert "test1" not in tm._timers
        
        # Callback should not have been called
        time.sleep(0.2)
        callback.assert_not_called()
    
    def test_timeout_callback_execution(self):
        """Test that timeout callbacks are executed."""
        tm = TimeoutManager()
        callback = Mock()
        
        # Create short timeout
        tm.create_timeout("test1", 0.05, callback)
        
        # Wait for timeout to trigger
        time.sleep(0.1)
        
        # Callback should have been called
        callback.assert_called_once()
        
        # Cleanup
        tm.cleanup_all()
    
    def test_replace_existing_timeout(self):
        """Test replacing an existing timeout."""
        tm = TimeoutManager()
        callback1 = Mock()
        callback2 = Mock()
        
        # Create first timeout
        tm.create_timeout("test1", 0.1, callback1)
        
        # Replace with second timeout
        tm.create_timeout("test1", 0.1, callback2)
        
        # Should still have only one timeout with the same ID
        assert len(tm._timers) == 1
        assert "test1" in tm._timers
        
        # Wait for timeout
        time.sleep(0.15)
        
        # Only second callback should be called
        callback1.assert_not_called()
        callback2.assert_called_once()
        
        # Cleanup
        tm.cleanup_all()
    
    def test_cleanup_all_timeouts(self):
        """Test cleaning up all timeouts."""
        tm = TimeoutManager()
        callback1 = Mock()
        callback2 = Mock()
        
        # Create multiple timeouts
        tm.create_timeout("test1", 0.1, callback1)
        tm.create_timeout("test2", 0.1, callback2)
        
        assert len(tm._timers) == 2
        
        # Cleanup all
        tm.cleanup_all()
        
        assert len(tm._timers) == 0
        
        # Wait and verify callbacks were not called
        time.sleep(0.15)
        callback1.assert_not_called()
        callback2.assert_not_called()
    
    def test_thread_safety(self):
        """Test TimeoutManager thread safety with concurrent operations."""
        tm = TimeoutManager()
        callbacks_called = []
        
        def create_timeouts(thread_id):
            for i in range(5):
                callback = Mock()
                callback.side_effect = lambda: callbacks_called.append(f"{thread_id}_{i}")
                tm.create_timeout(f"thread_{thread_id}_timeout_{i}", 0.05, callback)
        
        # Create timeouts from multiple threads
        threads = []
        for thread_id in range(3):
            thread = threading.Thread(target=create_timeouts, args=(thread_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have 15 timers (3 threads × 5 timeouts each)
        assert len(tm._timers) == 15
        
        # Wait for timeouts to trigger
        time.sleep(0.1)
        
        # Cleanup
        tm.cleanup_all()


class TestTimeoutContext:
    """Test the cross-platform timeout_context function."""
    
    def test_timeout_context_no_timeout(self):
        """Test timeout_context when operation completes within timeout."""
        start_time = time.time()
        
        with timeout_context(1.0) as timeout_event:
            time.sleep(0.1)
            # Check that timeout hasn't occurred
            assert not timeout_event.is_set()
        
        elapsed = time.time() - start_time
        assert elapsed < 1.0
    
    def test_timeout_context_with_timeout(self):
        """Test timeout_context when operation exceeds timeout."""
        start_time = time.time()
        
        with pytest.raises(TimeoutError, match="Operation timed out after 0.1 seconds"):
            with timeout_context(0.1) as timeout_event:
                time.sleep(0.2)
        
        elapsed = time.time() - start_time
        # Should have timed out quickly
        assert elapsed < 0.5
    
    def test_timeout_context_cleanup(self):
        """Test that timeout_context properly cleans up resources."""
        initial_timer_count = len(_timeout_manager._timers)
        
        with timeout_context(1.0):
            # Timer should be active during context
            assert len(_timeout_manager._timers) > initial_timer_count
        
        # Timer should be cleaned up after context
        assert len(_timeout_manager._timers) == initial_timer_count
    
    def test_timeout_context_exception_cleanup(self):
        """Test cleanup when exception occurs within timeout context."""
        initial_timer_count = len(_timeout_manager._timers)
        
        with pytest.raises(ValueError):
            with timeout_context(1.0):
                raise ValueError("Test exception")
        
        # Timer should still be cleaned up
        assert len(_timeout_manager._timers) == initial_timer_count
    
    def test_timeout_context_thread_safety(self):
        """Test timeout_context with concurrent usage from multiple threads."""
        results = []
        exceptions = []
        
        def worker_thread(thread_id, sleep_time, timeout_time):
            try:
                with timeout_context(timeout_time):
                    time.sleep(sleep_time)
                results.append(f"thread_{thread_id}_completed")
            except TimeoutError as e:
                exceptions.append(f"thread_{thread_id}_timeout")
            except Exception as e:
                exceptions.append(f"thread_{thread_id}_error_{type(e).__name__}")
        
        threads = []
        
        # Create threads with different sleep/timeout combinations
        thread_configs = [
            (1, 0.05, 0.2),  # Should complete
            (2, 0.2, 0.05),  # Should timeout
            (3, 0.1, 0.3),   # Should complete
            (4, 0.3, 0.1),   # Should timeout
        ]
        
        for thread_id, sleep_time, timeout_time in thread_configs:
            thread = threading.Thread(
                target=worker_thread, 
                args=(thread_id, sleep_time, timeout_time)
            )
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Verify expected results
        assert "thread_1_completed" in results
        assert "thread_3_completed" in results
        assert "thread_2_timeout" in exceptions
        assert "thread_4_timeout" in exceptions
        
        # All timers should be cleaned up
        assert len(_timeout_manager._timers) == 0


class TestExecutorTimeoutContext:
    """Test the ThreadPoolExecutor-based timeout context."""
    
    def test_executor_timeout_no_timeout(self):
        """Test executor timeout when operation completes within timeout."""
        start_time = time.time()
        
        with executor_timeout_context(1.0):
            time.sleep(0.1)
        
        elapsed = time.time() - start_time
        assert elapsed < 1.0
    
    def test_executor_timeout_with_timeout(self):
        """Test executor timeout when operation exceeds timeout."""
        start_time = time.time()
        
        with pytest.raises(TimeoutError, match="Operation timed out after 0.1 seconds"):
            with executor_timeout_context(0.1):
                time.sleep(0.2)
        
        elapsed = time.time() - start_time
        # Should have timed out quickly
        assert elapsed < 0.5


class TestCrossPlatformCompatibility:
    """Test cross-platform compatibility of timeout mechanisms."""
    
    def test_windows_compatibility(self):
        """Test that timeout works on Windows (no signal dependency)."""
        # This test verifies that we don't use signal.SIGALRM or signal.alarm
        # which are Unix-specific
        
        with timeout_context(0.1):
            # Should work without importing signal module
            pass
        
        # Verify no signal module usage in our timeout implementation
        import worker.services
        source_code = worker.services.__file__
        with open(source_code, 'r') as f:
            content = f.read()
        
        # Should not contain Unix-specific signal usage
        assert 'signal.SIGALRM' not in content
        assert 'signal.alarm' not in content
    
    def test_thread_local_timeout_ids(self):
        """Test that timeout IDs are thread-local to prevent conflicts."""
        timeout_ids = []
        
        def capture_timeout_id():
            with patch.object(_timeout_manager, 'create_timeout') as mock_create:
                with timeout_context(1.0):
                    pass
                # Extract the timeout_id from the mock call
                timeout_id = mock_create.call_args[0][0]
                timeout_ids.append(timeout_id)
        
        # Run from multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=capture_timeout_id)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All timeout IDs should be unique (contain different thread IDs)
        assert len(set(timeout_ids)) == len(timeout_ids)
        
        # Each should contain the thread ID
        for timeout_id in timeout_ids:
            assert 'timeout_' in timeout_id
            assert '_' in timeout_id  # Should have thread ID and timestamp


class TestTimeoutIntegration:
    """Test timeout integration with document processing operations."""
    
    def test_timeout_with_mock_operations(self):
        """Test timeout mechanism with mock long-running operations."""
        
        def slow_operation():
            time.sleep(0.2)
            return "completed"
        
        def fast_operation():
            time.sleep(0.05)
            return "completed"
        
        # Fast operation should complete
        with timeout_context(0.1):
            result = fast_operation()
            assert result == "completed"
        
        # Slow operation should timeout
        with pytest.raises(TimeoutError):
            with timeout_context(0.1):
                slow_operation()
    
    def test_timeout_error_messages(self):
        """Test that timeout errors have informative messages."""
        with pytest.raises(TimeoutError) as exc_info:
            with timeout_context(0.05):
                time.sleep(0.1)
        
        error_message = str(exc_info.value)
        assert "timed out after 0.05 seconds" in error_message
    
    def test_nested_timeout_contexts(self):
        """Test that nested timeout contexts work correctly."""
        with timeout_context(0.2):
            # Inner timeout should be more restrictive
            with pytest.raises(TimeoutError):
                with timeout_context(0.05):
                    time.sleep(0.1)
        
        # Outer context should still be active and not timeout
        time.sleep(0.01)  # Small additional delay


class TestTimeoutPerformance:
    """Test timeout mechanism performance characteristics."""
    
    def test_timeout_overhead(self):
        """Test that timeout mechanism has minimal overhead."""
        # Measure time without timeout
        start = time.time()
        for _ in range(100):
            pass
        baseline = time.time() - start
        
        # Measure time with timeout
        start = time.time()
        for _ in range(100):
            with timeout_context(1.0):
                pass
        with_timeout = time.time() - start
        
        # Timeout overhead should be reasonable (less than 10x baseline)
        assert with_timeout < baseline * 10
    
    def test_concurrent_timeout_performance(self):
        """Test performance with many concurrent timeouts."""
        start_time = time.time()
        
        def worker():
            with timeout_context(0.1):
                time.sleep(0.05)
        
        threads = []
        for _ in range(20):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        elapsed = time.time() - start_time
        # Should complete reasonably quickly (less than 2 seconds)
        assert elapsed < 2.0
        
        # All timers should be cleaned up
        assert len(_timeout_manager._timers) == 0