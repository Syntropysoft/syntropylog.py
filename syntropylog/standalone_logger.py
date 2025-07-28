"""
Standalone Ultra-Fast Logger for SyntropyLog

This is a completely independent logger with zero external dependencies.
It does ONE thing: log messages as fast as possible.
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from collections import deque
import threading
from datetime import datetime


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


class StandaloneTransport:
    """
    Standalone transport - no external dependencies.
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


class ConsoleTransport(StandaloneTransport):
    """
    Ultra-fast console transport - outputs pure JSON for log collectors.
    """
    
    __slots__ = ('_lock',)
    
    def __init__(self, name: str = "json"):
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


class PythonicConsoleTransport(StandaloneTransport):
    """
    Pythonic console transport - compatible with Python's logging standard.
    
    This transport follows the familiar Python logging format that developers expect.
    """
    
    __slots__ = ('_lock', '_level_colors', '_format_string')
    
    def __init__(self, name: str = "pythonic", format_string: str = None):
        super().__init__(name)
        self._lock = threading.Lock()
        self._format_string = format_string or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        self._level_colors = {
            'error': '\033[91m',  # Red
            'warn': '\033[93m',   # Yellow
            'info': '\033[94m',   # Blue
            'debug': '\033[92m',  # Green
            'reset': '\033[0m',   # Reset
            'gray': '\033[90m',   # Gray
        }
    
    def _colorize(self, text: str, color: str) -> str:
        """Add color to text."""
        return f"{self._level_colors.get(color, '')}{text}{self._level_colors['reset']}"
    
    def _format_timestamp(self, timestamp: int) -> str:
        """Format timestamp like Python logging."""
        dt = datetime.fromtimestamp(timestamp / 1000)
        return dt.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]  # Include milliseconds
    
    def _format_log_string(self, entry: LogEntry) -> str:
        """Format log entry like Python logging standard."""
        # Extract logger name from context or use default
        logger_name = entry.context.get('logger_name', 'root')
        
        # Format timestamp
        timestamp = self._format_timestamp(entry.timestamp)
        
        # Format level (uppercase like Python logging)
        level = entry.level.upper()
        
        # Format message
        message = entry.message
        
        # Build the main log line
        log_line = f"{timestamp} - {logger_name} - {level} - {message}"
        
        # Add extra context if present (excluding logger_name)
        extra_context = {k: v for k, v in entry.context.items() if k != 'logger_name'}
        if extra_context:
            context_str = json.dumps(extra_context, separators=(',', ':'))
            log_line += f" | {context_str}"
        
        return log_line
    
    async def _send_impl(self, entry: LogEntry) -> None:
        """
        Send log entry in Pythonic format.
        
        Args:
            entry: Log entry to output
        """
        try:
            # Format the log string
            log_line = self._format_log_string(entry)
            
            # Add color based on level
            level_color = entry.level
            colored_line = self._colorize(log_line, level_color)
            
            # Thread-safe print
            with self._lock:
                print(colored_line, flush=True)
                
        except Exception:
            # Silent observer - don't interrupt logging pipeline
            pass


class CompactConsoleTransport(StandaloneTransport):
    """
    Compact console transport - single-line format for developers.
    """
    
    __slots__ = ('_lock', '_level_colors')
    
    def __init__(self, name: str = "compact"):
        super().__init__(name)
        self._lock = threading.Lock()
        self._level_colors = {
            'error': '\033[91m',  # Red
            'warn': '\033[93m',   # Yellow
            'info': '\033[96m',   # Cyan
            'debug': '\033[92m',  # Green
            'reset': '\033[0m',   # Reset
            'gray': '\033[90m',   # Gray
            'blue': '\033[94m',   # Blue
        }
    
    def _colorize(self, text: str, color: str) -> str:
        """Add color to text."""
        return f"{self._level_colors.get(color, '')}{text}{self._level_colors['reset']}"
    
    def _format_timestamp(self, timestamp: int) -> str:
        """Format timestamp for display."""
        dt = datetime.fromtimestamp(timestamp / 1000)
        return dt.strftime('%H:%M:%S')
    
    async def _send_impl(self, entry: LogEntry) -> None:
        """
        Send log entry in compact format.
        
        Args:
            entry: Log entry to output
        """
        try:
            # Format timestamp
            time_str = self._colorize(self._format_timestamp(entry.timestamp), 'gray')
            
            # Format level with color
            level_color = entry.level
            level_str = self._colorize(f"[{entry.level.upper()}]", level_color)
            
            # Format message
            message_str = entry.message or ''
            
            # Build main line
            log_line = f"{time_str} {level_str}: {message_str}"
            
            # Add context if present
            if entry.context:
                context_items = []
                for key, value in entry.context.items():
                    if isinstance(value, (dict, list)):
                        value_str = json.dumps(value, separators=(',', ':'))
                    else:
                        value_str = str(value)
                    context_items.append(f"{self._colorize(key, 'gray')}={self._colorize(value_str, 'gray')}")
                
                if context_items:
                    log_line += f"\n  {self._colorize('└─', 'gray')} {' '.join(context_items)}"
            
            # Thread-safe print
            with self._lock:
                print(log_line, flush=True)
                
        except Exception:
            # Silent observer - don't interrupt logging pipeline
            pass


class PrettyConsoleTransport(StandaloneTransport):
    """
    Pretty console transport - colorful format for development.
    """
    
    __slots__ = ('_lock', '_level_colors')
    
    def __init__(self, name: str = "pretty"):
        super().__init__(name)
        self._lock = threading.Lock()
        self._level_colors = {
            'error': '\033[91m',  # Red
            'warn': '\033[93m',   # Yellow
            'info': '\033[94m',   # Blue
            'debug': '\033[92m',  # Green
            'reset': '\033[0m',   # Reset
            'gray': '\033[90m',   # Gray
            'cyan': '\033[96m',   # Cyan
        }
    
    def _colorize(self, text: str, color: str) -> str:
        """Add color to text."""
        return f"{self._level_colors.get(color, '')}{text}{self._level_colors['reset']}"
    
    def _format_timestamp(self, timestamp: int) -> str:
        """Format timestamp for display."""
        dt = datetime.fromtimestamp(timestamp / 1000)
        return dt.strftime('%H:%M:%S')
    
    async def _send_impl(self, entry: LogEntry) -> None:
        """
        Send log entry in pretty format.
        
        Args:
            entry: Log entry to output
        """
        try:
            # Format timestamp
            time_str = self._colorize(self._format_timestamp(entry.timestamp), 'gray')
            
            # Format level with color
            level_color = entry.level
            level_str = self._colorize(f"[{entry.level.upper()}]", level_color)
            
            # Format message
            message_str = entry.message or ''
            
            # Build main line
            log_line = f"{time_str} {level_str}: {message_str}"
            
            # Add context if present
            if entry.context:
                context_str = self._colorize(json.dumps(entry.context, indent=2), 'gray')
                log_line += f"\n{context_str}"
            
            # Thread-safe print
            with self._lock:
                print(log_line, flush=True)
                
        except Exception:
            # Silent observer - don't interrupt logging pipeline
            pass


class ClassicConsoleTransport(StandaloneTransport):
    """
    Classic console transport - traditional format like Log4j.
    """
    
    __slots__ = ('_lock', '_level_colors')
    
    def __init__(self, name: str = "classic"):
        super().__init__(name)
        self._lock = threading.Lock()
        self._level_colors = {
            'error': '\033[91m',  # Red
            'warn': '\033[93m',   # Yellow
            'info': '\033[92m',   # Green
            'debug': '\033[94m',  # Blue
            'reset': '\033[0m',   # Reset
            'gray': '\033[90m',   # Gray
            'magenta': '\033[95m', # Magenta
        }
    
    def _colorize(self, text: str, color: str) -> str:
        """Add color to text."""
        return f"{self._level_colors.get(color, '')}{text}{self._level_colors['reset']}"
    
    def _format_timestamp(self, timestamp: int) -> str:
        """Format timestamp in classic format."""
        dt = datetime.fromtimestamp(timestamp / 1000)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    async def _send_impl(self, entry: LogEntry) -> None:
        """
        Send log entry in classic format.
        
        Args:
            entry: Log entry to output
        """
        try:
            # Format timestamp
            time_str = self._format_timestamp(entry.timestamp)
            
            # Format level with color and padding
            level_color = entry.level
            level_str = self._colorize(entry.level.upper().ljust(5), level_color)
            
            # Format service (using default if not present)
            service = entry.context.get('service', 'app')
            service_str = self._colorize(f"[{service}]", 'magenta')
            
            # Build metadata string
            meta_items = []
            for key, value in entry.context.items():
                if key != 'service':
                    if isinstance(value, (dict, list)):
                        value_str = json.dumps(value, separators=(',', ':'))
                    else:
                        value_str = str(value)
                    meta_items.append(f"{key}={value_str}")
            
            meta_str = ""
            if meta_items:
                meta_str = self._colorize(f" [{' '.join(meta_items)}]", 'gray')
            
            # Build final line
            log_line = f"{time_str} {level_str} {service_str}{meta_str}"
            
            # Thread-safe print
            with self._lock:
                print(log_line, flush=True)
                
        except Exception:
            # Silent observer - don't interrupt logging pipeline
            pass


class StandaloneLogger:
    """
    Standalone ultra-optimized logger - zero external dependencies.
    
    This logger does ONE thing: log messages as fast as possible.
    It doesn't know about contexts, configs, or any other framework components.
    """
    
    __slots__ = ('_level', '_transports', '_context', '_enabled')
    
    def __init__(self, level: LogLevel = LogLevel.INFO):
        self._level = level
        self._transports: List[StandaloneTransport] = []
        self._context: Dict[str, Any] = {}
        self._enabled = True
    
    def set_level(self, level: LogLevel) -> None:
        """Set log level."""
        self._level = level
    
    def add_transport(self, transport: StandaloneTransport) -> None:
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
        """Create log entry with minimal overhead."""
        # Merge context with additional kwargs
        context = {**self._context, **kwargs}
        
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
    def transports(self) -> List[StandaloneTransport]:
        """Get transports list."""
        return self._transports.copy()
    
    @property
    def is_enabled(self) -> bool:
        """Check if logger is enabled."""
        return self._enabled


class StandaloneLoggerFactory:
    """
    Factory for creating standalone ultra-optimized loggers.
    """
    
    @staticmethod
    async def create_logger(level: LogLevel = LogLevel.INFO) -> StandaloneLogger:
        """
        Create standalone ultra-fast logger with pythonic console transport.
        
        Args:
            level: Initial log level
            
        Returns:
            Configured logger instance
        """
        logger = StandaloneLogger(level)
        
        # Add default pythonic console transport (most familiar to Python developers)
        pythonic_transport = PythonicConsoleTransport()
        logger.add_transport(pythonic_transport)
        
        return logger 