# slpy — Refactor Plan

> Port of SyntropyLog (Node.js) to Python. Goal: same declarative philosophy, same core surface, Python-idiomatic.

---

## Can this work?

Yes. The fundamentals are already there:

- `MaskingRule` with pre-compiled regex patterns — solid
- `LoggerMatrix` for per-level context filtering — solid
- `ContextData` with correlation IDs — solid
- Async-first design — correct direction

The blocking issues are architectural, not logical. They are all fixable in a linear sequence.

---

## Phase 1 — Remove everything that doesn't belong in the core

### Files to delete entirely

| File/Folder | Reason |
|-------------|--------|
| `syntropylog/http/` | Integration, not core. Reintroduce as optional extra later. |
| `syntropylog/redis/` | Integration, not core. Reintroduce as optional extra later. |
| `syntropylog/brokers/` | Integration, not core. Reintroduce as optional extra later. |
| `syntropylog/serialization/` | Unnecessary pipeline abstraction. Python's `json` module is sufficient for the core. |
| `syntropylog/standalone_logger.py` | Parallel logger that shouldn't exist outside the framework. |

### Changes inside existing files

**`syntropylog/core.py`**

Remove:
- `HttpManager` import and `_http` attribute
- `BeaconRedis` import and `_redis` attribute
- `BrokerManager` import and `_brokers` attribute
- `SerializationManager` import and `_serialization` attribute
- Steps 4, 5, 6, 7 in `init()` (HTTP, Redis, Brokers, Serialization)
- Corresponding shutdown entries in `components_to_shutdown`
- `add_context_with_matrix()` method — matrix belongs in config declaration, not imperative API
- `get_filtered_context()` method — internal, not public API
- `add_masking_rule()` imperative method — rules are declared at `init()`, not added after

Keep:
- `init()` / `shutdown()` lifecycle
- `context()` async context manager
- `get_logger(name)` — named loggers
- `mask_data()` — direct masking utility
- `set_log_level()` — runtime level change (legitimate hot-reload)
- `is_initialized` property

**`syntropylog/logger.py`**

Remove:
- `UltraFastTransport` class entirely — the async `deque` + background worker is unnecessary complexity
- `_queue`, `_worker_task`, `_worker()`, `_start_worker()` from any logger class
- `LoggerFactory` if it only wraps construction — replace with direct instantiation

Keep:
- `LogLevel` enum
- `LogEntry` dataclass
- `ConsoleTransport` — simplified to synchronous `print` / `sys.stdout.write`
- Logger class with `debug()`, `info()`, `warn()`, `error()`, `audit()` methods
- `child(bindings)` — binds context once, carried on every subsequent log
- `with_meta(payload)` — equivalent of TS `withMeta()`

**`syntropylog/context.py`**

Remove:
- `import threading` — replace with `contextvars` (Python 3.7+ native)
- `threading.local()` based storage — replace with `contextvars.ContextVar`
- `add_with_matrix()` imperative method
- `configure_logger_matrix()` imperative method

Keep:
- `LoggerMatrix` dataclass — context field filtering per level
- `ContextData` dataclass — correlation ID + data
- `ContextManager` class with `scope(**kwargs)` async context manager

The fix: `contextvars.ContextVar` is Python's native `AsyncLocalStorage` equivalent.
It propagates correctly across `asyncio.create_task()`, `asyncio.gather()`, and thread pools.

```python
# Before (broken in async)
_local = threading.local()

# After (correct)
from contextvars import ContextVar
_current_context: ContextVar[ContextData] = ContextVar('_current_context', default=None)
```

**`syntropylog/__init__.py`**

Remove:
- `import signal` + `signal.signal()` calls at module level — side effect on import
- `_signal_handler()` function — the application owns its shutdown, not the framework
- `_graceful_shutdown_with_timeout()` — move to user's application entry point if needed
- All imports of deleted modules (http, redis, brokers, serialization, testing mocks for those)
- `_shutdown_event`, `_shutdown_in_progress` globals

Keep:
- `slpy` singleton instance (renamed from `syntropy_log`)
- Core class exports
- `__version__`, `__author__`, `__license__`

**`syntropylog/config.py`**

Remove:
- `get_http_config()`, `get_redis_config()`, `get_broker_config()`, `get_serialization_config()`
- All `HttpConfig`, `RedisConfig`, `BrokerConfig`, `SerializationConfig` dataclasses

Keep:
- `LoggerConfig` (level, transports)
- `MaskingConfig` (rules, max_depth)
- `ContextConfig` (correlation_id_header, enable_auto_correlation)
- `Config` / `ConfigManager` with `validate()`

---

## Phase 2 — Rename to slpy

### Package rename

| Before | After |
|--------|-------|
| `syntropylog/` (package dir) | `slpy/` |
| `from syntropylog import syntropy_log` | `from slpy import slpy` |
| `syntropy_log.init(...)` | `slpy.init(...)` |
| `setup.py` name: `"syntropylog"` | `"slpy"` |

### Singleton rename

```python
# __init__.py
slpy = SyntropyLog()
```

### Public API after rename

```python
from slpy import slpy

await slpy.init({
    'logger': {'level': 'info'},
    'masking': {'enableDefaultRules': True},
})

logger = slpy.get_logger('payment-service')
logger.info('Payment processed', amount=299)

async with slpy.context(user_id='123', request_id='abc'):
    logger.info('User action')
```

---

## Phase 3 — Package and publish

### `setup.py` / `pyproject.toml`

Migrate from `setup.py` to `pyproject.toml` (PEP 517/518 — current standard):

```toml
[project]
name = "slpy"
version = "0.1.0"
description = "The declarative observability framework for Python"
requires-python = ">=3.7"
dependencies = []  # zero runtime dependencies
```

Zero runtime dependencies — same as the Node.js version.

### Entry point

```python
# slpy/__init__.py
from .core import SyntropyLog

slpy = SyntropyLog()

__all__ = ['slpy', 'SyntropyLog', 'ConsoleTransport', 'MaskingEngine', ...]
__version__ = "0.1.0"
```

---

## Phase 5 — FastAPI / ASGI middleware integration

Same pattern as Node.js (Express/Fastify middleware). One line wires everything.

```python
from slpy.fastapi import SyntropyMiddleware

app = FastAPI()
app.add_middleware(SyntropyMiddleware)
```

What the middleware does automatically (same as Node.js):
- Extracts `correlation_id` from incoming header (`X-Correlation-ID` or configurable) — or generates one if absent
- Opens a `contextvars` scope for the lifetime of the request
- All logs emitted during the request automatically carry `correlation_id`, `request_id`, `method`, `path`
- Masking pipeline active on every log within scope
- Closes the scope cleanly when the response is sent

Implementation: pure ASGI middleware (works with FastAPI, Starlette, any ASGI framework).
No FastAPI-specific dependency — `SyntropyMiddleware` only depends on the ASGI spec.

```python
# slpy/fastapi.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from slpy import slpy

class SyntropyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = (
            request.headers.get('x-correlation-id') or
            str(uuid.uuid4())
        )
        async with slpy.context(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        ):
            response = await call_next(request)
            response.headers['x-correlation-id'] = correlation_id
            return response
```

This is the gap in the Python ecosystem today — no single package does structured logging
+ masking + automatic request context in one middleware line.

---

## Phase 4 — New README (post-rename)

Mirror the Node.js README philosophy:

- Tagline: "The Declarative Observability Framework for Python"
- "You declare what each log should carry. slpy handles the rest."
- Same 3-column table: what you declare / what slpy does automatically / outcome
- `await slpy.init(config)` as canonical entry point
- Named loggers + `.child()` pattern
- `with_meta()` for structured payload routing
- Benchmark section (vs structlog, loguru, standard logging)
- Zero dependencies

---

## What stays, what goes — summary table

| Component | Status | Reason |
|-----------|--------|--------|
| `MaskingEngine` | Keep | Core differentiator, well-implemented |
| `LoggerMatrix` | Keep | Declarative field filtering |
| `ContextManager` (with contextvars fix) | Keep + fix | Core feature |
| `Logger` + `child()` + `with_meta()` | Keep + add | Core API |
| `ConsoleTransport` | Keep, simplify | Default transport |
| `HttpManager` | Remove | Integration layer, not core |
| `BeaconRedis` | Remove | Integration layer, not core |
| `BrokerManager` | Remove | Integration layer, not core |
| `SerializationManager` | Remove | Over-engineered, unnecessary |
| `standalone_logger.py` | Remove | Parallel logger, no place in framework |
| Signal handlers in `__init__` | Remove | Side effect on import, app's responsibility |
| Async queue worker in logger | Remove | Not deterministic, not needed |

---

## Risk assessment

**Low risk — the core logic is sound.** Masking, matrix filtering, and context propagation are the hardest parts and they're already written correctly. The removals are subtractive — we are not rewriting logic, we are deleting complexity.

**One real fix required:** `contextvars` migration in `context.py`. Without this, context propagation breaks in any `asyncio.gather()` or `create_task()` scenario. It's a targeted change (~30 lines) but it's required for correctness.

**Testing:** The existing `examples/` folder provides a good smoke-test suite. After phase 1 they should still run (minus any examples that depend on deleted integrations).
