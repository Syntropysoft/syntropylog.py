"""
Logger System for SyntropyLog

This module provides the core logging functionality with structured logging,
automatic context propagation, and multiple transport support.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from .context import ContextManager


class LogLevel(Enum):
    """Log levels enumeration."""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class Transport:
    """
    Base transport class for log output.
    
    This is the base class for all log transports. Transports are responsible
    for delivering log entries to their final destination (console, file, etc.).
    
    The transport follows the "Silent Observer" philosophy - transport failures
    are reported but don't interrupt the logging pipeline.
    """
    
    def __init__(self, name: str):
        """
        Initialize the transport.
        
        Args:
            name: Transport name for identification
        """
        self.name = name
        self.enabled = True
    
    async def send(self, entry: Dict[str, Any]) -> None:
        """
        Send a log entry to the transport destination.
        
        This method must be implemented by subclasses to handle the actual
        delivery of log entries.
        
        Args:
            entry: Log entry dictionary to send
        """
        raise NotImplementedError("Subclasses must implement send()")
    
    async def shutdown(self) -> None:
        """
        Shutdown the transport and cleanup resources.
        
        This method should be implemented by subclasses to perform any
        necessary cleanup when the transport is being shut down.
        """
        pass


class ConsoleTransport(Transport):
    """
    Console transport for log output.
    
    This transport outputs log entries to the console (stdout/stderr)
    with formatted output.
    """
    
    def __init__(self, name: str = "console", format_string: str = None):
        """
        Initialize the console transport.
        
        Args:
            name: Transport name
            format_string: Custom format string for log output
        """
        super().__init__(name)
        self.format_string = format_string or "{timestamp} [{level}] {message} {context}"
    
    async def send(self, entry: Dict[str, Any]) -> None:
        """
        Send log entry to console.
        
        Args:
            entry: Log entry to output
        """
        try:
            formatted = self.format_string.format(**entry)
            print(formatted)
        except Exception as error:
            # Silent observer - don't interrupt logging pipeline
            print(f"Console transport error: {error}")


class Logger:
    """
    Main logger class for SyntropyLog.
    
    This class provides structured logging with automatic context propagation,
    multiple transport support, and level filtering.
    
    The logger follows the "Silent Observer" philosophy - logging failures
    are reported but don't interrupt the main application flow.
    
    Attributes:
        _context: Context manager for correlation IDs
        _transports: List of configured transports
        _level: Current log level
        _formatters: Log formatters
        _enabled: Whether logging is enabled
    """
    
    def __init__(self, context: ContextManager, transports: List[Transport] = None):
        """
        Initialize the logger.
        
        Args:
            context: Context manager for correlation
            transports: List of transports to use
        """
        self._context = context
        self._transports = transports or []
        self._level = LogLevel.INFO
        self._formatters = {}
        self._enabled = True
        
        # Initialize internal logger for framework operations
        self._internal_logger = logging.getLogger('syntropylog.logger')
        self._internal_logger.setLevel(logging.WARNING)
    
    def set_level(self, level: str) -> None:
        """
        Set the log level.
        
        Args:
            level: Log level ('debug', 'info', 'warn', 'error')
        """
        try:
            self._level = LogLevel(level.lower())
        except ValueError:
            self._internal_logger.warning(f"Invalid log level: {level}")
    
    def add_transport(self, transport: Transport) -> None:
        """
        Add a transport to the logger.
        
        Args:
            transport: Transport instance to add
        """
        self._transports.append(transport)
    
    def remove_transport(self, name: str) -> None:
        """
        Remove a transport by name.
        
        Args:
            name: Name of transport to remove
        """
        self._transports = [t for t in self._transports if t.name != name]
    
    def _should_log(self, level: LogLevel) -> bool:
        """
        Check if a log level should be processed.
        
        Args:
            level: Log level to check
            
        Returns:
            True if the level should be logged
        """
        level_order = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARN: 2,
            LogLevel.ERROR: 3
        }
        return level_order[level] >= level_order[self._level]
    
    def _create_entry(self, level: LogLevel, message: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Create a log entry with context and metadata.
        
        Args:
            level: Log level
            message: Log message
            **kwargs: Additional log data
            
        Returns:
            Complete log entry dictionary
        """
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level.value,
            'message': message,
            'data': kwargs
        }
        
        # Add context data if available
        if self._context:
            correlation_id = self._context.get_correlation_id()
            if correlation_id:
                entry['correlation_id'] = correlation_id
            
            context_data = self._context.get_context_data()
            if context_data:
                entry['context'] = context_data
        
        return entry
    
    async def _send_to_transports(self, entry: Dict[str, Any]) -> None:
        """
        Send log entry to all enabled transports.
        
        Args:
            entry: Log entry to send
        """
        for transport in self._transports:
            if transport.enabled:
                try:
                    await transport.send(entry)
                except Exception as error:
                    # Silent observer - report but don't interrupt
                    self._internal_logger.error(f"Transport {transport.name} failed: {error}")
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """
        Log a debug message.
        
        Args:
            message: Debug message
            **kwargs: Additional debug data
        """
        if self._should_log(LogLevel.DEBUG):
            entry = self._create_entry(LogLevel.DEBUG, message, **kwargs)
            asyncio.create_task(self._send_to_transports(entry))
    
    def info(self, message: str, **kwargs: Any) -> None:
        """
        Log an info message.
        
        Args:
            message: Info message
            **kwargs: Additional info data
        """
        if self._should_log(LogLevel.INFO):
            entry = self._create_entry(LogLevel.INFO, message, **kwargs)
            asyncio.create_task(self._send_to_transports(entry))
    
    def warn(self, message: str, **kwargs: Any) -> None:
        """
        Log a warning message.
        
        Args:
            message: Warning message
            **kwargs: Additional warning data
        """
        if self._should_log(LogLevel.WARN):
            entry = self._create_entry(LogLevel.WARN, message, **kwargs)
            asyncio.create_task(self._send_to_transports(entry))
    
    def error(self, message: str, **kwargs: Any) -> None:
        """
        Log an error message.
        
        Args:
            message: Error message
            **kwargs: Additional error data
        """
        if self._should_log(LogLevel.ERROR):
            entry = self._create_entry(LogLevel.ERROR, message, **kwargs)
            asyncio.create_task(self._send_to_transports(entry))
    
    async def shutdown(self) -> None:
        """
        Shutdown the logger and all transports.
        
        This method ensures that all transports are properly shut down
        and any pending log entries are flushed.
        """
        try:
            # Shutdown all transports
            for transport in self._transports:
                try:
                    await transport.shutdown()
                except Exception as error:
                    self._internal_logger.error(f"Transport {transport.name} shutdown failed: {error}")
            
            self._enabled = False
            
        except Exception as error:
            self._internal_logger.error(f"Logger shutdown failed: {error}")
    
    @property
    def level(self) -> LogLevel:
        """Get current log level."""
        return self._level
    
    @property
    def transports(self) -> List[Transport]:
        """Get list of configured transports."""
        return self._transports.copy()
    
    @property
    def is_enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._enabled


class LoggerFactory:
    """
    Factory for creating logger instances.
    
    This class provides a factory pattern for creating logger instances
    with different configurations and transports.
    """
    
    def __init__(self):
        """Initialize the logger factory."""
        self._default_transports = {
            'console': ConsoleTransport
        }
    
    async def create_logger(self, config: Dict[str, Any], context: ContextManager) -> Logger:
        """
        Create a logger instance with the specified configuration.
        
        Args:
            config: Logger configuration
            context: Context manager for correlation
            
        Returns:
            Configured logger instance
        """
        # Create logger instance
        logger = Logger(context)
        
        # Set log level
        if 'level' in config:
            logger.set_level(config['level'])
        
        # Add transports
        transports = config.get('transports', ['console'])
        for transport_name in transports:
            transport = await self._create_transport(transport_name, config)
            if transport:
                logger.add_transport(transport)
        
        return logger
    
    async def _create_transport(self, name: str, config: Dict[str, Any]) -> Optional[Transport]:
        """
        Create a transport instance by name.
        
        Args:
            name: Transport name
            config: Transport configuration
            
        Returns:
            Transport instance or None if creation fails
        """
        try:
            if name == 'console':
                format_string = config.get('formatters', {}).get('console', None)
                return ConsoleTransport('console', format_string)
            
            # Add more transport types here as they are implemented
            # elif name == 'file':
            #     return FileTransport(...)
            # elif name == 'http':
            #     return HttpTransport(...)
            
            return None
            
        except Exception as error:
            # Silent observer - don't interrupt logger creation
            print(f"Failed to create transport {name}: {error}")
            return None 