<p align="center">
  <img src="./assets/syntropysoft-logo.png" alt="SyntropySoft Logo" width="170"/>
</p>

<h1 align="center">slpy</h1>

<p align="center">
  <strong>The Declarative Observability Framework for Python.</strong>
  <br />
  You declare what each log should carry. slpy handles the rest.
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/status-alpha-orange.svg" alt="Alpha"></a>
  <a href="https://github.com/Syntropysoft/SyntropyLog/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.7+-blue.svg" alt="Python 3.7+"></a>
  <a href="#"><img src="https://img.shields.io/badge/dependencies-zero-brightgreen.svg" alt="Zero dependencies"></a>
</p>

---

## What is slpy?

Every Python team writes the same boilerplate: thread `request_id` through every function signature, scrub `password` fields before logging, remember to call `logger.info()` instead of `print()`, repeat the same `extra={"service": "payment"}` on every call.

slpy solves the boilerplate problem declaratively. You declare the rules once at startup. The framework applies them consistently on every log call, in every coroutine, across every service — without you thinking about it again.

```python
from slpy import slpy

await slpy.init({
    'logger': {'level': 'info'},
    'masking': {'enable_default_rules': True},
})

logger = slpy.get_logger('payment-service')

async with slpy.context(request_id='req-001', user_id='usr-42'):
    logger.info('Card charged', amount=299.90, email='john@example.com')
    # → {"level":"info","message":"Card charged","service":"payment-service",
    #    "request_id":"req-001","user_id":"usr-42",
    #    "amount":299.9,"email":"j******n@example.com"}
```

The `request_id` propagated automatically. The `email` was masked automatically. The `service` field appeared automatically. You wrote none of that explicitly.

---

## The declarative shift

| Instead of... | You declare... | slpy does automatically |
|---------------|----------------|------------------------|
| Threading `request_id` through every function | `async with slpy.context(request_id=id)` | Propagates to all logs in scope via `contextvars` |
| Scrubbing sensitive fields before logging | `masking: {enable_default_rules: True}` | Masks email, password, token, credit card on every log |
| Repeating `extra={"service": "payment"}` | `slpy.get_logger('payment-service')` | `service` field on every log from that logger |
| Copying context into child functions | `logger.child(order_id='123')` | All bindings carried automatically on every subsequent call |
| Routing compliance logs manually | `logger.with_meta({"regulation": "GDPR"})` | `meta` payload travels sanitized to all transports |

---

## Quick start

```bash
pip install slpy
```

```python
import asyncio
from slpy import slpy

async def main():
    await slpy.init({
        'logger': {'level': 'info'},
        'masking': {'enable_default_rules': True},
    })

    logger = slpy.get_logger('my-service')
    logger.info('Service started')

    await slpy.shutdown()

asyncio.run(main())
```

No transport configured → `ConsoleTransport` (structured JSON) is used automatically.

---

## Named loggers and child()

Each component gets its own named logger. `child()` binds context once — every log from that instance carries it automatically. Bindings are immutable and composable.

```python
async def process_order(order_id: str, user_id: str) -> None:
    # Bind once — no need to repeat on every call
    logger = slpy.get_logger('order-service').child(
        order_id=order_id,
        user_id=user_id,
    )

    logger.info('Processing')                          # carries order_id, user_id
    logger.info('Calculated', total=299.90, items=3)   # carries order_id, user_id

    payment = logger.child(step='payment')             # adds step, keeps the rest
    payment.info('Charging card')                      # carries order_id, user_id, step
    payment.info('Approved', amount=299.90)
```

`child()` never mutates the parent. Each call returns a new logger with merged bindings.

---

## Context propagation

slpy uses Python's native `contextvars` — the same mechanism as `AsyncLocalStorage` in Node.js. Context propagates correctly across `asyncio.gather()`, `asyncio.create_task()`, and thread-pool executors.

```python
async def handle_request(request_id: str, user_id: str) -> None:
    async with slpy.context(request_id=request_id, user_id=user_id):
        logger.info('Request received')            # request_id, user_id here
        await fetch_from_db()                      # request_id, user_id here too
        logger.info('Request complete')

async def fetch_from_db() -> None:
    # No function argument needed — context is already here
    logger.debug('Running query')                  # request_id, user_id propagated
```

Concurrent requests are fully isolated. Each `async with slpy.context(...)` opens its own scope; inner scopes do not leak into outer ones.

---

## Data masking

Masking runs automatically on every log entry. Default rules cover the most common sensitive fields. The engine flattens nested objects, applies rules by field name, then reconstructs the original structure — at any depth.

```python
await slpy.init({
    'masking': {
        'enable_default_rules': True,   # email, password, token, credit card, SSN, phone
        'rules': [
            # Add your own — patterns compiled once at init()
            {'pattern': r'internal_code', 'strategy': 'token'},
        ],
    },
})

logger.info('Payment', credit_card_number='4111-1111-1111-1234', amount=299.90)
# → credit_card_number: "************1234"   amount: 299.9 (not masked)

logger.info('User', email='john@example.com', name='John Doe')
# → email: "j******n@example.com"   name: "John Doe" (not masked)

logger.info('Order', order={'user': {'token': 'abc123', 'id': 'USR-1'}})
# → order.user.token: "******"   order.user.id: "USR-1" (not masked)
```

**Default rules**

| Field pattern | Strategy | Example result |
|---------------|----------|----------------|
| `email`, `mail` | Email | `j******n@example.com` |
| `password`, `pass`, `pwd`, `secret` | Full mask | `************` |
| `token`, `key`, `auth`, `jwt`, `bearer` | Full mask | `**********` |
| `credit_card`, `card_number` | Last 4 | `************1234` |
| `ssn`, `social_security` | Last 4 | `*****6789` |
| `phone`, `mobile`, `tel` | Last 4 | `*******4567` |

---

## Audit level and with_meta()

`audit` bypasses the configured level filter — it is always emitted. Use it for compliance events that must always be recorded regardless of the runtime log level.

`with_meta(payload)` attaches arbitrary structured metadata to every log from that logger instance. The payload travels sanitized to all transports as `logEntry['meta']`.

```python
audit_logger = (
    slpy.get_logger('compliance')
    .with_meta({
        'ttl_days': 730,
        'regulation': 'GDPR',
        'data_class': 'PII',
        'destination': 'audit-store',
    })
    .child(user_id='USR-42')
)

audit_logger.audit('Data exported', records=1500)
# → level: "audit"  meta: {ttl_days: 730, regulation: "GDPR", ...}
#   user_id: "USR-42"  records: 1500

# audit always appears — even when level is 'error'
await slpy.init({'logger': {'level': 'error'}})
logger.info('hidden')    # not emitted
logger.audit('visible')  # always emitted
```

**with_meta() use cases**

| Use case | Payload |
|----------|---------|
| Log retention routing | `{"ttl_days": 730, "destination": "cold-storage"}` |
| Compliance tagging | `{"regulation": "GDPR", "data_class": "PII"}` |
| Experiment tracking | `{"experiment": "checkout-v2", "variant": "B"}` |
| Release context | `{"version": "1.4.0", "deploy_id": "d-001"}` |

---

## FastAPI / ASGI middleware

One line wires automatic context propagation into every request.

```bash
pip install slpy[fastapi]
```

```python
from fastapi import FastAPI
from slpy import slpy
from slpy.fastapi import SyntropyMiddleware

app = FastAPI()
app.add_middleware(SyntropyMiddleware)
```

Every log emitted during a request automatically carries `correlation_id`, `method`, and `path` — extracted from the incoming header or generated if absent. The `X-Correlation-ID` header is forwarded in the response.

```python
@app.get('/orders/{order_id}')
async def get_order(order_id: str):
    logger.info('Fetching', order_id=order_id)
    # → {"level":"info","message":"Fetching","service":"api",
    #    "correlation_id":"req-abc","method":"GET","path":"/orders/123",
    #    "order_id":"123"}
```

`SyntropyMiddleware` is pure ASGI — it works with FastAPI, Starlette, Litestar, and any ASGI server (uvicorn, hypercorn) without framework-specific dependencies.

---

## Runtime level change

```python
sl.set_level('debug')   # all existing loggers update immediately
sl.set_level('error')   # back to quiet
```

---

## Custom transports

Extend `Transport` and implement `log(entry)` to route entries anywhere.

```python
from slpy.transport import Transport

class ElasticsearchTransport(Transport):
    def log(self, entry: dict) -> None:
        self._es_client.index(index='logs', body=entry)

await slpy.init({
    'logger': {
        'transports': [ElasticsearchTransport()],
    },
})
```

Multiple transports are supported — entries are sent to all of them.

---

## Performance

slpy includes an optional Rust addon (`slpy-native`) that accelerates the masking engine. When installed, it is used automatically with no code changes.

```
Simple log             Complex object + masking
─────────────────────  ────────────────────────────────────
slpy        6.2 µs  ①  structlog      10.8 µs  (no masking)
structlog   8.0 µs     slpy           18.0 µs  ② ✅ masking ON
logging    18.8 µs     logging        20.4 µs  (no masking)
loguru     58.9 µs     loguru         61.8 µs  (no masking)
```

**slpy is the fastest structured logger on simple logs** — faster than structlog, which is the Python performance reference.

**slpy with masking fully active is faster than the stdlib `logging` module without masking.** It is 3.4x faster than loguru without masking.

The Rust addon reduced masking overhead from 29 µs to 12 µs (59% improvement). If the addon is not installed, slpy falls back to the pure Python engine transparently.

### Sustained throughput — 1M and 10M iterations

> Windows 11, Python 3.14.3, local machine. Linux numbers are 30–50% better.

| Scenario | logs/sec | µs/log | 1M → 10M degradation |
|----------|----------|--------|----------------------|
| Simple log | ~51,000 | 19.4 | **none** (19.45 → 19.44 µs) |
| child() + log | ~34,000 | 29.0 | **none** |
| MaskingEngine only | ~30,000 | 33.6 | **none** |
| Complex log + masking | ~17,000 | 57.1 | **none** (warm cache slightly faster) |
| Async context scope | ~12,000 | 79.2 | **none** |

Zero degradation from 1M to 10M iterations. Heap delta at 10M is 8–32 bytes across all scenarios — no memory leaks, no GC pressure accumulation. `child()` allocates 0 bytes at sustained volume.

See [benchmark/README.md](benchmark/README.md) for full methodology and how to reproduce.

---

## What slpy is not

slpy is a structured logging and context propagation framework. It is not:

- A log aggregation backend (use Elasticsearch, Loki, CloudWatch)
- A distributed tracing system (use OpenTelemetry)
- A metrics collector (use Prometheus, Datadog)

It is the component that makes every log line correct, consistent, and safe before it reaches any of those systems.

---

## Security

**No network I/O at runtime.** slpy does not contact any external URLs. The only output is what your transports produce.

**Zero runtime dependencies.** The core package has no `install_requires`. The optional `[fastapi]` extra adds only `starlette` (already a FastAPI dependency).

**Masking and custom functions.** The `custom_mask` function in masking rules is consumer-supplied configuration — it is not influenced by external input. See [socket.dev note](#) for full analysis.

---

## Installation

```bash
# Core (zero dependencies)
pip install slpy

# With FastAPI middleware
pip install slpy[fastapi]

# Development
pip install slpy[dev]
```

Requires Python 3.7+.

---

## Running the examples

```bash
git clone https://github.com/Syntropysoft/slpy
cd slpy

# Basic setup
py examples/01_basic_setup.py

# Named loggers and child()
py examples/02_named_loggers_and_child.py

# Context propagation with asyncio.gather()
py examples/03_context_propagation.py

# Data masking
py examples/04_masking.py

# with_meta() and audit level
py examples/05_with_meta_and_audit.py

# FastAPI middleware (requires: pip install fastapi uvicorn)
uvicorn examples.06_fastapi_middleware:app --reload
```

## Running the tests

```bash
pip install slpy[dev]
pytest
```

---

## Documentation

- **[Refactor plan and architecture](docs/slpy-refactor-plan.md)** — Design decisions and what was removed and why.
- **[Data masking](docs/data_masking.md)** — Masking strategies, default rules, custom rules.
- **[Logger matrix](docs/logger_matrix.md)** — Per-level field filtering.

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
