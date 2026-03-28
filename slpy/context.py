"""
Context propagation for slpy.

Uses Python's native contextvars.ContextVar — the correct tool for async
context propagation across asyncio.create_task(), asyncio.gather(), and
thread-pool executors. Equivalent to Node.js AsyncLocalStorage.
"""

import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, Dict

_ctx: ContextVar[Dict[str, Any]] = ContextVar("_slpy_ctx", default={})


class ContextManager:
    """
    Opens and closes async context scopes.
    All log calls within a scope automatically carry the context data.
    Scopes are isolated — inner scopes do not mutate the outer scope.
    """

    @asynccontextmanager
    async def scope(self, **kwargs: Any):
        """
        Open a context scope with the given key/value pairs.

        Example:
            async with slpy.context(user_id="123", request_id="abc"):
                logger.info("User action")
                # user_id and request_id appear in every log line
        """
        current = _ctx.get()
        token = _ctx.set({**current, **kwargs})
        try:
            yield
        finally:
            _ctx.reset(token)

    def get(self) -> Dict[str, Any]:
        """Return the current context snapshot."""
        return _ctx.get()

    def get_correlation_id(self) -> str:
        """Return the current correlation_id or generate a new one."""
        return _ctx.get().get("correlation_id", str(uuid.uuid4()))
