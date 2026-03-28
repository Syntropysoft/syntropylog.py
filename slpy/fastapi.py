"""
FastAPI / ASGI middleware for slpy.

One line wires automatic context propagation into every request:

    from slpy.fastapi import SyntropyMiddleware

    app = FastAPI()
    app.add_middleware(SyntropyMiddleware, source=SOURCE_FRONTEND)

The `source` parameter selects which inbound mapping to use — declared
in context.inbound config. Each source can have different header names
for the same conceptual fields.
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

        source — selects the inbound mapping declared in context.inbound.
                 Defaults to 'default'. Use a constant for clarity:

                     app.add_middleware(SyntropyMiddleware, source=SOURCE_FRONTEND)
        """

        def __init__(self, app: Any, source: str = "default") -> None:
            super().__init__(app)
            self._source = source

        async def dispatch(self, request: Request, call_next: Any) -> Response:
            from slpy import slpy  # late import to avoid circular dependency

            inbound_map: Dict[str, str] = (
                slpy._config.context.inbound.get(self._source, {})
            )
            outbound_propagation: Dict[str, str] = (
                slpy._config.context.outbound.propagation
            )
            custom_headers = slpy._config.context.custom_headers

            ctx_fields: Dict[str, Any] = {}
            response_headers: Dict[str, str] = {}

            for field_name, header_name in inbound_map.items():
                value = request.headers.get(header_name)
                if value is None and field_name == "correlation_id":
                    value = str(uuid.uuid4())
                if value is not None:
                    ctx_fields[field_name] = value
                    # Forward using the outbound wire name if configured
                    outbound_header = outbound_propagation.get(field_name, header_name)
                    response_headers[outbound_header] = value

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
