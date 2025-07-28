#!/usr/bin/env python3
"""
Lifecycle test - testing the complete framework lifecycle.

This example demonstrates the proper initialization, usage, and graceful shutdown
of the SyntropyLog framework, including signal handling and resource cleanup.
"""

import asyncio
import signal
import sys
import os
import time
import threading

# Add the syntropylog directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'syntropylog'))

from syntropylog import syntropy_log


async def custom_shutdown_handler():
    """Custom shutdown handler example."""
    print("🔄 Executing custom shutdown handler...")
    await asyncio.sleep(1)  # Simulate cleanup work
    print("✅ Custom shutdown handler completed")


async def simulate_work():
    """Simulate application work."""
    print("🚀 Starting application work...")
    
    # Add some context
    syntropy_log.add_context("user_id", "12345")
    syntropy_log.add_context("session_id", "session_abc")
    
    # Simulate some logging
    for i in range(5):
        syntropy_log.info(f"Processing task {i}", task_id=i, status="in_progress")
        await asyncio.sleep(0.5)
        
        if i == 2:
            syntropy_log.warn("Database connection slow", query_time=1500)
        
        syntropy_log.info(f"Task {i} completed", task_id=i, status="completed")
    
    print("✅ Application work completed")


async def test_context_manager():
    """Test the context manager functionality."""
    print("\n🔗 Testing context manager...")
    
    async with syntropy_log.context(operation="batch_process", batch_id="batch_001"):
        syntropy_log.info("Starting batch operation")
        
        # Nested context
        async with syntropy_log.context(sub_operation="data_validation"):
            syntropy_log.info("Validating data", records_count=1000)
            await asyncio.sleep(0.2)
            syntropy_log.info("Data validation completed", valid_records=998)
        
        syntropy_log.info("Batch operation completed")


async def test_hot_reload():
    """Test hot-reload capabilities."""
    print("\n🔄 Testing hot-reload capabilities...")
    
    # Change log level
    syntropy_log.set_log_level("debug")
    syntropy_log.debug("This debug message should now be visible")
    
    # Add more context
    syntropy_log.add_context("environment", "development")
    syntropy_log.add_context("version", "1.0.0")
    
    syntropy_log.info("Hot-reload test completed")


async def main():
    """Main example function."""
    print("🚀 SyntropyLog Python - Complete Lifecycle Test")
    print("=" * 60)
    
    try:
        # Initialize the framework
        print("\n📋 Initializing SyntropyLog framework...")
        config = {
            'logger': {
                'level': 'info',
                'transports': ['console']
            },
            'context': {
                'correlation_enabled': True,
                'auto_generate_ids': True
            }
        }
        
        await syntropy_log.init(config)
        print("✅ Framework initialized successfully")
        
        # Add custom shutdown handler
        syntropy_log.add_shutdown_handler(custom_shutdown_handler)
        print("✅ Custom shutdown handler registered")
        
        # Show initial status
        status = syntropy_log.get_status()
        print(f"📊 Framework status: {status['initialized']}")
        print(f"📊 Components available: {len(status['components'])}")
        
        # Test basic functionality
        await simulate_work()
        
        # Test context manager
        await test_context_manager()
        
        # Test hot-reload
        await test_hot_reload()
        
        # Show final status
        final_status = syntropy_log.get_status()
        print(f"\n📊 Final status: {final_status['initialized']}")
        
        print("\n⏳ Waiting 3 seconds before shutdown...")
        print("💡 Try pressing Ctrl+C to test signal handling!")
        await asyncio.sleep(3)
        
    except KeyboardInterrupt:
        print("\n⚠️  Received keyboard interrupt")
    except Exception as error:
        print(f"\n❌ Error during execution: {error}")
    finally:
        # Graceful shutdown
        print("\n🛑 Starting graceful shutdown...")
        shutdown_result = await syntropy_log.shutdown()
        
        print(f"📊 Shutdown result:")
        print(f"   Success: {shutdown_result['success']}")
        print(f"   Duration: {shutdown_result.get('duration', 'N/A'):.2f}s")
        print(f"   Components shutdown: {len(shutdown_result.get('components_shutdown', []))}")
        
        if shutdown_result.get('errors'):
            print(f"   Errors: {len(shutdown_result['errors'])}")
            for error in shutdown_result['errors']:
                print(f"     - {error}")
        
        print("✅ Lifecycle test completed")


def signal_test():
    """Test signal handling in a separate thread."""
    print("\n🧪 Testing signal handling...")
    print("💡 This will simulate SIGTERM in 2 seconds...")
    
    def send_signal():
        time.sleep(2)
        print("📡 Sending SIGTERM signal...")
        os.kill(os.getpid(), signal.SIGTERM)
    
    signal_thread = threading.Thread(target=send_signal, daemon=True)
    signal_thread.start()


if __name__ == "__main__":
    # Uncomment the next line to test signal handling
    # signal_test()
    
    asyncio.run(main())