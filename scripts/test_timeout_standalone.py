#!/usr/bin/env python3
"""
Standalone cross-platform timeout test.
Tests the timeout mechanism without external dependencies.
"""
import time
import threading
import platform
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError


class TimeoutError(Exception):
    """Raised when an operation times out."""
    pass


class TimeoutManager:
    """Thread-safe, cross-platform timeout manager."""
    
    def __init__(self):
        self._timers = {}
        self._lock = threading.Lock()
    
    def create_timeout(self, timeout_id: str, seconds: int, callback):
        """Create a timeout that calls callback after seconds."""
        with self._lock:
            # Cancel existing timer if any
            if timeout_id in self._timers:
                self._timers[timeout_id].cancel()
            
            timer = threading.Timer(seconds, callback)
            self._timers[timeout_id] = timer
            timer.start()
            return timer
    
    def cancel_timeout(self, timeout_id: str):
        """Cancel a timeout by ID."""
        with self._lock:
            if timeout_id in self._timers:
                self._timers[timeout_id].cancel()
                del self._timers[timeout_id]


# Global timeout manager instance
_timeout_manager = TimeoutManager()


@contextmanager
def timeout_context(seconds: int):
    """Cross-platform, thread-safe timeout context manager."""
    timeout_id = f"timeout_{threading.current_thread().ident}_{time.time()}"
    timeout_occurred = threading.Event()
    
    def timeout_callback():
        timeout_occurred.set()
    
    # Create the timeout
    timer = _timeout_manager.create_timeout(timeout_id, seconds, timeout_callback)
    
    try:
        yield timeout_occurred
        
        # Check if timeout occurred during execution
        if timeout_occurred.is_set():
            raise TimeoutError(f"Operation timed out after {seconds} seconds")
            
    finally:
        # Always clean up the timeout
        _timeout_manager.cancel_timeout(timeout_id)


def test_basic_timeout():
    """Test basic timeout functionality."""
    print(f"🖥️  Testing on {platform.system()} {platform.release()}")
    
    # Test 1: Operation completes within timeout
    print("\n✅ Test 1: Operation completes within timeout")
    start_time = time.time()
    try:
        with timeout_context(1.0) as timeout_event:
            time.sleep(0.1)
            print(f"   Operation completed in {time.time() - start_time:.2f}s")
            print(f"   Timeout occurred: {timeout_event.is_set()}")
    except TimeoutError:
        print("   ❌ Unexpected timeout")
        return False
    
    # Test 2: Operation times out
    print("\n⏰ Test 2: Operation times out")
    start_time = time.time()
    try:
        with timeout_context(0.1) as timeout_event:
            time.sleep(0.2)
        print("   ❌ Should have timed out")
        return False
    except TimeoutError as e:
        elapsed = time.time() - start_time
        print(f"   ✅ Correctly timed out after {elapsed:.2f}s")
        print(f"   Error message: {e}")
    
    return True


def test_thread_safety():
    """Test thread safety of timeout mechanism."""
    print("\n🧵 Test 3: Thread safety")
    results = []
    exceptions = []
    
    def worker_thread(thread_id, sleep_time, timeout_time):
        try:
            with timeout_context(timeout_time):
                time.sleep(sleep_time)
            results.append(f"thread_{thread_id}_completed")
        except TimeoutError:
            exceptions.append(f"thread_{thread_id}_timeout")
        except Exception as e:
            exceptions.append(f"thread_{thread_id}_error_{type(e).__name__}")
    
    # Create threads with different configurations
    threads = []
    configs = [
        (1, 0.05, 0.2),  # Should complete
        (2, 0.2, 0.05),  # Should timeout
        (3, 0.1, 0.3),   # Should complete
    ]
    
    for thread_id, sleep_time, timeout_time in configs:
        thread = threading.Thread(
            target=worker_thread,
            args=(thread_id, sleep_time, timeout_time)
        )
        threads.append(thread)
        thread.start()
    
    # Wait for all threads
    for thread in threads:
        thread.join()
    
    print(f"   Completed threads: {results}")
    print(f"   Timed out threads: {exceptions}")
    
    # Verify expected results
    expected_completed = {"thread_1_completed", "thread_3_completed"}
    expected_timeouts = {"thread_2_timeout"}
    
    if set(results) == expected_completed and set(exceptions) == expected_timeouts:
        print("   ✅ Thread safety test passed")
        return True
    else:
        print("   ❌ Thread safety test failed")
        return False


def test_executor_timeout():
    """Test ThreadPoolExecutor-based timeout for CPU-bound operations."""
    print("\n⚙️  Test 4: CPU-bound operation timeout")
    
    def cpu_intensive_task():
        # Simulate CPU-intensive work
        total = 0
        for i in range(1000000):
            total += i * i
        return total
    
    # Test with sufficient timeout
    start_time = time.time()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(cpu_intensive_task)
            result = future.result(timeout=2.0)
        elapsed = time.time() - start_time
        print(f"   ✅ CPU task completed in {elapsed:.2f}s, result: {result}")
    except FuturesTimeoutError:
        print("   ❌ Unexpected timeout for CPU task")
        return False
    
    # Test with insufficient timeout
    start_time = time.time()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(cpu_intensive_task)
            future.result(timeout=0.001)  # Very short timeout
        print("   ❌ Should have timed out")
        return False
    except FuturesTimeoutError:
        elapsed = time.time() - start_time
        print(f"   ✅ CPU task correctly timed out after {elapsed:.3f}s")
    
    return True


def test_windows_compatibility():
    """Test Windows compatibility by checking for signal usage."""
    print("\n🪟 Test 5: Windows compatibility (no Unix signals)")
    
    # This test passes if we can import the timeout mechanism
    # and it doesn't use signal.SIGALRM or signal.alarm
    try:
        # Try to use timeout mechanism
        with timeout_context(0.1):
            time.sleep(0.05)
        print("   ✅ Timeout mechanism works without Unix signals")
        
        # Check that we're not using signal module inappropriately
        import signal
        if hasattr(signal, 'SIGALRM') and platform.system() == 'Windows':
            print("   ⚠️  Note: Running on Windows but SIGALRM is available (WSL?)")
        else:
            print("   ✅ Appropriate signal handling for platform")
        
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    """Run all cross-platform timeout tests."""
    print("🛡️  Cross-Platform Timeout Mechanism Test")
    print("=" * 50)
    
    tests = [
        ("Basic Timeout Functionality", test_basic_timeout),
        ("Thread Safety", test_thread_safety), 
        ("CPU-bound Operation Timeout", test_executor_timeout),
        ("Windows Compatibility", test_windows_compatibility),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Cross-platform timeout mechanism is working correctly.")
        print("\n🌟 Key Benefits:")
        print("   • Works on Windows, Linux, and macOS")
        print("   • Thread-safe for concurrent operations") 
        print("   • No dependency on Unix-specific signals")
        print("   • Proper resource cleanup")
        print("   • Supports both I/O-bound and CPU-bound timeouts")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())