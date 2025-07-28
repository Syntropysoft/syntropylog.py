#!/usr/bin/env python3
"""
Standalone logger test - zero external dependencies.

This example demonstrates the ultra-optimized standalone logger.
"""

import asyncio
import time
import sys
import os

# Add the syntropylog directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'syntropylog'))

from standalone_logger import StandaloneLogger, LogLevel, StandaloneLoggerFactory


async def main():
    """Main example function."""
    print("🚀 SyntropyLog Python - Standalone Ultra-Optimized Logger")
    print("=" * 60)
    
    # Create standalone ultra-fast logger
    logger = await StandaloneLoggerFactory.create_logger(LogLevel.INFO)
    
    print("\n📝 Basic logging:")
    logger.info("Application started")
    logger.warn("This is a warning message")
    logger.error("This is an error message")
    logger.debug("This debug message won't show (level is INFO)")
    
    print("\n📊 Performance test:")
    start_time = time.time()
    
    # Log 1000 messages for performance test
    for i in range(1000):
        logger.info(f"Performance test message {i}", 
                   user_id=f"user_{i}", 
                   action="test",
                   timestamp=time.time())
    
    end_time = time.time()
    duration = end_time - start_time
    throughput = 1000 / duration
    
    print(f"✅ Logged 1000 messages in {duration:.3f}s")
    print(f"🚀 Throughput: {throughput:.0f} messages/second")
    
    # Add context
    logger.add_context("session_id", "session_123")
    logger.add_context("environment", "development")
    
    print("\n🔗 Context logging:")
    logger.info("User action", user_id="123", action="login")
    logger.warn("Database slow", query_time=1500, table="users")
    
    print("\n🔄 Async operations test:")
    # Test async operations
    tasks = []
    for i in range(10):
        task = asyncio.create_task(log_async(logger, i))
        tasks.append(task)
    
    await asyncio.gather(*tasks)
    
    print("\n🛑 Shutting down...")
    await logger.shutdown()
    print("✅ Logger shutdown complete")


async def log_async(logger: StandaloneLogger, task_id: int):
    """Async logging function for testing."""
    await asyncio.sleep(0.1)  # Simulate async work
    logger.info(f"Async task completed", task_id=task_id, status="success")


if __name__ == "__main__":
    asyncio.run(main()) 