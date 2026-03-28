"""
FastAPI / ASGI middleware for slpy.

One line wires automatic context propagation into every request:

    from slpy.fastapi import SyntropyMiddleware

    app = FastAPI()
    app.add_middleware(SyntropyMiddleware)

Every log emitted during a request automatically carries the fields
declared in the 'context.propagation' config (correlation_id, trace_id,
session_id, transaction_id) plus any custom_headers configured.
"""

import uuid
from typing import Any, Dict, Optional

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

        Reads headers defined in slpy.init() context.propagation config,
        sets them in context under their conceptual names, and forwards
        them in the response.

        No configuration needed here — everything is declared in init().
        """

        async def dispatch(self, request: Request, call_next: Any) -> Response:
            from slpy import slpy  # late import to avoid circular dependency

            propagation: Dict[str, str] = slpy._config.context.propagation
            custom_headers = slpy._config.context.custom_headers

            # Build context fields from propagation config
            ctx_fields: Dict[str, Any] = {}
            response_headers: Dict[str, str] = {}

            for field_name, header_name in propagation.items():
                value = request.headers.get(header_name)
                if value is None and field_name == "correlation_id":
                    value = str(uuid.uuid4())  # always generate if missing
                if value is not None:
                    ctx_fields[field_name] = value
                    response_headers[header_name] = value

            # Custom headers — stored as-is using normalized key
            for header_name in custom_headers:
                value = request.headers.get(header_name)
                if value is not None:
                    key = header_name.lower().replace("-", "_")
                    ctx_fields[key] = value

            ctx_fields["method"] = request.method
            ctx_fields["path"] = str(request.url.path)

            async with slpy.context(**ctx_fields):
                response = await call_next(request)
                for header_name, value in response_headers.items():
                    response.headers[header_name] = value
                return response

else:
    class SyntropyMiddleware:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _require_starlette()
