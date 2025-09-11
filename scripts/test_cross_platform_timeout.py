#!/usr/bin/env python3
"""
Cross-platform timeout demonstration script.
Shows that the new timeout mechanism works on Windows, Linux, and macOS.
"""
import sys
import time
import platform
from pathlib import Path

# Add the worker module to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "worker"))

from worker.services import timeout_context, TimeoutError


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
    
    # Test 3: Nested timeout contexts
    print("\n🔄 Test 3: Nested timeout contexts")
    try:
        with timeout_context(0.5):
            print("   Outer timeout context active")
            try:
                with timeout_context(0.1):
                    print("   Inner timeout context active")
                    time.sleep(0.2)
                print("   ❌ Inner timeout should have triggered")
                return False
            except TimeoutError:
                print("   ✅ Inner timeout triggered correctly")
            
            # Outer context should still be active
            time.sleep(0.1)
            print("   ✅ Outer timeout context still active")
    except TimeoutError:
        print("   ❌ Outer timeout should not have triggered")
        return False
    
    return True


def test_thread_safety():
    """Test thread safety of timeout mechanism."""
    import threading
    
    print("\n🧵 Test 4: Thread safety")
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


def test_no_signal_dependency():
    """Verify that the implementation doesn't use Unix-specific signals."""
    print("\n🚫 Test 5: No Unix signal dependency")
    
    # Check if signal module is imported
    import worker.services
    
    # Read the source file
    source_file = worker.services.__file__
    with open(source_file, 'r') as f:
        content = f.read()
    
    # Check for Unix-specific signal usage
    unix_signals = ['SIGALRM', 'signal.alarm', 'signal.signal']
    found_signals = []
    
    for sig in unix_signals:
        if sig in content:
            found_signals.append(sig)
    
    if found_signals:
        print(f"   ❌ Found Unix-specific signals: {found_signals}")
        return False
    else:
        print("   ✅ No Unix-specific signal dependencies found")
        return True


def main():
    """Run all cross-platform timeout tests."""
    print("🛡️  Cross-Platform Timeout Mechanism Test")
    print("=" * 50)
    
    tests = [
        ("Basic Timeout Functionality", test_basic_timeout),
        ("Thread Safety", test_thread_safety),
        ("No Signal Dependencies", test_no_signal_dependency),
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
    
    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Cross-platform timeout mechanism is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())