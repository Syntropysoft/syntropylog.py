"""
Ultra-Optimized Logger System for SyntropyLog

This module provides the core logging functionality with extreme performance
optimization for log collectors. Designed for maximum throughput with minimal overhead.
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from collections import deque
import threading


class LogLevel(Enum):
    """Log levels enumeration - optimized for speed."""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Ultra-optimized log entry using slots for minimal memory overhead."""
    level: str
    message: str
    timestamp: int
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> str:
        """Direct JSON serialization for maximum speed."""
        return json.dumps({
            'level': self.level,
            'message': self.message,
            'timestamp': self.timestamp,
            'context': self.context
        }, separators=(',', ':'), ensure_ascii=False)


class UltraFastTransport:
    """
    Ultra-optimized transport base class.
    
    Uses slots and minimal overhead for maximum performance.
    """
    
    __slots__ = ('name', 'enabled', '_queue', '_worker_task')
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self._queue: deque = deque(maxlen=10000)  # Prevent memory leaks
        self._worker_task: Optional[asyncio.Task] = None
    
    async def _start_worker(self):
        """Start async worker for non-blocking operations."""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())
    
    async def _worker(self):
        """Background worker for processing log entries."""
        while self.enabled:
            try:
                if self._queue:
                    entry = self._queue.popleft()
                    await self._send_impl(entry)
                else:
                    await asyncio.sleep(0.001)  # 1ms sleep for efficiency
            except Exception:
                # Silent observer - continue processing
                continue
    
    async def _send_impl(self, entry: LogEntry) -> None:
        """Implementation method to be overridden by subclasses."""
        raise NotImplementedError
    
    async def send(self, entry: LogEntry) -> None:
        """
        Send log entry asynchronously - fire and forget.
        
        Args:
            entry: Log entry to send
        """
        if not self.enabled:
            return
            
        # Add to queue for async processing
        self._queue.append(entry)
        await self._start_worker()
    
    async def shutdown(self) -> None:
        """Shutdown transport gracefully."""
        self.enabled = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass


class ConsoleTransport(UltraFastTransport):
    """
    Ultra-fast console transport optimized for log collectors.
    
    Outputs pure JSON for maximum parsing speed.
    """
    
    __slots__ = ('_lock',)
    
    def __init__(self, name: str = "console"):
        super().__init__(name)
        self._lock = threading.Lock()
    
    async def _send_impl(self, entry: LogEntry) -> None:
        """
        Send log entry to console as pure JSON.
        
        Args:
            entry: Log entry to output
        """
        try:
            # Direct JSON output for maximum speed
            json_line = entry.to_json()
            
            # Thread-safe print for concurrent access
            with self._lock:
                print(json_line, flush=True)
                
        except Exception:
            # Silent observer - don't interrupt logging pipeline
            pass


class UltraFastLogger:
    """
    Ultra-optimized logger for maximum performance.
    
    Uses slots, async operations, and minimal overhead for extreme throughput.
    """
    
    __slots__ = ('_level', '_transports', '_context', '_enabled')
    
    def __init__(self, level: LogLevel = LogLevel.INFO):
        self._level = level
        self._transports: List[UltraFastTransport] = []
        self._context: Dict[str, Any] = {}
        self._enabled = True
    
    def set_level(self, level: LogLevel) -> None:
        """Set log level."""
        self._level = level
    
    def add_transport(self, transport: UltraFastTransport) -> None:
        """Add transport."""
        self._transports.append(transport)
    
    def add_context(self, key: str, value: Any) -> None:
        """Add context data."""
        self._context[key] = value
    
    def _should_log(self, level: LogLevel) -> bool:
        """Check if level should be logged."""
        if not self._enabled:
            return False
            
        level_order = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARN: 2,
            LogLevel.ERROR: 3
        }
        
        return level_order[level] >= level_order[self._level]
    
    def _create_entry(self, level: LogLevel, message: str, **kwargs: Any) -> LogEntry:
        """Create log entry with minimal overhead and context filtering."""
        # Get filtered context from context manager if available
        filtered_context = {}
        
        # Try to get filtered context from global context manager
        try:
            from . import syntropy_log
            if syntropy_log.context and syntropy_log.context.is_initialized:
                filtered_context = syntropy_log.context.get_filtered_context(level.value)
        except Exception:
            # Fallback to local context if global context is not available
            filtered_context = self._context.copy()
        
        # Merge filtered context with additional kwargs
        context = {**filtered_context, **kwargs}
        
        # Apply masking to sensitive data if masking engine is available
        try:
            from . import syntropy_log
            if syntropy_log.masking and syntropy_log.masking.is_initialized:
                context = syntropy_log.masking.mask_data(context)
        except Exception:
            # Silent observer - continue without masking if it fails
            pass
        
        # Use time.time() for maximum speed (no datetime overhead)
        timestamp = int(time.time() * 1000)  # milliseconds
        
        return LogEntry(
            level=level.value,
            message=message,
            timestamp=timestamp,
            context=context
        )
    
    async def _send_to_transports(self, entry: LogEntry) -> None:
        """Send entry to all transports asynchronously."""
        if not self._transports:
            return
            
        # Fire and forget - don't await
        for transport in self._transports:
            asyncio.create_task(transport.send(entry))
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        if self._should_log(LogLevel.DEBUG):
            entry = self._create_entry(LogLevel.DEBUG, message, **kwargs)
            asyncio.create_task(self._send_to_transports(entry))
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        if self._should_log(LogLevel.INFO):
            entry = self._create_entry(LogLevel.INFO, message, **kwargs)
            asyncio.create_task(self._send_to_transports(entry))
    
    def warn(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        if self._should_log(LogLevel.WARN):
            entry = self._create_entry(LogLevel.WARN, message, **kwargs)
            asyncio.create_task(self._send_to_transports(entry))
    
    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        if self._should_log(LogLevel.ERROR):
            entry = self._create_entry(LogLevel.ERROR, message, **kwargs)
            asyncio.create_task(self._send_to_transports(entry))
    
    async def shutdown(self) -> None:
        """Shutdown logger gracefully."""
        self._enabled = False
        
        # Shutdown all transports
        for transport in self._transports:
            await transport.shutdown()
    
    @property
    def level(self) -> LogLevel:
        """Get current log level."""
        return self._level
    
    @property
    def transports(self) -> List[UltraFastTransport]:
        """Get transports list."""
        return self._transports.copy()
    
    @property
    def is_enabled(self) -> bool:
        """Check if logger is enabled."""
        return self._enabled


class LoggerFactory:
    """
    Factory for creating ultra-optimized loggers.
    """
    
    @staticmethod
    async def create_logger(level: LogLevel = LogLevel.INFO) -> UltraFastLogger:
        """
        Create ultra-fast logger with console transport.
        
        Args:
            level: Initial log level
            
        Returns:
            Configured logger instance
        """
        logger = UltraFastLogger(level)
        
        # Add default console transport
        console_transport = ConsoleTransport()
        logger.add_transport(console_transport)
        
        return logger 