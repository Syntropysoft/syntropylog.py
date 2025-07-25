"""
Context Management for SyntropyLog

This module provides context management functionality for automatic correlation
ID propagation and context data sharing across async operations. It implements
async context managers and thread-safe context storage.
"""

import asyncio
import uuid
import threading
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ContextData:
    """
    Container for context data with metadata.
    
    This class holds context information along with metadata about when
    it was created and modified.
    
    Attributes:
        data: The actual context data dictionary
        correlation_id: Unique correlation ID for this context
        created_at: Timestamp when context was created
        modified_at: Timestamp when context was last modified
        parent_id: Correlation ID of parent context (if any)
    """
    data: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    modified_at: datetime = field(default_factory=datetime.utcnow)
    parent_id: Optional[str] = None
    
    def update(self, key: str, value: Any) -> None:
        """
        Update a context key and mark as modified.
        
        Args:
            key: Context key to update
            value: New value for the key
        """
        self.data[key] = value
        self.modified_at = datetime.utcnow()
    
    def remove(self, key: str) -> None:
        """
        Remove a context key and mark as modified.
        
        Args:
            key: Context key to remove
        """
        if key in self.data:
            del self.data[key]
            self.modified_at = datetime.utcnow()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a context value with optional default.
        
        Args:
            key: Context key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            Context value or default
        """
        return self.data.get(key, default)
    
    def copy(self) -> 'ContextData':
        """
        Create a shallow copy of this context data.
        
        Returns:
            New ContextData instance with copied data
        """
        new_context = ContextData(
            data=self.data.copy(),
            correlation_id=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            parent_id=self.correlation_id
        )
        return new_context


class ContextManager:
    """
    Manages context propagation across async operations.
    
    This class provides thread-safe context management with automatic
    correlation ID generation and context inheritance. It supports
    nested contexts and automatic cleanup.
    
    The context manager follows the "Silent Observer" philosophy -
    context operations never throw exceptions that could interrupt
    the main application flow.
    
    Attributes:
        _contexts: Thread-local storage for context data
        _lock: Thread lock for thread safety
        _config: Configuration for context management
    """
    
    def __init__(self):
        """Initialize the context manager."""
        self._contexts = threading.local()
        self._lock = threading.Lock()
        self._config: Optional[Dict[str, Any]] = None
        self._initialized = False
        
        # Initialize thread-local storage
        if not hasattr(self._contexts, 'stack'):
            self._contexts.stack = []
    
    async def init(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the context manager with configuration.
        
        Args:
            config: Configuration dictionary for context management
        """
        self._config = config or {}
        self._initialized = True
    
    def _get_current_context(self) -> Optional[ContextData]:
        """
        Get the current context for the current thread.
        
        Returns:
            Current context data or None if no context exists
        """
        if not hasattr(self._contexts, 'stack') or not self._contexts.stack:
            return None
        return self._contexts.stack[-1]
    
    def _push_context(self, context: ContextData) -> None:
        """
        Push a new context onto the stack.
        
        Args:
            context: Context data to push
        """
        if not hasattr(self._contexts, 'stack'):
            self._contexts.stack = []
        self._contexts.stack.append(context)
    
    def _pop_context(self) -> Optional[ContextData]:
        """
        Pop the current context from the stack.
        
        Returns:
            Popped context data or None if stack is empty
        """
        if not hasattr(self._contexts, 'stack') or not self._contexts.stack:
            return None
        return self._contexts.stack.pop()
    
    def get_correlation_id(self) -> Optional[str]:
        """
        Get the current correlation ID.
        
        Returns:
            Current correlation ID or None if no context exists
        """
        current = self._get_current_context()
        return current.correlation_id if current else None
    
    def get_context_data(self) -> Dict[str, Any]:
        """
        Get all current context data.
        
        Returns:
            Dictionary containing all current context data
        """
        current = self._get_current_context()
        return current.data.copy() if current else {}
    
    def add(self, key: str, value: Any) -> None:
        """
        Add a key-value pair to the current context.
        
        This method follows the "Silent Observer" philosophy - it never
        throws exceptions that could interrupt the application flow.
        
        Args:
            key: Context key to add
            value: Value to associate with the key
        """
        try:
            with self._lock:
                current = self._get_current_context()
                if current:
                    current.update(key, value)
                else:
                    # Create new context if none exists
                    new_context = ContextData()
                    new_context.update(key, value)
                    self._push_context(new_context)
        except Exception:
            # Silent observer - don't interrupt application flow
            pass
    
    def remove(self, key: str) -> None:
        """
        Remove a key from the current context.
        
        This method follows the "Silent Observer" philosophy - it never
        throws exceptions that could interrupt the application flow.
        
        Args:
            key: Context key to remove
        """
        try:
            with self._lock:
                current = self._get_current_context()
                if current:
                    current.remove(key)
        except Exception:
            # Silent observer - don't interrupt application flow
            pass
    
    def update(self, key: str, value: Any) -> None:
        """
        Update a key in the current context.
        
        This method follows the "Silent Observer" philosophy - it never
        throws exceptions that could interrupt the application flow.
        
        Args:
            key: Context key to update
            value: New value for the key
        """
        try:
            with self._lock:
                current = self._get_current_context()
                if current:
                    current.update(key, value)
                else:
                    # Create new context if none exists
                    new_context = ContextData()
                    new_context.update(key, value)
                    self._push_context(new_context)
        except Exception:
            # Silent observer - don't interrupt application flow
            pass
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the current context.
        
        Args:
            key: Context key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            Context value or default
        """
        try:
            current = self._get_current_context()
            return current.get(key, default) if current else default
        except Exception:
            return default
    
    @asynccontextmanager
    async def scope(self, **context_data: Any):
        """
        Async context manager for context scope.
        
        This method provides an async context manager that creates a new
        context scope with the provided data. The context is automatically
        cleaned up when the context manager exits.
        
        Args:
            **context_data: Key-value pairs to add to the context
            
        Example:
            ```python
            async with context_manager.scope(user_id='123', session_id='abc'):
                # All operations here have access to user_id and session_id
                logger.info('User action', action='login')
            ```
        """
        # Create new context with current context as parent
        current = self._get_current_context()
        new_context = ContextData()
        
        # Inherit from parent context
        if current:
            new_context.data = current.data.copy()
            new_context.parent_id = current.correlation_id
        
        # Add new context data
        for key, value in context_data.items():
            new_context.update(key, value)
        
        # Push new context onto stack
        with self._lock:
            self._push_context(new_context)
        
        try:
            yield new_context
        finally:
            # Pop context from stack
            with self._lock:
                self._pop_context()
    
    def create_child_context(self, **context_data: Any) -> ContextData:
        """
        Create a child context with additional data.
        
        This method creates a new context that inherits from the current
        context and adds the provided data.
        
        Args:
            **context_data: Key-value pairs to add to the child context
            
        Returns:
            New ContextData instance
        """
        current = self._get_current_context()
        child_context = ContextData()
        
        # Inherit from parent context
        if current:
            child_context.data = current.data.copy()
            child_context.parent_id = current.correlation_id
        
        # Add new context data
        for key, value in context_data.items():
            child_context.update(key, value)
        
        return child_context
    
    def get_context_chain(self) -> List[ContextData]:
        """
        Get the full context chain from current to root.
        
        Returns:
            List of context data objects from current to root
        """
        chain = []
        current = self._get_current_context()
        
        while current:
            chain.append(current)
            if current.parent_id:
                # In a real implementation, you might want to store
                # parent contexts in a registry for lookup
                break
            current = None
        
        return chain
    
    async def shutdown(self) -> None:
        """
        Shutdown the context manager.
        
        This method cleans up any remaining context data and resets
        the internal state.
        """
        try:
            with self._lock:
                if hasattr(self._contexts, 'stack'):
                    self._contexts.stack.clear()
            self._initialized = False
        except Exception:
            # Silent observer - don't interrupt shutdown process
            pass
    
    @property
    def is_initialized(self) -> bool:
        """Check if the context manager is initialized."""
        return self._initialized
    
    @property
    def has_context(self) -> bool:
        """Check if there is an active context."""
        return self._get_current_context() is not None 