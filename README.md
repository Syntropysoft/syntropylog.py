<p align="center">
  <img src="https://syntropysoft.com/syntropylog-logo.png" alt="SyntropyLog Logo" width="170"/>
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

<p align="center">
  slpy is the Python member of the SyntropyLog family — same declarative model, three runtimes:
  <a href="https://www.npmjs.com/package/syntropylog"><strong>SyntropyLog</strong></a> (Node.js) ·
  <a href="https://www.nuget.org/packages/sl4n/"><strong>sl4n</strong></a> (.NET) ·
  <strong>slpy</strong> (Python)
</p>

---

## What's new in 0.4.0

- **Logging Matrix** — a per-level whitelist of context fields, declared once. [Section ›](#logging-matrix)
- **Retention policies** — named compliance policies (`with_retention('SOX_AUDIT_TRAIL')`) stamped on every tagged entry. [Section ›](#retention-policies)
- **DurableFileTransport** — audit delivery that survives backend outages AND process restarts, via a self-emptying disk spool. [Section ›](#durable-delivery--durablefiletransport)
- **Masking hardened, in BOTH engines (Python + Rust)** — non-string values and nested objects under a sensitive key are now masked (`password=12345` and `password={'hash': ...}` no longer leak); lists are no longer corrupted by the masking pass; `MASK_KEYS` aliases + `mask_pattern()`; `on_masking_error` hook; on failure the entry degrades to a safe payload — raw metadata never leaks.
- **Safety boundary** — ANSI/control characters stripped from every string before transports (log-injection defense); `on_log_failure` hook; `slpy.get_stats()` health counters.
- **Testing toolkit** — `slpy.testing.SpyTransport` for asserting on emitted (and masked) entries.
- **Timestamps are now ISO-8601** with milliseconds and offset (was epoch-ms) — the same format as SyntropyLog and sl4n.

Details: [CHANGELOG.md](CHANGELOG.md).

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
| Filtering noisy context per level | `logging_matrix: {'info': [...], 'error': ['*']}` | Only whitelisted context fields reach a transport at each level |
| Routing compliance logs manually | `logger.with_retention('SOX_AUDIT_TRAIL')` | `retention` / `retention_class` / `retention_days` stamped on every entry |
| Writing a transport class per destination | `AdapterTransport(adapter=UniversalAdapter(executor=fn))` | Your executor receives the clean entry — connect to anything |
| Manually building headers per destination | `context.targets: {kafka: {...}, s3: {...}}` | `get_propagation_headers("kafka")` returns the right key names |
| Adding tracing calls before every outbound call | `observability: {transports: [...]}` | `OutboundEvent` emitted automatically on every `get_propagation_headers()` |

---

## Quick start

```bash
pip install slpy-log
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

## Logging Matrix

A declarative whitelist deciding **which context fields appear at each log level**. A context field not whitelisted for a level never reaches a transport. Compliance reviews the matrix, not your codebase.

```python
await slpy.init({
    'logging_matrix': {
        'default': ['request_id'],                       # any level not listed
        'info':    ['request_id', 'user_id', 'operation'],
        'error':   ['*'],                                # '*' = every context field
    },
})

async with slpy.context(request_id='req-7', user_id='u-1', tenant_id='acme'):
    logger.info('Payment captured')
    # → request_id, user_id  (tenant_id dropped — not in the info whitelist)
    logger.error('Payment failed')
    # → request_id, user_id, tenant_id  ('*' lets everything through)
```

**The matrix governs context, not per-call data.** Core fields (`level`, `message`, `service`, `timestamp`), `child()` bindings and per-call kwargs are always emitted (and masked) — if you don't want a per-call field logged, don't pass it. The matrix exists for the auto-propagating context you *can't* trim at each call site.

Semantics (identical across the family):

1. No `logging_matrix` configured → every context field passes (nothing changes).
2. Level listed → only those fields pass.
3. Level not listed → the `default` entry applies.
4. Neither the level nor `default` exist → **all context is dropped** for that level. Strict whitelist — always define `default`.
5. A list containing `'*'` → every context field passes at that level.

Change it at runtime — only field visibility changes; masking, levels and transports stay as set at `init()`:

```python
slpy.reconfigure_logging_matrix({'default': ['request_id'], 'error': ['*']})
```

---

## Data masking

Masking runs automatically on every log entry, before any transport. Rules match **field names** at any depth; once a key matches, everything beneath it is masked — nested dicts, lists, and non-string scalars included.

> **Masking is by field name, never free text.** It masks the value of fields whose *key* matches a rule; it does **not** scan message text or string contents for PII. Put sensitive data in keyed fields — log-data quality is the caller's responsibility.

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

# Non-strings and nested structures under a sensitive key are masked too:
logger.info('Login', password=12345)             # → password: "*****"
logger.info('Auth', password={'hash': 'abc'})    # → password.hash: "***"
```

**One rule set, two engines, identical output.** If the optional Rust addon (`slpy-native`) is installed, masking runs in Rust; otherwise in pure Python. Both engines share the same semantics, locked by a byte-for-byte parity test fixture — the same discipline the Node.js sibling adopted after a native/JS divergence leaked PII (its KNOWN-ISSUES #2).

Build custom rules from the grouped key aliases instead of string literals (keeps patterns out of secret scanners):

```python
from slpy import MASK_KEYS, mask_pattern

'masking': {
    'rules': [
        {'pattern': mask_pattern(*MASK_KEYS['token']), 'strategy': 'token'},
    ],
}
```

**Failsafe.** Masking never throws. If it fails, the failure is counted (`slpy.get_stats().masking_failures`), reported through the optional `masking.on_masking_error` hook, and the entry degrades to a safe payload (`level`/`timestamp`/`message`/`service` + `_masking_failed: True`) — the raw metadata never leaks. Rules only ever run against field names (capped at 256 chars), never values, which bounds regex evaluation by construction.

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

## Retention policies

Compliance metadata as data: declare named policies once, tag loggers with `with_retention(name)`, and every tagged entry carries the policy — so your transport can route and expire it by rule. slpy attaches the metadata; storage and expiry are the transport's job.

```python
await slpy.init({
    'retention_policies': {
        'SOX_AUDIT_TRAIL': {'days': 2555, 'class': 'SOX'},   # 7 years
        'GDPR_ACCESS':     {'days': 90,   'class': 'GDPR'},
    },
})

audit = slpy.get_logger('payments').with_retention('SOX_AUDIT_TRAIL')
audit.audit('Manager override', user_id='u-1')
# → retention: "SOX_AUDIT_TRAIL"  retention_class: "SOX"  retention_days: 2555
#   level: "audit"  user_id: "u-1"
```

- The stamped fields are **never filtered by the Logging Matrix** — they are bindings, not context.
- An unregistered name still stamps `retention` — compliance intent is never silently dropped.
- Inline policies work without a registry entry: `with_retention({'days': 30, 'class': 'PCI'})`.
- Composes with the rest of the fluent API: `logger.child(...).with_retention(...).with_meta(...)`.

Pair it with `DurableFileTransport` (below) so tagged entries are also *delivered* with guarantees.

---

## FastAPI / ASGI middleware

One line wires automatic context propagation into every request.

```bash
pip install slpy-log[fastapi]
```

```python
from fastapi import FastAPI
from slpy import slpy
from slpy.fastapi import SyntropyMiddleware

# Define your field, source, and target constants once
FIELD_CORRELATION = 'correlation_id'
SOURCE_FRONTEND   = 'frontend'
TARGET_HTTP       = 'http'

await slpy.init({
    'context': {
        'inbound':  {SOURCE_FRONTEND: {FIELD_CORRELATION: 'X-Correlation-ID'}},
        'outbound': {TARGET_HTTP:     {FIELD_CORRELATION: 'X-Correlation-ID'}},
    },
})

app = FastAPI()
app.add_middleware(SyntropyMiddleware, source=SOURCE_FRONTEND)
```

Every log emitted during a request automatically carries `correlation_id`, `method`, and `path` — extracted from the incoming header or generated if absent. The correlation header is forwarded in the response using the outbound wire name.

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

## Propagation headers

### Conceptual field names

`correlation_id`, `trace_id`, `session_id`, `transaction_id` are **conceptual names internal to the framework**. They are not the names that travel on the wire — they are the keys slpy uses to identify each field inside the active context.

The actual name that travels — the HTTP header, the Kafka key, the S3 metadata key — is declared by you in the configuration. The framework uses the conceptual names internally to read and write context, and translates them to the correct wire name for each destination at the moment of sending.

```
inbound['frontend']  internal context   outbound['http']      outbound['kafka']
──────────────────   ────────────────   ─────────────────     ─────────────────
X-Correlation-ID  -> correlation_id ->  X-Correlation-ID  /   correlationId
X-Trace-ID        -> trace_id       ->  X-Trace-ID        /   traceId

inbound['partner']   internal context   outbound['http']      outbound['kafka']
──────────────────   ────────────────   ─────────────────     ─────────────────
x-request-id      -> correlation_id ->  X-Correlation-ID  /   correlationId
x-b3-traceid      -> trace_id       ->  X-Trace-ID        /   traceId
```

`inbound` and `outbound` are symmetric: `{name: {field: wire_name}}`. Each inbound source can use different wire names — the internal context and outbound side are identical regardless of which source the request came in from.

This applies in both directions:

- **Inbound** — `SyntropyMiddleware` reads incoming request headers using the wire names (`X-Correlation-ID`) and stores them in context under the conceptual name (`correlation_id`).
- **Outbound** — `get_propagation_headers()` reads context by conceptual name and returns the dict translated to the wire names for the requested destination.

Application code never sees wire names. It only works with conceptual names.

---

### Configuration

No built-in defaults. You declare exactly the fields your service needs — nothing more, nothing less.

The recommended pattern is to define your own constants in one place and use them as keys everywhere — config, sources, targets, and accessors. This way a typo is caught by the IDE instead of failing silently at runtime. The `FIELD_` and `SOURCE_` prefixes in the examples below are naming conventions — they are not part of slpy.

```python
# fields.py — one place, all your field, source, and target definitions
FIELD_CORRELATION = 'correlation_id'
FIELD_TRACE       = 'trace_id'
FIELD_TENANT      = 'tenant_id'

SOURCE_FRONTEND = 'frontend'
SOURCE_PARTNER  = 'partner'
SOURCE_LEGACY   = 'legacy'

TARGET_HTTP  = 'http'    # default — used by get_propagation_headers() with no arg
TARGET_KAFKA = 'kafka'
TARGET_S3    = 's3'
TARGET_AZURE = 'azure'
```

`inbound` and `outbound` have the same shape: `{name: {field: wire_name}}`. One is keyed by source, the other by destination. The internal context is the translation layer between them.

```python
from myapp.fields import (
    FIELD_CORRELATION, FIELD_TRACE, FIELD_TENANT,
    SOURCE_FRONTEND, SOURCE_PARTNER, SOURCE_LEGACY,
    TARGET_HTTP, TARGET_KAFKA, TARGET_S3, TARGET_AZURE,
)

await slpy.init({
    'context': {
        'inbound': {
            SOURCE_FRONTEND: {FIELD_CORRELATION: 'X-Correlation-ID', FIELD_TRACE: 'X-Trace-ID'},
            SOURCE_PARTNER:  {FIELD_CORRELATION: 'x-request-id',     FIELD_TRACE: 'x-b3-traceid'},
            SOURCE_LEGACY:   {FIELD_CORRELATION: 'correlationid'},
        },
        'outbound': {
            TARGET_HTTP:  {FIELD_CORRELATION: 'X-Correlation-ID', FIELD_TRACE: 'X-Trace-ID'},
            TARGET_KAFKA: {FIELD_CORRELATION: 'correlationId',    FIELD_TRACE: 'traceId'},
            TARGET_S3:    {FIELD_CORRELATION: 'Correlation_ID'},
            TARGET_AZURE: {FIELD_CORRELATION: 'CorrelationID',    FIELD_TRACE: 'TraceID'},
        },
    },
})

# Each middleware instance reads from its declared source
app.add_middleware(SyntropyMiddleware, source=SOURCE_FRONTEND)
```

The `source` parameter tells the middleware which inbound mapping to use. A BFF receiving traffic from multiple origins can declare each source separately — each with different wire names mapping to the same conceptual fields. Outbound is identical regardless of source.

### Usage

```python
async with slpy.context(correlation_id='req-001', trace_id='trace-xyz'):

    # No arg — uses TARGET_HTTP ('http') by default
    await httpx.get(url, headers=slpy.get_propagation_headers())
    # -> {'X-Correlation-ID': 'req-001', 'X-Trace-ID': 'trace-xyz'}

    await kafka.send(topic, headers=slpy.get_propagation_headers(TARGET_KAFKA))
    # -> {'correlationId': 'req-001', 'traceId': 'trace-xyz'}

    await s3.put_object(Metadata=slpy.get_propagation_headers(TARGET_S3))
    # -> {'Correlation_ID': 'req-001'}

    await bus.send(msg, properties=slpy.get_propagation_headers(TARGET_AZURE))
    # -> {'CorrelationID': 'req-001', 'TraceID': 'trace-xyz'}
```

Only fields that have a value in the active context appear in the result.

**Context accessors**

`slpy.get(key)` reads any field from the active context by its conceptual name.

```python
from myapp.fields import FIELD_CORRELATION, FIELD_TRACE, FIELD_TENANT

slpy.get(FIELD_CORRELATION)                          # -> 'req-001'
slpy.get(FIELD_TRACE)                                # -> 'trace-xyz'
slpy.get(FIELD_TENANT)                               # -> 'acme'

slpy.get_propagation_header_name(FIELD_CORRELATION)  # -> 'X-Correlation-ID'
slpy.get_propagation_header_name(FIELD_TENANT)       # -> 'X-Tenant-ID'
```

---

## Observability layer

Every `get_propagation_headers()` call automatically emits an `OutboundEvent` — a trazability record of what context left the service, to which target, and when. **These are not logs.** They are a separate observability channel, never masked, routed to a dedicated set of transports.

```python
from slpy import slpy, ObservabilityTransport, OutboundEvent

class DatadogAPMTransport(ObservabilityTransport):
    def emit(self, event: OutboundEvent) -> None:
        datadog.trace(
            name='outbound',
            resource=event.target,
            span_id=event.trace_id,
            meta=event.headers,
        )

await slpy.init({
    'observability': {
        'transports': [DatadogAPMTransport()],  # Jaeger, Zipkin, custom — anything
    },
})
```

`OutboundEvent` fields:

| Field | Type | Description |
|-------|------|-------------|
| `target` | `str` | `"http"`, `"kafka"`, `"s3"`, `"azure"`, etc. |
| `headers` | `dict` | Key/value pairs as they will be sent |
| `correlation_id` | `str \| None` | From current context |
| `trace_id` | `str \| None` | From current context |
| `timestamp` | `int` | Epoch milliseconds |

```python
event.to_dict()
# → {
#     "event":          "outbound",
#     "target":         "kafka",
#     "headers":        {"correlationId": "req-001"},
#     "correlation_id": "req-001",
#     "trace_id":       "trace-xyz",
#     "timestamp":      1714000000000
#   }
```

**Fanout** — route to multiple backends simultaneously:

```python
'observability': {
    'transports': [JaegerTransport(), ZipkinTransport(), CustomStoreTransport()],
}
```

**Silent observer** — a broken transport never affects the application. The error is swallowed internally.

**Disable entirely:**

```python
'observability': {'enabled': False}  # zero overhead, zero events
```

---

## Runtime level change

```python
sl.set_level('debug')   # all existing loggers update immediately
sl.set_level('error')   # back to quiet
```

---

## Transports

| Transport | Output | Use case |
|-----------|--------|----------|
| `ConsoleTransport` | Structured JSON | Production, CI, log collectors — **default** |
| `PrettyConsoleTransport` | Colored human-readable | Local development |
| `AdapterTransport` | Any destination | Databases, HTTP APIs, queues, multiple targets |
| `DurableFileTransport` | Wraps any of the above | Audit logs that must survive outages and restarts |

### AdapterTransport + UniversalAdapter

The most powerful routing primitive. You provide an `executor` function — sync or async — that receives the clean, already-masked log entry and sends it anywhere. slpy handles context propagation, masking, level filtering, error isolation, and fanout.

```python
from slpy import slpy, AdapterTransport, UniversalAdapter, ConsoleTransport

async def my_executor(data: dict) -> None:
    # One function. Any number of destinations. Fully async.
    await asyncio.gather(
        prisma.system_log.create(data=data),
        mongo_collection.insert_one(data),
        es.index(index='logs', body=data),
    )

db_transport = AdapterTransport(
    name='db',
    adapter=UniversalAdapter(executor=my_executor),
    formatter=lambda e: {**e, 'timestamp': datetime.fromisoformat(e['timestamp'])},
)

await slpy.init({
    'logger': {
        'transports': [
            db_transport,       # → Postgres + MongoDB + Elasticsearch
            ConsoleTransport(), # → stdout
        ],
    },
    'masking': {'enable_default_rules': True},
})
```

When `my_executor` is called, the entry is already:
- **Masked** — `email`, `password`, `token`, credit card fields scrubbed
- **Context-enriched** — `request_id`, `user_id`, any `slpy.context()` fields attached
- **Formatted** — optionally transformed by your `formatter` to match your DB schema

The executor is the only thing you write. Connect to Postgres, MongoDB, Elasticsearch, Datadog, OpenTelemetry, Kafka, a REST API, or all of them at once — slpy does not know or care.

**`formatter`** (optional) — transform the entry before it reaches the executor. Use it to map field names, convert types, or add schema-specific fields:

```python
def db_formatter(entry: dict) -> dict:
    return {
        **entry,
        'timestamp': datetime.fromisoformat(entry['timestamp']),
        'env': os.getenv('APP_ENV', 'production'),
    }
```

### PrettyConsoleTransport

Human-readable colored output. Zero external dependencies — pure ANSI codes.

```python
from slpy import slpy, PrettyConsoleTransport

await slpy.init({
    'logger': {
        'level': 'debug',
        'transports': [PrettyConsoleTransport()],
    },
})
```

```
12:00:00.123  DEBUG  payment-service     Starting up          version=0.1.0
12:00:00.124  INFO   payment-service     Service ready        port=8080
12:00:00.124  WARN   payment-service     High memory usage    heap_mb=420
12:00:00.124  ERROR  payment-service     Connection refused   host=db.internal
12:00:00.124  INFO   payment-service     User login           email=j**n@example.com
12:00:00.124  AUDIT  payment-service     Data exported        meta={"regulation":"GDPR"}
```

**Auto-detects TTY** — when stdout is not a terminal (CI, pipes, production), falls back to JSON
automatically. No code change needed between environments.

Masking remains active in pretty output — sensitive fields are masked regardless of transport.

```python
PrettyConsoleTransport()            # auto-detect TTY (recommended)
PrettyConsoleTransport(colors=True) # force colors on
PrettyConsoleTransport(colors=False)# force JSON (same as ConsoleTransport)
```

### Custom transports

For full control, extend `Transport` and implement `log(entry)`:

```python
from slpy.transport import Transport

class ElasticsearchTransport(Transport):
    def log(self, entry: dict) -> None:
        self._es_client.index(index='logs', body=entry)
```

For most cases, `AdapterTransport` + `UniversalAdapter` is simpler — no subclassing needed.

Multiple transports are supported — entries are sent to all of them.

### Durable delivery — DurableFileTransport

Fire-and-forget is the right default for `info`/`warn` — and exactly wrong for audit entries a compliance auditor will ask for. `DurableFileTransport` wraps any transport with a durability **buffer** (not an archive):

**When does it write to disk?** Only during an outage — these are the exact conditions:

1. **Happy path (inner transport works):** entries go straight through. **Nothing touches disk.**
2. **The inner transport raises:** the entry is appended to the spool file (JSONL, order preserved). Every following entry is spooled too.
3. **Each new log probes recovery:** when the inner transport accepts entries again, the backlog drains in order.
4. **Backlog fully drained:** the spool file **deletes itself**. No rotation, no archive, no cleanup to maintain.
5. **Process crash/restart during an outage:** the leftover spool is recovered when the transport is constructed — delivery resumes automatically.

```python
from slpy import slpy, AdapterTransport, DurableFileTransport, UniversalAdapter

durable = DurableFileTransport(
    inner=AdapterTransport(
        name='audit',
        # Idempotent executor: at-least-once delivery means a crash
        # mid-delivery re-sends — upsert by a unique id you control.
        adapter=UniversalAdapter(executor=lambda e: audit_store.upsert(e['event_id'], e)),
    ),
    spool_path='/var/log/app/audit-spool.jsonl',   # LOCAL disk — the net, not the destination
)

await slpy.init({'logger': {'transports': [durable]}})
slpy.get_logger('payments').with_retention('SOX_AUDIT_TRAIL').audit(
    'Card charged', event_id='evt-1', order_id='o-1',
)
```

Same design as sl4n's `DurableFileTransport` and the spirit of SyntropyLog's `DurableAdapterTransport` + `persistPath`.

---

## Self-observability and the safety boundary

The pipeline survives every failure silently (a logging framework must never crash your app). `get_stats()` is how you **see** those survivals — read it from a health endpoint:

```python
stats = slpy.get_stats()
stats.logs_processed      # entries emitted
stats.transport_failures  # transport.log() raised (isolated, healthy sinks unaffected)
stats.masking_failures    # masking failed (safe payload emitted instead)
stats.uptime_seconds
stats.native_active       # True when the Rust masking engine is in use
```

Hooks, for when counters aren't enough — both are guarded (a broken hook can't break logging):

```python
await slpy.init({
    'logger':  {'on_log_failure': lambda exc, transport: alert(exc)},
    'masking': {'on_masking_error': lambda exc: alert(exc)},   # never receives the raw payload
})
```

**Log-injection defense:** ANSI escape sequences and control characters are stripped from every string value before transports — a crafted `user_agent` can't fake a log line, clear an operator's terminal, or smuggle escape codes into a log viewer.

---

## Testing your code

`slpy.testing.SpyTransport` captures every emitted entry — including masking output — so tests assert on what would actually leave the process:

```python
from slpy.testing import SpyTransport

spy = SpyTransport()
await slpy.init({'logger': {'transports': [spy]}})

...exercise your code...

assert spy.count == 2
assert spy.last_entry['level'] == 'audit'
assert spy.at_level('error') == []
assert spy.with_field('order_id', 'o-1')
assert spy.any_message_contains('info', 'charged')
assert spy.first_entry['password'] == '*******'   # masking already applied
spy.clear()
```

---

## Performance

slpy includes an optional Rust addon (`slpy-native`) that accelerates the masking engine. When installed, it is used automatically with no code changes.

```
Simple log             Complex object + masking
---------------------  ------------------------------------
slpy        6.2 µs  ①  structlog      10.8 µs  (no masking)
structlog   8.0 µs     slpy           18.0 µs  ② ✅ masking ON
logging    18.8 µs     logging        20.4 µs  (no masking)
loguru     58.9 µs     loguru         61.8 µs  (no masking)
```

> pyperf, null transport, Windows 11 local — numbers above are conservative.

**slpy is the fastest structured logger on simple logs** — faster than structlog, which is the Python performance reference.

**slpy with masking fully active is faster than the stdlib `logging` module without masking.** It is 3.4x faster than loguru without masking.

The Rust addon reduced masking overhead from 29 µs to 12 µs (59% improvement). If the addon is not installed, slpy falls back to the pure Python engine transparently.

### Sustained throughput — official results (GitHub Actions, Ubuntu, Python 3.12)

| Scenario | logs/sec | µs/log | degradation |
|----------|----------|--------|-------------|
| Simple log | **85,774** | 11.7 | — |
| MaskingEngine only | **59,369** | 16.8 | — |
| child() + log | **58,165** | 17.2 | 0 B heap |
| Complex log + masking | **33,472** | 29.9 | — |
| Async context scope | **22,237** | 45.0 | none (1M → 10M: 44.97 → 44.76 µs) |

Zero degradation across all scenarios. `child()` and async context scope allocate **0 bytes** at sustained volume — no GC pressure regardless of call volume.

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
pip install slpy-log

# With FastAPI middleware
pip install slpy-log[fastapi]

# Development
pip install slpy-log[dev]
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

# PrettyConsoleTransport — colored output (run in a real terminal)
py examples/07_pretty_console.py

# AdapterTransport + UniversalAdapter — fanout to multiple destinations
py examples/08_adapter_transport.py

# Observability layer — outbound event tracing
py examples/09_observability.py
```

## Running the tests

```bash
pip install slpy-log[dev]
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
