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
import time

from .config import Config, ConfigManager
from .context import ContextManager
from .logger import UltraFastLogger, LoggerFactory, LogLevel, LogEntry, ConsoleTransport
from .http import HttpManager
from .redis import BeaconRedis
from .brokers import BrokerManager
from .serialization import SerializationManager
from .masking import DataMaskingEngine


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
        _masking (DataMaskingEngine): Data masking engine for sensitive data
        _shutdown_handlers (List): List of shutdown handlers to execute
    """
    
    def __init__(self):
        """Initialize the SyntropyLog framework instance."""
        self._initialized: bool = False
        self._config: Optional[ConfigManager] = None
        self._context: Optional[ContextManager] = None
        self._logger: Optional[UltraFastLogger] = None
        self._http: Optional[HttpManager] = None
        self._redis: Optional[BeaconRedis] = None
        self._brokers: Optional[BrokerManager] = None
        self._serialization: Optional[SerializationManager] = None
        self._masking: Optional[DataMaskingEngine] = None
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
            context_config = self._config.get_context_config()
            await self._context.init({
                'enabled': context_config.enabled,
                'correlation_id_header': context_config.correlation_id_header,
                'enable_auto_correlation': context_config.enable_auto_correlation,
                'context_storage': context_config.context_storage,
                'max_context_depth': context_config.max_context_depth
            })
            
            # 3. Initialize logger system
            logger_config = self._config.get_logger_config()
            logger_factory = LoggerFactory()
            self._logger = await logger_factory.create_logger(
                LogLevel(logger_config.level)
            )
            
            # 4. Initialize HTTP instrumentation
            http_config = self._config.get_http_config()
            self._http = HttpManager()
            await self._http.init({
                'enabled': http_config.enabled,
                'correlation_headers': http_config.correlation_headers,
                'log_requests': http_config.log_requests,
                'log_responses': http_config.log_responses,
                'mask_sensitive_data': http_config.mask_sensitive_data
            })
            
            # 5. Initialize Redis integration
            redis_config = self._config.get_redis_config()
            if redis_config and redis_config.enabled:
                self._redis = BeaconRedis()
                await self._redis.init({
                    'url': redis_config.url,
                    'host': redis_config.host,
                    'port': redis_config.port,
                    'db': redis_config.db,
                    'password': redis_config.password,
                    'context_ttl': redis_config.context_ttl,
                    'enable_clustering': redis_config.enable_clustering
                })
            
            # 6. Initialize message brokers
            broker_config = self._config.get_broker_config()
            if broker_config and broker_config.enabled:
                self._brokers = BrokerManager()
                await self._brokers.init({
                    'type': broker_config.type,
                    'connection': broker_config.connection,
                    'topics': broker_config.topics,
                    'enable_correlation': broker_config.enable_correlation
                })
            
            # 7. Initialize serialization pipeline
            serialization_config = self._config.get_serialization_config()
            self._serialization = SerializationManager()
            await self._serialization.init({
                'enabled': serialization_config.enabled,
                'serializers': serialization_config.serializers,
                'pipeline_steps': serialization_config.pipeline_steps,
                'timeout': serialization_config.timeout,
                'enable_caching': serialization_config.enable_caching
            })
            
            # 8. Initialize data masking engine
            masking_config = self._config.get_masking_config()
            self._masking = DataMaskingEngine()
            await self._masking.init({
                'enabled': masking_config.enabled,
                'rules': masking_config.rules,
                'max_object_depth': masking_config.max_object_depth,
                'max_field_length': masking_config.max_field_length
            })
            
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
        
        Each component has its own timeout to prevent hanging.
        
        Returns:
            Dictionary with shutdown status information
        """
        if not self._initialized:
            return {"success": True, "message": "Framework not initialized"}
        
        shutdown_result = {
            "success": True, 
            "errors": [],
            "components_shutdown": [],
            "start_time": time.time()
        }
        
        try:
            self._internal_logger.info("Shutting down SyntropyLog framework...")
            
            # Execute registered shutdown handlers with timeout
            for i, handler in enumerate(self._shutdown_handlers):
                try:
                    await asyncio.wait_for(handler(), timeout=5.0)  # 5s timeout per handler
                    shutdown_result["components_shutdown"].append(f"shutdown_handler_{i}")
                except asyncio.TimeoutError:
                    error_msg = f"Shutdown handler {i} timeout after 5s"
                    shutdown_result["errors"].append(error_msg)
                    self._internal_logger.error(error_msg)
                except Exception as error:
                    error_msg = f"Shutdown handler {i} error: {error}"
                    shutdown_result["errors"].append(error_msg)
                    self._internal_logger.error(error_msg)
            
            # Shutdown components in reverse order with individual timeouts
            components_to_shutdown = [
                ("serialization", self._serialization, 10.0),
                ("brokers", self._brokers, 15.0),
                ("redis", self._redis, 10.0),
                ("http", self._http, 10.0),
                ("logger", self._logger, 5.0),
                ("context", self._context, 5.0),
                ("masking", self._masking, 5.0), # Added masking shutdown
            ]
            
            for component_name, component, timeout in components_to_shutdown:
                if component:
                    try:
                        await asyncio.wait_for(component.shutdown(), timeout=timeout)
                        shutdown_result["components_shutdown"].append(component_name)
                        self._internal_logger.info(f"✅ {component_name} shutdown completed")
                    except asyncio.TimeoutError:
                        error_msg = f"{component_name} shutdown timeout after {timeout}s"
                        shutdown_result["errors"].append(error_msg)
                        self._internal_logger.error(error_msg)
                    except Exception as error:
                        error_msg = f"{component_name} shutdown error: {error}"
                        shutdown_result["errors"].append(error_msg)
                        self._internal_logger.error(error_msg)
            
            await self._cleanup()
            
            shutdown_result["end_time"] = time.time()
            shutdown_result["duration"] = shutdown_result["end_time"] - shutdown_result["start_time"]
            
            if shutdown_result["errors"]:
                shutdown_result["success"] = False
                self._internal_logger.warning(f"Shutdown completed with {len(shutdown_result['errors'])} errors")
            else:
                self._internal_logger.info("✅ SyntropyLog framework shutdown completed successfully")
            
        except Exception as error:
            shutdown_result["success"] = False
            shutdown_result["errors"].append(f"General shutdown error: {error}")
            self._internal_logger.error(f"❌ Shutdown failed: {error}")
        
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
        self._masking = None # Added masking cleanup
        self._shutdown_handlers.clear()
    
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
    
    def add_context_with_matrix(self, key: str, value: Any, include_in_logs: bool = True) -> None:
        """
        Add context with matrix control.
        
        Args:
            key: Context key to add
            value: Value to associate with the key
            include_in_logs: Whether this field should be included in logs
        """
        if self._context:
            self._context.add_with_matrix(key, value, include_in_logs)
    
    def configure_logger_matrix(self, 
                               include_fields: Optional[List[str]] = None,
                               exclude_fields: Optional[List[str]] = None,
                               level_matrices: Optional[Dict[str, List[str]]] = None,
                               max_object_depth: Optional[int] = None,
                               max_field_length: Optional[int] = None) -> None:
        """
        Configure the logger matrix for context filtering.
        
        Args:
            include_fields: Fields to always include in logs
            exclude_fields: Fields to always exclude from logs
            level_matrices: Per-level field inclusion rules
            max_object_depth: Maximum depth for nested objects
            max_field_length: Maximum length for field values
        """
        if self._context:
            self._context.configure_logger_matrix(
                include_fields=include_fields,
                exclude_fields=exclude_fields,
                level_matrices=level_matrices,
                max_object_depth=max_object_depth,
                max_field_length=max_field_length
            )
    
    def get_filtered_context(self, level: str = "info") -> Dict[str, Any]:
        """
        Get filtered context data for logging.
        
        Args:
            level: Log level for filtering
            
        Returns:
            Filtered context dictionary
        """
        if self._context:
            return self._context.get_filtered_context(level)
        return {}
    
    def mask_data(self, data: Any) -> Any:
        """
        Mask sensitive data in any structure.
        
        Args:
            data: Data to mask (dict, list, or primitive)
            
        Returns:
            Masked data with same structure
        """
        if self._masking:
            return self._masking.mask_data(data)
        return data
    
    def add_masking_rule(self, 
                        pattern: str, 
                        strategy: str,
                        preserve_length: bool = True,
                        mask_char: str = "*",
                        custom_mask: Optional[callable] = None) -> None:
        """
        Add a custom masking rule.
        
        Args:
            pattern: Regex pattern to match field names
            strategy: Masking strategy ('credit_card', 'ssn', 'email', etc.)
            preserve_length: Whether to preserve original length
            mask_char: Character to use for masking
            custom_mask: Custom masking function
        """
        if self._masking:
            from .masking import MaskingStrategy
            try:
                strategy_enum = MaskingStrategy(strategy)
                self._masking.add_rule(
                    pattern=pattern,
                    strategy=strategy_enum,
                    preserve_length=preserve_length,
                    mask_char=mask_char,
                    custom_mask=custom_mask
                )
            except ValueError:
                # Invalid strategy - use CUSTOM
                self._masking.add_rule(
                    pattern=pattern,
                    strategy=MaskingStrategy.CUSTOM,
                    preserve_length=preserve_length,
                    mask_char=mask_char,
                    custom_mask=custom_mask
                )
    
    def get_masking_stats(self) -> Dict[str, Any]:
        """
        Get masking engine statistics.
        
        Returns:
            Dictionary with masking statistics
        """
        if self._masking:
            return self._masking.get_masking_stats()
        return {"initialized": False, "total_rules": 0}
    
    # Property accessors
    @property
    def logger(self) -> Optional[UltraFastLogger]:
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
    def masking(self) -> Optional[DataMaskingEngine]:
        """Get the data masking engine instance."""
        return self._masking
    
    @property
    def is_initialized(self) -> bool:
        """Check if the framework is initialized."""
        return self._initialized
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status information about the framework.
        
        Returns:
            Dictionary with status information for all components
        """
        status = {
            "initialized": self._initialized,
            "components": {}
        }
        
        if self._initialized:
            # Check each component status
            status["components"]["config"] = {
                "available": self._config is not None,
                "type": type(self._config).__name__ if self._config else None
            }
            
            status["components"]["context"] = {
                "available": self._context is not None,
                "type": type(self._context).__name__ if self._context else None
            }
            
            status["components"]["logger"] = {
                "available": self._logger is not None,
                "type": type(self._logger).__name__ if self._logger else None
            }
            
            status["components"]["http"] = {
                "available": self._http is not None,
                "type": type(self._http).__name__ if self._http else None
            }
            
            status["components"]["redis"] = {
                "available": self._redis is not None,
                "type": type(self._redis).__name__ if self._redis else None
            }
            
            status["components"]["brokers"] = {
                "available": self._brokers is not None,
                "type": type(self._brokers).__name__ if self._brokers else None
            }
            
            status["components"]["serialization"] = {
                "available": self._serialization is not None,
                "type": type(self._serialization).__name__ if self._serialization else None
            }

            status["components"]["masking"] = {
                "available": self._masking is not None,
                "type": type(self._masking).__name__ if self._masking else None
            }
            
            status["shutdown_handlers"] = len(self._shutdown_handlers)
        
        return status
    
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