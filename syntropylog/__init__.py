"""
SyntropyLog Python - From Chaos to Clarity

A comprehensive observability framework for Python applications that provides
structured logging, distributed tracing, and automatic context propagation
without interfering with your application's main flow.

This framework follows the "Silent Observer" philosophy - we report what happened
and nothing more. The logging pipeline never interrupts your application flow,
even if internal components fail.

Key Features:
- Structured logging with automatic context propagation
- Distributed tracing with correlation IDs
- HTTP client instrumentation
- Redis integration for context storage
- Message broker support (Kafka, RabbitMQ, NATS)
- Custom serialization pipeline
- Framework-agnostic testing utilities
- Hot-reload configuration capabilities

Example:
    ```python
    import asyncio
    from syntropylog import syntropy_log
    
    async def main():
        # Initialize the framework
        await syntropy_log.init({
            'logger': {'level': 'info'},
            'redis': {'url': 'redis://localhost:6379'}
        })
        
        # Use the logger with automatic context
        with syntropy_log.context(user_id='123'):
            syntropy_log.info('User action', action='login')
            
        # Graceful shutdown
        await syntropy_log.shutdown()
    
    asyncio.run(main())
    ```

Version: 0.1.0
License: Apache 2.0
Author: Syntropysoft
"""

from typing import Dict, Any, Optional
import asyncio
import signal
import sys

# Core framework imports
from .core import SyntropyLog
from .context import ContextManager
from .logger import UltraFastLogger, LoggerFactory, LogLevel, LogEntry, ConsoleTransport
from .config import Config, ConfigManager

# HTTP instrumentation
from .http import HttpManager, InstrumentedHttpClient

# Redis integration
from .redis import BeaconRedis

# Message brokers
from .brokers import BrokerManager

# Serialization
from .serialization import SerializationManager, SerializerRegistry

# Testing utilities
from .testing import (
    create_test_helper,
    SyntropyLogMock,
    BeaconRedisMock,
    MockHttpClient,
    MockBrokerAdapter,
    MockSerializerRegistry
)

# Main singleton instance
syntropy_log = SyntropyLog()

# Convenience exports
__all__ = [
    # Main instance
    'syntropy_log',
    
    # Core classes
    'SyntropyLog',
    'ContextManager',
    'UltraFastLogger',
    'LoggerFactory',
    'LogLevel',
    'LogEntry',
    'ConsoleTransport',
    'Config',
    'ConfigManager',
    
    # HTTP
    'HttpManager',
    'InstrumentedHttpClient',
    
    # Redis
    'BeaconRedis',
    
    # Brokers
    'BrokerManager',
    
    # Serialization
    'SerializationManager',
    'SerializerRegistry',
    
    # Testing
    'create_test_helper',
    'SyntropyLogMock',
    'BeaconRedisMock',
    'MockHttpClient',
    'MockBrokerAdapter',
    'MockSerializerRegistry'
]

# Version information
__version__ = "0.1.0"
__author__ = "Syntropysoft"
__license__ = "Apache 2.0"

# Graceful shutdown handler
import threading
import time

# Global flag to track shutdown state
_shutdown_event = threading.Event()
_shutdown_in_progress = False

def _signal_handler(signum: int, frame: Any) -> None:
    """
    Handle shutdown signals (SIGINT, SIGTERM) gracefully.
    
    This ensures that all resources are properly cleaned up when the application
    receives a termination signal. Handles Kubernetes graceful shutdown properly.
    
    Args:
        signum: The signal number
        frame: The current stack frame
    """
    global _shutdown_in_progress
    
    if _shutdown_in_progress:
        print(f"\nReceived signal {signum} during shutdown. Forcing exit...")
        sys.exit(1)
    
    _shutdown_in_progress = True
    print(f"\nReceived signal {signum}. Starting graceful shutdown...")
    
    # Set shutdown event to notify any waiting threads
    _shutdown_event.set()
    
    # Start shutdown in a separate thread to avoid blocking signal handler
    def shutdown_worker():
        try:
            # Get the current event loop or create a new one
            try:
                loop = asyncio.get_running_loop()
                # If we're in an event loop, schedule the shutdown
                future = asyncio.run_coroutine_threadsafe(
                    _graceful_shutdown_with_timeout(), loop
                )
                # Wait for shutdown to complete with timeout
                result = future.result(timeout=30)  # 30 second timeout
                print(f"✅ Graceful shutdown completed: {result}")
            except RuntimeError:
                # No event loop running, create one
                result = asyncio.run(_graceful_shutdown_with_timeout())
                print(f"✅ Graceful shutdown completed: {result}")
        except Exception as error:
            print(f"❌ Shutdown failed: {error}")
        finally:
            # Force exit after shutdown attempt
            sys.exit(0)
    
    # Start shutdown in background thread
    shutdown_thread = threading.Thread(target=shutdown_worker, daemon=True)
    shutdown_thread.start()

async def _graceful_shutdown_with_timeout(timeout: int = 30) -> Dict[str, Any]:
    """
    Perform graceful shutdown with timeout protection.
    
    Args:
        timeout: Maximum time to wait for shutdown in seconds
        
    Returns:
        Shutdown result dictionary
    """
    try:
        # Start shutdown with timeout
        shutdown_task = asyncio.create_task(syntropy_log.shutdown())
        
        # Wait for shutdown to complete or timeout
        result = await asyncio.wait_for(shutdown_task, timeout=timeout)
        return result
        
    except asyncio.TimeoutError:
        print(f"⚠️  Shutdown timeout after {timeout}s. Forcing exit...")
        return {"success": False, "error": "shutdown_timeout"}
    except Exception as error:
        print(f"❌ Shutdown error: {error}")
        return {"success": False, "error": str(error)}

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler) 