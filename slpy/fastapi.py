"""
FastAPI / ASGI middleware for slpy.

One line wires automatic correlation propagation into every request:

    from slpy.fastapi import SyntropyMiddleware

    app = FastAPI()
    app.add_middleware(SyntropyMiddleware)

Every log emitted during a request automatically carries:
    correlation_id, method, path
"""

import uuid
from typing import Any

# Starlette is a dependency of FastAPI — no extra install needed.
try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    _starlette_available = True
except ImportError:
    _starlette_available = False


def _require_starlette() -> None:
    if not _starlette_available:
        raise ImportError(
            "starlette is required for SyntropyMiddleware. "
            "Install it with: pip install fastapi  (starlette is included)"
        )


if _starlette_available:
    class SyntropyMiddleware(BaseHTTPMiddleware):
        """
        ASGI middleware that opens a slpy context scope per request.

        Configuration (optional kwargs to add_middleware):
            correlation_header: str  — header name to read/write (default: X-Correlation-ID)
        """

        def __init__(self, app: Any, correlation_header: str = "X-Correlation-ID") -> None:
            super().__init__(app)
            self._header = correlation_header.lower()

        async def dispatch(self, request: Request, call_next: Any) -> Response:
            from slpy import slpy  # late import to avoid circular dependency

            correlation_id = (
                request.headers.get(self._header) or str(uuid.uuid4())
            )

            async with slpy.context(
                correlation_id=correlation_id,
                method=request.method,
                path=str(request.url.path),
            ):
                response = await call_next(request)
                response.headers[self._header] = correlation_id
                return response

else:
    # Placeholder so imports don't fail when starlette is not installed
    class SyntropyMiddleware:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _require_starlette()
