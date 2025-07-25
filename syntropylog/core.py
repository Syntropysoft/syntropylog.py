"""
Core SyntropyLog Framework

This module contains the main SyntropyLog class that orchestrates all framework
components and manages the application lifecycle. It follows the singleton pattern
to ensure consistent state across the application.

The framework implements the "Silent Observer" philosophy - it observes and reports
without interfering with the main application flow.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from .config import Config, ConfigManager
from .context import ContextManager
from .logger import Logger, LoggerFactory
from .http import HttpManager
from .redis import BeaconRedis
from .brokers import BrokerManager
from .serialization import SerializationManager


class SyntropyLog:
    """
    Main SyntropyLog framework class.
    
    This is the central orchestrator for all framework components. It manages
    the lifecycle of the framework, coordinates between different modules,
    and provides a unified interface for logging and observability.
    
    The class follows the singleton pattern to ensure consistent state
    across the entire application.
    
    Attributes:
        _initialized (bool): Whether the framework has been initialized
        _config (ConfigManager): Configuration manager instance
        _context (ContextManager): Context manager for correlation IDs
        _logger (Logger): Main logger instance
        _http (HttpManager): HTTP instrumentation manager
        _redis (BeaconRedis): Redis client for context storage
        _brokers (BrokerManager): Message broker manager
        _serialization (SerializationManager): Serialization pipeline manager
        _shutdown_handlers (List): List of shutdown handlers to execute
    """
    
    def __init__(self):
        """Initialize the SyntropyLog framework instance."""
        self._initialized: bool = False
        self._config: Optional[ConfigManager] = None
        self._context: Optional[ContextManager] = None
        self._logger: Optional[Logger] = None
        self._http: Optional[HttpManager] = None
        self._redis: Optional[BeaconRedis] = None
        self._brokers: Optional[BrokerManager] = None
        self._serialization: Optional[SerializationManager] = None
        self._shutdown_handlers: List[callable] = []
        
        # Initialize internal logger for framework operations
        self._internal_logger = logging.getLogger('syntropylog.core')
        self._internal_logger.setLevel(logging.WARNING)
    
    async def init(self, config: Dict[str, Any]) -> 'SyntropyLog':
        """
        Initialize the SyntropyLog framework.
        
        This method sets up all framework components in the correct order:
        1. Configuration management
        2. Context management
        3. Logger system
        4. HTTP instrumentation
        5. Redis integration
        6. Message brokers
        7. Serialization pipeline
        
        All components are created as singletons and cannot be redefined
        after initialization.
        
        Args:
            config: Configuration dictionary containing framework settings
            
        Returns:
            Self instance for method chaining
            
        Raises:
            RuntimeError: If framework is already initialized
            ValueError: If configuration is invalid
        """
        if self._initialized:
            raise RuntimeError("SyntropyLog is already initialized")
        
        try:
            self._internal_logger.info("Initializing SyntropyLog framework...")
            
            # 1. Initialize configuration
            self._config = ConfigManager(config)
            await self._config.validate()
            
            # 2. Initialize context management
            self._context = ContextManager()
            await self._context.init(self._config.get_context_config())
            
            # 3. Initialize logger system
            logger_factory = LoggerFactory()
            self._logger = await logger_factory.create_logger(
                self._config.get_logger_config(),
                self._context
            )
            
            # 4. Initialize HTTP instrumentation
            self._http = HttpManager()
            await self._http.init(self._config.get_http_config(), self._context)
            
            # 5. Initialize Redis integration
            redis_config = self._config.get_redis_config()
            if redis_config and redis_config.get('enabled', True):
                self._redis = BeaconRedis()
                await self._redis.init(redis_config, self._context)
            
            # 6. Initialize message brokers
            broker_config = self._config.get_broker_config()
            if broker_config and broker_config.get('enabled', False):
                self._brokers = BrokerManager()
                await self._brokers.init(broker_config, self._context)
            
            # 7. Initialize serialization pipeline
            self._serialization = SerializationManager()
            await self._serialization.init(self._config.get_serialization_config())
            
            self._initialized = True
            self._internal_logger.info("SyntropyLog framework initialized successfully")
            
        except Exception as error:
            self._internal_logger.error(f"Failed to initialize SyntropyLog: {error}")
            await self._cleanup()
            raise
        
        return self
    
    async def shutdown(self) -> Dict[str, Any]:
        """
        Gracefully shutdown the SyntropyLog framework.
        
        This method ensures that all resources are properly cleaned up:
        1. Execute registered shutdown handlers
        2. Close HTTP connections
        3. Close Redis connections
        4. Close broker connections
        5. Flush any pending logs
        6. Reset internal state
        
        The shutdown process follows the "Silent Observer" philosophy -
        errors during shutdown are logged but don't prevent the process.
        
        Returns:
            Dictionary with shutdown status information
        """
        if not self._initialized:
            return {"success": True, "message": "Framework not initialized"}
        
        shutdown_result = {"success": True, "errors": []}
        
        try:
            self._internal_logger.info("Shutting down SyntropyLog framework...")
            
            # Execute registered shutdown handlers
            for handler in self._shutdown_handlers:
                try:
                    await handler()
                except Exception as error:
                    shutdown_result["errors"].append(f"Shutdown handler error: {error}")
                    self._internal_logger.error(f"Shutdown handler failed: {error}")
            
            # Shutdown components in reverse order
            if self._serialization:
                try:
                    await self._serialization.shutdown()
                except Exception as error:
                    shutdown_result["errors"].append(f"Serialization shutdown error: {error}")
            
            if self._brokers:
                try:
                    await self._brokers.shutdown()
                except Exception as error:
                    shutdown_result["errors"].append(f"Broker shutdown error: {error}")
            
            if self._redis:
                try:
                    await self._redis.shutdown()
                except Exception as error:
                    shutdown_result["errors"].append(f"Redis shutdown error: {error}")
            
            if self._http:
                try:
                    await self._http.shutdown()
                except Exception as error:
                    shutdown_result["errors"].append(f"HTTP shutdown error: {error}")
            
            if self._logger:
                try:
                    await self._logger.shutdown()
                except Exception as error:
                    shutdown_result["errors"].append(f"Logger shutdown error: {error}")
            
            if self._context:
                try:
                    await self._context.shutdown()
                except Exception as error:
                    shutdown_result["errors"].append(f"Context shutdown error: {error}")
            
            await self._cleanup()
            self._internal_logger.info("SyntropyLog framework shutdown completed")
            
        except Exception as error:
            shutdown_result["success"] = False
            shutdown_result["errors"].append(f"General shutdown error: {error}")
            self._internal_logger.error(f"Shutdown failed: {error}")
        
        return shutdown_result
    
    async def _cleanup(self) -> None:
        """
        Clean up internal state after shutdown.
        
        This method resets all internal references and state to allow
        for potential re-initialization if needed.
        """
        self._initialized = False
        self._config = None
        self._context = None
        self._logger = None
        self._http = None
        self._redis = None
        self._brokers = None
        self._serialization = None
        self._shutdown_handlers.clear()
    
    def add_shutdown_handler(self, handler: callable) -> None:
        """
        Register a shutdown handler to be executed during framework shutdown.
        
        Shutdown handlers are executed in the order they were registered.
        Each handler should be an async function that performs cleanup
        operations for a specific component or resource.
        
        Args:
            handler: Async function to execute during shutdown
        """
        if not asyncio.iscoroutinefunction(handler):
            raise ValueError("Shutdown handler must be an async function")
        
        self._shutdown_handlers.append(handler)
    
    @asynccontextmanager
    async def context(self, **context_data: Any):
        """
        Context manager for automatic context propagation.
        
        This method provides a context manager that automatically propagates
        context data to all logging operations within its scope. The context
        is automatically cleaned up when the context manager exits.
        
        Args:
            **context_data: Key-value pairs to add to the context
            
        Example:
            ```python
            async with syntropy_log.context(user_id='123', session_id='abc'):
                logger.info('User action', action='login')
                # Both user_id and session_id are automatically included
            ```
        """
        if not self._initialized:
            raise RuntimeError("SyntropyLog must be initialized before using context")
        
        if not self._context:
            raise RuntimeError("Context manager not available")
        
        async with self._context.scope(**context_data):
            yield
    
    # Convenience methods for logging
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message with current context."""
        if self._logger:
            self._logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message with current context."""
        if self._logger:
            self._logger.info(message, **kwargs)
    
    def warn(self, message: str, **kwargs: Any) -> None:
        """Log a warning message with current context."""
        if self._logger:
            self._logger.warn(message, **kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message with current context."""
        if self._logger:
            self._logger.error(message, **kwargs)
    
    # Configuration hot-reload methods
    def set_log_level(self, level: str) -> None:
        """
        Change the log level at runtime.
        
        Args:
            level: New log level ('debug', 'info', 'warn', 'error')
        """
        if self._logger:
            self._logger.set_level(level)
    
    def add_context(self, key: str, value: Any) -> None:
        """
        Add a key-value pair to the current context.
        
        Args:
            key: Context key
            value: Context value
        """
        if self._context:
            self._context.add(key, value)
    
    def remove_context(self, key: str) -> None:
        """
        Remove a key from the current context.
        
        Args:
            key: Context key to remove
        """
        if self._context:
            self._context.remove(key)
    
    def update_context(self, key: str, value: Any) -> None:
        """
        Update a context key with a new value.
        
        Args:
            key: Context key to update
            value: New value
        """
        if self._context:
            self._context.update(key, value)
    
    # Property accessors
    @property
    def logger(self) -> Optional[Logger]:
        """Get the main logger instance."""
        return self._logger
    
    @property
    def context(self) -> Optional[ContextManager]:
        """Get the context manager instance."""
        return self._context
    
    @property
    def http(self) -> Optional[HttpManager]:
        """Get the HTTP manager instance."""
        return self._http
    
    @property
    def redis(self) -> Optional[BeaconRedis]:
        """Get the Redis client instance."""
        return self._redis
    
    @property
    def brokers(self) -> Optional[BrokerManager]:
        """Get the broker manager instance."""
        return self._brokers
    
    @property
    def serialization(self) -> Optional[SerializationManager]:
        """Get the serialization manager instance."""
        return self._serialization
    
    @property
    def is_initialized(self) -> bool:
        """Check if the framework is initialized."""
        return self._initialized 