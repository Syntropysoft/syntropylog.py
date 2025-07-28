#!/usr/bin/env python3
"""
Transports test - testing all console transports.

This example demonstrates all the different console transports available.
"""

import asyncio
import time
import sys
import os

# Add the syntropylog directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'syntropylog'))

from standalone_logger import (
    StandaloneLogger, 
    LogLevel, 
    StandaloneLoggerFactory,
    ConsoleTransport,
    PythonicConsoleTransport,
    CompactConsoleTransport,
    PrettyConsoleTransport,
    ClassicConsoleTransport
)


async def test_transport(transport_name: str, transport_class, logger: StandaloneLogger):
    """Test a specific transport."""
    print(f"\n{'='*60}")
    print(f"🚀 Testing {transport_name}")
    print(f"{'='*60}")
    
    # Clear existing transports and add the test transport
    logger._transports.clear()
    transport = transport_class()
    logger.add_transport(transport)
    
    # Add some context
    logger.add_context("service", "test-app")
    logger.add_context("version", "1.0.0")
    logger.add_context("environment", "development")
    
    # Test different log levels
    logger.debug("This is a debug message", user_id="123", action="test")
    logger.info("Application started successfully", port=8080, host="localhost")
    logger.warn("Database connection is slow", query_time=1500, table="users")
    logger.error("Failed to process request", error_code=500, path="/api/users")
    
    # Test with complex context
    logger.info("User action completed", 
               user_id="456", 
               action="login",
               metadata={"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"},
               performance={"response_time": 45, "memory_usage": "128MB"})
    
    # Wait a bit for async processing
    await asyncio.sleep(0.1)


async def test_pythonic_transport(logger: StandaloneLogger):
    """Test the Pythonic transport specifically."""
    print(f"\n{'='*60}")
    print(f"🚀 Testing Pythonic Console (Default)")
    print(f"{'='*60}")
    
    # Clear existing transports and add the pythonic transport
    logger._transports.clear()
    transport = PythonicConsoleTransport()
    logger.add_transport(transport)
    
    # Add logger name context (like Python logging)
    logger.add_context("logger_name", "myapp.api")
    logger.add_context("service", "test-app")
    
    # Test different log levels
    logger.debug("This is a debug message", user_id="123", action="test")
    logger.info("Application started successfully", port=8080, host="localhost")
    logger.warn("Database connection is slow", query_time=1500, table="users")
    logger.error("Failed to process request", error_code=500, path="/api/users")
    
    # Test with complex context
    logger.info("User action completed", 
               user_id="456", 
               action="login",
               metadata={"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"},
               performance={"response_time": 45, "memory_usage": "128MB"})
    
    # Wait a bit for async processing
    await asyncio.sleep(0.1)


async def main():
    """Main example function."""
    print("🚀 SyntropyLog Python - Console Transports Test")
    print("=" * 60)
    
    # Create logger
    logger = await StandaloneLoggerFactory.create_logger(LogLevel.DEBUG)
    
    # Test Pythonic transport first (it's the default)
    await test_pythonic_transport(logger)
    
    # Test each transport
    transports = [
        ("JSON Console", ConsoleTransport),
        ("Compact Console", CompactConsoleTransport),
        ("Pretty Console", PrettyConsoleTransport),
        ("Classic Console", ClassicConsoleTransport),
    ]
    
    for transport_name, transport_class in transports:
        await test_transport(transport_name, transport_class, logger)
    
    print(f"\n{'='*60}")
    print("✅ All transports tested successfully!")
    print(f"{'='*60}")
    
    # Shutdown
    await logger.shutdown()


if __name__ == "__main__":
    asyncio.run(main()) 