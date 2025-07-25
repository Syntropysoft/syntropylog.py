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
from .logger import Logger, LoggerFactory
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
    'Logger',
    'LoggerFactory',
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
def _signal_handler(signum: int, frame: Any) -> None:
    """
    Handle shutdown signals (SIGINT, SIGTERM) gracefully.
    
    This ensures that all resources are properly cleaned up when the application
    receives a termination signal.
    
    Args:
        signum: The signal number
        frame: The current stack frame
    """
    print(f"\nReceived signal {signum}. Shutting down gracefully...")
    asyncio.create_task(syntropy_log.shutdown())
    sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler) 