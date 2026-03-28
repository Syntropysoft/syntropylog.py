# Changelog

All notable changes to slpy are documented here.

---

## [0.1.0] — 2026-03-27

First public release. Complete rewrite of the original `syntropylog` Python prototype —
same declarative philosophy as [SyntropyLog for Node.js](https://github.com/Syntropysoft/SyntropyLog),
rebuilt from scratch for Python idioms.

### Core

- **`SyntropyLog` singleton** — `await slpy.init(config)` / `await slpy.shutdown()` lifecycle.
  Raises on double init. Safe to call `shutdown()` multiple times.
- **`get_logger(name)`** — named loggers cached per name. Same name, same instance.
- **`set_level(level)`** — runtime log level change, propagates to all existing loggers immediately.
- **Default transport** — if no transport configured, `ConsoleTransport` (structured JSON) is used automatically.
- **`SLPY_LOG_LEVEL` env var** — overrides the configured level at startup.

### Logger

- **`child(**bindings)`** — binds context once, carried on every log from the returned instance.
  Immutable — never mutates the parent logger. Fully composable.
- **`with_meta(payload)`** — attaches arbitrary structured metadata to every log as `logEntry['meta']`.
  Use cases: retention routing, compliance tagging, experiment tracking.
- **`audit(message)`** — always emitted regardless of configured log level.
  For compliance events that must always be recorded.
- **Log levels**: `debug`, `info`, `warn`, `error`, `audit`.
- **Silent observer** — transport errors never propagate to the application.

### Context propagation

- **`async with slpy.context(**kwargs)`** — opens a `contextvars` scope. All logs within
  the scope automatically carry the given fields.
- **Python-native `contextvars`** — replaces the previous `threading.local()` approach.
  Propagates correctly across `asyncio.gather()`, `asyncio.create_task()`, and thread-pool executors.
- Scopes are isolated — inner scopes do not mutate outer ones. Zero memory leak at 10M iterations.

### MaskingEngine

- **Flatten → match → unflatten strategy** — handles nested objects at any depth.
- **Default rules** — email, password, token/key/auth/jwt/bearer, credit card, SSN, phone.
  Enabled by default. Disable with `enable_default_rules=False`.
- **Custom rules** — add patterns at `init()` with any `MaskingStrategy`.
- **Custom mask function** — `MaskingStrategy.CUSTOM` with a `custom_mask: callable`.
- **Non-string values** — numbers, booleans, None are never masked.
- **Silent observer** — masking errors return the original data unchanged.

### Rust addon — slpy-native

- **`NativeMaskingEngine`** — Rust implementation of the full masking pipeline (flatten, regex, unflatten).
- **59% faster masking** — overhead reduced from 29 µs to 12 µs on complex nested objects.
- **Automatic activation** — `MaskingEngine` delegates to Rust when `slpy-native` is installed.
  No code changes required.
- **Transparent fallback** — if the addon is unavailable or the build fails, the Python engine
  is used automatically.
- **`custom_mask` fallback** — rules with Python callables always use the Python engine
  (Python functions cannot be called from Rust).
- **Disable with env var** — `SLPY_NATIVE_DISABLE=1`.

### FastAPI / ASGI middleware

- **`SyntropyMiddleware`** — pure ASGI middleware. One line wires automatic context propagation
  into every request: `correlation_id`, `method`, `path`.
- Extracts `X-Correlation-ID` from incoming headers or generates a UUID.
- Forwards `X-Correlation-ID` in the response.
- Works with FastAPI, Starlette, Litestar, and any ASGI server (uvicorn, hypercorn).
- No FastAPI-specific dependency — only `starlette` (already a FastAPI dependency).

### Transports

- **`ConsoleTransport`** — structured JSON to stdout. Default when no transport is configured.
- **`PrettyConsoleTransport`** — human-readable colored output for development. Zero external
  dependencies — pure ANSI codes. Auto-detects TTY: falls back to JSON automatically when stdout
  is not a terminal (CI, pipes, production). Colors per level: debug=dim grey, info=green,
  warn=yellow, error=red, audit=cyan. Format: `HH:MM:SS.mmm  LEVEL  service  message  key=value`.
  Masking remains active — sensitive fields are masked in pretty output too.
  `colors=True/False` to force on/off; default=auto-detect.
- **`UniversalAdapter`** — wraps an executor function (sync or async) that receives the clean,
  already-masked log entry and routes it to any destination. The entry arrives with context
  propagation applied, masking complete, and all bindings merged. The executor is the only
  thing the consumer writes.
- **`AdapterTransport`** — transport that delegates to a `UniversalAdapter`. Accepts an optional
  `formatter` to transform the entry before it reaches the executor (field mapping, type
  conversion, schema adaptation). One executor can fan out to N destinations via `asyncio.gather`.
  Silent observer — errors in the executor never propagate to the application.
- **`Transport` base class** — implement `log(entry: dict)` to route entries anywhere.
- Multiple transports supported — entries are sent to all of them.

### Performance (Windows 11, Python 3.14, local — Linux is 30–50% better)

| Scenario | logs/sec | µs/log |
|----------|----------|--------|
| Simple log (Rust addon) | ~51,000 | 19.4 |
| child() + log | ~34,000 | 29.0 |
| MaskingEngine only | ~30,000 | 33.6 |
| Complex log + masking | ~17,000 | 57.1 |
| Async context scope | ~12,000 | 79.2 |

Zero degradation from 100k to 10M iterations across all scenarios.

Compared to ecosystem peers (pyperf, null transport, Windows):

| Logger | Simple log | Complex + masking |
|--------|-----------|------------------|
| **slpy** | **6.2 µs ①** | **18.0 µs ✅ masking ON** |
| structlog | 8.0 µs | 10.8 µs (no masking) |
| logging (stdlib) | 18.8 µs | 20.4 µs (no masking) |
| loguru | 58.9 µs | 61.8 µs (no masking) |

### Testing

- 77 tests across config, masking, context, logger, core, transports, adapter, and FastAPI middleware.
- `CaptureTransport` pattern for asserting log output without I/O.
- `pytest-asyncio` with `asyncio_mode = auto`.
- 85% coverage. Uncovered lines are Rust addon paths (only active when `slpy-native` is installed) and silent observer `except` blocks.

### Examples

- `01_basic_setup.py` — init, get_logger, log levels.
- `02_named_loggers_and_child.py` — named loggers, child() composition.
- `03_context_propagation.py` — contextvars across asyncio.gather().
- `04_masking.py` — default rules, nested objects, custom rules.
- `05_with_meta_and_audit.py` — with_meta(), audit level bypass.
- `06_fastapi_middleware.py` — SyntropyMiddleware with lifespan.
- `07_pretty_console.py` — PrettyConsoleTransport colored output.
- `08_adapter_transport.py` — AdapterTransport + UniversalAdapter fanout to Postgres, MongoDB, Elasticsearch simultaneously.

### Package

- **Zero runtime dependencies** — `install_requires = []`.
- `pyproject.toml` (PEP 517/518) alongside `setup.py`.
- `py.typed` marker — full type annotation support.
- Optional extras: `slpy[fastapi]`, `slpy[dev]`.
- GitHub Actions: benchmark workflow runs on every push to `main`.

### Removed from original prototype

The following components from the original `syntropylog` Python prototype were removed.
They were unfinished skeletons that added complexity without delivering functionality:

- `HttpManager` — HTTP instrumentation skeleton
- `BeaconRedis` — Redis context storage skeleton
- `BrokerManager` — Kafka/RabbitMQ/NATS skeleton
- `SerializationManager` — custom serialization pipeline skeleton
- `standalone_logger.py` — parallel logger outside the framework
- Signal handlers registered at import time (`SIGINT`/`SIGTERM` in `__init__.py`)
- Async queue worker in logger (`deque` + background `asyncio.Task`)
- `threading.local()` context storage (replaced by `contextvars`)

---

## Prior history

The original `syntropylog` Python package (versions before 0.1.0) was an internal
prototype and is not documented here. This changelog begins with the public release.
