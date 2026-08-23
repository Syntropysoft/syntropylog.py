<p align="center">
  <img src="https://syntropysoft.com/syntropylog-logo.png" alt="SyntropyLog Logo" width="170"/>
</p>

<h1 align="center">slpy</h1>

<p align="center">
  <strong>The declarative observability framework for Python — the Python member of the SyntropyLog family.</strong>
  <br />
  Correlation IDs, PII masking by field name, per-level field control and retention — declared <strong>once</strong> at <code>init()</code> and enforced on every log, with an optional <strong>Rust masking engine</strong> (transparent pure-Python fallback). <strong>Failsafe by design:</strong> logging can never crash your app — and audit entries can survive backend outages <strong>and process restarts</strong>.
</p>

<p align="center">
  <a href="https://pypi.org/project/slpy-log/"><img src="https://img.shields.io/pypi/v/slpy-log.svg" alt="PyPI Version"></a>
  <a href="https://github.com/Syntropysoft/syntropylog.py/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.7+-blue.svg" alt="Python 3.7+"></a>
  <a href="#"><img src="https://img.shields.io/badge/dependencies-zero-brightgreen.svg" alt="Zero dependencies"></a>
</p>

<p align="center">
  slpy is the Python implementation of <a href="https://www.npmjs.com/package/syntropylog"><strong>SyntropyLog</strong></a> — the reference implementation for Node.js. The same declarative model exists for <strong>.NET</strong> as <a href="https://www.nuget.org/packages/sl4n/"><strong>sl4n</strong></a>, built on <code>Microsoft.Extensions.Logging</code>. Same concepts everywhere — Logging Matrix, masking by field name, retention, durable delivery — each implemented idiomatically for its runtime.
</p>

---

## What's new

- **Faster — masking in the Python engine is 3.3x faster (5,576 → 1,697 ns/op).** Field *names* repeat across log entries while values change, yet every key was re-scanned against every rule regex on every log. The engine now caches the *decision* per key name (bounded, cap 4096, invalidated on `add_rule`) — never the value. Masked output is byte-for-byte identical, nested keys included. A family fix: found by the Java port's JMH suite, applied to SyntropyLog (JS) and slpy the same day.
- **Hardened — explosive custom key patterns are rejected at rule construction.** CPython's `re` cannot be interrupted mid-match, and the 256-char key cap alone does not bound a nested quantifier (measured: `(a+)+$` hangs at 40 chars). `MaskingRule` now fails fast with a clear error on such patterns; safe patterns and default rules are unaffected. The Rust engine (linear-time `regex` crate) was already immune by construction.

Details: [CHANGELOG.md](CHANGELOG.md).

---

## Quick start

```bash
pip install slpy-log
```

```python
import asyncio
from slpy import slpy

async def main():
    # 1. Configure once — this is all you need.
    await slpy.init({'logger': {'level': 'info'}, 'masking': {'enable_default_rules': True}})

    # 2. Log. Sensitive fields are masked automatically, before any transport.
    logger = slpy.get_logger('payments')
    async with slpy.context(request_id='req-001'):
        logger.info('Card charged', email='john@example.com', password='hunter2', amount=299.90)

    await slpy.shutdown()

asyncio.run(main())
```

What lands on the console (structured JSON — this is the real output):

```json
{"level":"info","message":"Card charged","timestamp":"2026-07-09T15:14:14.929+00:00","service":"payments","request_id":"req-001","email":"j***@example.com","password":"[REDACTED]","amount":299.9}
```

The `request_id` propagated automatically. The `email` and `password` were masked automatically. The `service` field appeared automatically. You wrote none of that explicitly — and this is the **default behavior**, not magic. From here everything is configurable: masking rules, which context fields each level emits, where logs go, retention. The sections below are how.

> **Masking is by field name.** A field whose *key* matches a rule is masked; text you put in the message itself passes through untouched. So pass sensitive data as **keyword fields** — `logger.info('msg', email=email)` — not interpolated into the message string. **Log-data quality is the caller's responsibility:** masking enforces your rules on keyed fields — it can't find PII you hide in prose.

---

## What slpy is

> **Not a logger — an observability pipeline.** With `logging`, `structlog` or `loguru` you wire correlation IDs, PII redaction, and per-level field control yourself, in every service. slpy does it for you: declare it **once** in `init()`, and it runs on every log call, in every coroutine, across every service — before the entry ever reaches the **console, your database, Elasticsearch, Datadog, or wherever your `executor` sends it.**

Every Python team building services ends up writing the same boilerplate: thread `request_id` through every function signature, scrub `password` before logging, remember `extra={"service": ...}` on every call, repeat the same middleware in every service.

slpy solves that **declaratively**. You declare the rules once at startup; the framework applies them consistently on every log call, in every coroutine, across every service.

It is scoped on purpose: slpy owns the **log pipeline up to the moment of persistence** — matrix filtering, context propagation, masking, sanitization, retention metadata. **It does not manage any backend** (no database, HTTP or broker clients in the core). Where the entry goes is a one-function `executor` you write. That keeps the framework independent of client-library versions and storage churn.

Four pillars:

- **Logging Matrix** — a declarative whitelist of context fields per log level. If a field isn't in the matrix for that level, it never reaches a transport. Field control by config, not by code review.
- **Retention-aware audit trail with delivery guarantees** — `with_retention(...)` travels with each entry so your transport routes it by policy. `DurableFileTransport` adds a self-emptying disk spool so audit entries survive backend outages and process restarts.
- **Universal Adapter** — one `executor` function sends logs to Postgres, Mongo, Elasticsearch, S3, anything. You write the executor; the framework stays agnostic of client libraries.
- **Silent Observer pipeline** — masking with a safe-payload fallback, ANSI/control-char sanitization, per-transport failure isolation. Logging cannot crash your app; failures surface through hooks and counters (`get_stats()`).

An optional Rust engine (`slpy-native`) accelerates masking when installed, with a transparent pure-Python fallback when not — **same rules, same output, locked by a shared parity test**.

---

## How it compares to logging, structlog & loguru

`logging`, `structlog` and `loguru` are loggers. slpy is a different category — an **observability pipeline** that does *in the framework* what a logger leaves to you:

| | logging / structlog / loguru | slpy |
|---|---|---|
| **Category** | logger | observability pipeline (matrix → masking → sanitization → routing) |
| **PII masking** | bring your own processors | built in, by field name, at any depth — optional **Rust engine** |
| **Correlation IDs** | you thread them, per service | automatic via `contextvars`, declared once |
| **Per-level field control** | manual | declarative **Logging Matrix** |
| **Retention / audit routing** | DIY | first-class — `with_retention` + a restart-surviving durable transport |
| **If logging throws** | can bubble into your code | **Silent Observer** — logging never throws, can't crash your app |

**On speed — honestly:** the only apples-to-apples comparison is *minimal logging* (no masking), and there slpy is competitive — see the measured numbers in [Performance](#performance). With masking fully active slpy still beats stdlib `logging` without masking, but structlog/loguru numbers are a no-masking reference, not a race: they don't mask, correlate or filter.

---

## The declarative shift

With a logger, you **write logging**. With slpy, you **declare observability**.

| Instead of… | You declare… | slpy does automatically |
|---|---|---|
| Threading `request_id` through every function | `async with slpy.context(request_id=id)` | Propagates to all logs in scope via `contextvars` |
| Scrubbing sensitive fields before logging | `masking: {'enable_default_rules': True}` | Masks email, password, token, card, SSN, phone on every log |
| Repeating `extra={"service": "payments"}` | `slpy.get_logger('payments')` | `service` on every log from that logger |
| Copying context into child functions | `logger.child(order_id='123')` | Bindings carried on every subsequent call |
| Filtering noisy context per level | `logging_matrix: {'info': [...], 'error': ['*']}` | Only whitelisted context fields reach a transport at each level |
| Routing compliance logs manually | `logger.with_retention('SOX_AUDIT_TRAIL')` | `retention` / `retention_class` / `retention_days` stamped on every entry |
| Writing a transport class per destination | `AdapterTransport` + `UniversalAdapter` | Your `executor` receives the clean entry — connect to anything |
| Building headers per downstream target | `context.outbound: {'kafka': {...}}` | `get_propagation_headers('kafka')` returns the right wire names |

---

## Logging Matrix — the differentiator

A declarative whitelist deciding **which context fields appear at each log level**. A context field not whitelisted for a level never reaches a transport. Compliance reviews the matrix, not your codebase.

```python
await slpy.init({
    'logging_matrix': {
        'default': ['request_id'],                        # any level not listed
        'info':    ['request_id', 'user_id', 'operation'],
        'error':   ['*'],                                 # '*' = every context field
    },
})

async with slpy.context(request_id='req-7', user_id='u-1', tenant_id='acme'):
    logger.info('Payment captured')
    # → request_id, user_id  (tenant_id dropped — not in the info whitelist)
    logger.error('Payment failed')
    # → request_id, user_id, tenant_id  ('*' lets everything through)
```

**The matrix governs context, not per-call data.** Core fields (`level`, `message`, `service`, `timestamp`), `child()` bindings and per-call kwargs are always emitted (and masked) — if you don't want a per-call field logged, don't pass it. The matrix exists for the auto-propagating context you *can't* trim at each call site.

The exact rules (identical across SyntropyLog, sl4n and slpy):

1. No `logging_matrix` configured → every context field passes (nothing changes).
2. Level listed → only those fields pass.
3. Level not listed → the `default` entry applies.
4. Neither the level nor `default` exist → **all context is dropped** for that level. Strict whitelist — always define `default`.
5. A list containing `'*'` → every context field passes at that level.

Change it at runtime — no restart. Security boundary: only context-field visibility changes; masking, levels and transports stay as set at `init()`:

```python
slpy.reconfigure_logging_matrix({'default': ['request_id'], 'error': ['*']})
```

---

## Named loggers and the fluent API

Each component gets its own named logger. `child()` binds context once — every log from that instance carries it automatically. Bindings are immutable and composable; `child()` never mutates the parent.

```python
logger = slpy.get_logger('order-service').child(order_id=order_id, user_id=user_id)

logger.info('Processing')                          # carries order_id, user_id
logger.info('Calculated', total=299.90, items=3)   # carries order_id, user_id

payment = logger.child(step='payment')             # adds step, keeps the rest
payment.info('Charging card')
```

| Builder | Binds to every log | Notes |
|---|---|---|
| `get_logger('name')` | `service: 'name'` | cached singleton per name |
| `child(**fields)` | the given fields | immutable, composable |
| `with_meta(payload)` | `meta: {...}` | free-form structured metadata |
| `with_retention(name \| dict)` | `retention` fields | registry lookup by name, or inline `{'days','class'}` |

`audit(...)` always emits, regardless of the configured level — use it for compliance events:

```python
await slpy.init({'logger': {'level': 'error'}})
logger.info('hidden')    # not emitted
logger.audit('visible')  # always emitted
```

---

## Context propagation

slpy uses Python's native `contextvars` — the same mechanism as `AsyncLocalStorage` in Node.js. Context propagates correctly across `asyncio.gather()`, `asyncio.create_task()`, and thread-pool executors. Concurrent requests are fully isolated.

```python
async def handle_request(request_id: str, user_id: str) -> None:
    async with slpy.context(request_id=request_id, user_id=user_id):
        logger.info('Request received')            # request_id, user_id here
        await fetch_from_db()                      # ...and here, no arguments threaded

async def fetch_from_db() -> None:
    logger.debug('Running query')                  # request_id, user_id propagated
```

### FastAPI / ASGI middleware

One line wires automatic context extraction into every request (`pip install slpy-log[fastapi]`). Declare which inbound headers map to which conceptual fields, per source, and which wire names each outbound target uses:

```python
'context': {
    'inbound':  {'http': {'request_id': 'X-Request-ID'}},
    'outbound': {
        'http':  {'request_id': 'X-Request-ID'},      # default target
        'kafka': {'request_id': 'requestId'},
    },
}
```

### Propagation headers

`get_propagation_headers(target)` returns the current context translated to the wire names of that target — HTTP headers, Kafka headers, S3 metadata, anything:

```python
await httpx.get(url, headers=slpy.get_propagation_headers())        # http names
await kafka.send(topic, headers=slpy.get_propagation_headers('kafka'))
```

Every call also emits an `OutboundEvent` on a separate observability channel (never masked, own transports) — a traceability record of what context left the service, to which target, and when. Route it to Jaeger, Datadog, or disable with `'observability': {'enabled': False}`.

---

## Data masking

Masking runs automatically on every entry before it reaches any transport — **identically in the Rust engine and the Python fallback** (one rule set, asserted equal by a shared parity test). Rules match **field names** at any depth; once a key matches, everything beneath it is masked — nested dicts, lists, and non-string scalars included.

> **Masking matches the field _name_, not the content.** It masks the value of fields whose key matches a rule; it does **not** scan free-text strings or the log message for PII. Put sensitive data in keyed fields — **log-data quality is the caller's responsibility.**

```python
await slpy.init({
    'masking': {
        'enable_default_rules': True,   # email, password, token, card, SSN, phone
        'rules': [
            {'pattern': r'internal_code', 'strategy': 'token'},   # your own, on top
        ],
    },
})

logger.info('Payment', card_number='4111-1111-1111-1234', amount=299.90)
# → card_number: "************1234"   amount: 299.9 (numbers untouched)

logger.info('Order', order={'user': {'token': 'abc123', 'id': 'USR-1'}})
# → order.user.token: "[REDACTED]"   order.user.id: "USR-1" (not a sensitive key)

# Non-strings and nested structures under a sensitive key are masked too:
logger.info('Login', password=12345)             # → password: "[REDACTED]"
logger.info('Auth', password={'hash': 'abc'})    # → password.hash: "[REDACTED]"
```

**Identifiers keep their last digits (debuggable); credentials are fully redacted.** Real outputs from the default rules:

| Field key (examples) | Input | Result |
|---|---|---|
| `email`, `mail` | `john@example.com` | `j***@example.com` |
| `password`, `pass`, `pwd`, `secret` | `hunter2` | `[REDACTED]` |
| `token`, `key`, `auth`, `jwt`, `bearer`, `api_key` | `abc123xyz` | `[REDACTED]` |
| `credit_card`, `card_number`, `creditCardNumber` | `4111-1111-1111-1234` | `****-****-****-1234` |
| `ssn`, `social_security`, `ssn_number` | `123-45-6789` | `***-**-6789` |
| `phone`, `mobile`, `tel`, `phone_number` | `+1 (555) 123-4567` | `+* (***) ***-4567` |

Identifiers keep their separators: the format is what makes a masked value readable in a log, and
the last four digits are not the secret. Credentials get no partial and no length — a
length-preserving password mask publishes how long the password is, so `mask_char` is ignored for
`password` and `token`.

Every one of these comes from a `MaskSpec`, and the mapping from strategy to spec is
`strategy_to_spec()`. The masking primitive is shared across the whole family: slpy asserts the
same `mask-parity-cases.json` fixture as SyntropyLog (Node), its Rust addon and the JVM port, so a
card masked here reads exactly like a card masked there. Write your own as data:

```python
from slpy import MaskSpec, MaskingRule, MaskingStrategy

MaskingRule(
    pattern=r'^cuit$',
    strategy=MaskingStrategy.CUSTOM,
    spec=MaskSpec(scope='digits', unmask_end=1),   # 20-12345678-9 → **-********-9
)
```

A `spec` crosses into the Rust engine as data. A `custom_mask` callable cannot, and keeps that
rule on the Python engine.

The default rules are deliberately **greedy** — a field name that *contains* a sensitive word is masked (`user_password`, `sessionKey`). Better to over-mask than to leak. For precise custom rules, build anchored patterns from the grouped aliases (no string literals — keeps secret scanners like Sonar quiet):

```python
from slpy import MASK_KEYS, mask_pattern

'masking': {
    'rules': [
        {'pattern': mask_pattern(*MASK_KEYS['token']), 'strategy': 'token'},   # ^(token|key|auth|jwt|bearer)$
    ],
}
```

**One sink can be exempt: the audit ledger.** Masking runs once, before the transport loop, so
every sink gets the same redacted entry — right for consoles and APMs, wrong for the compliance
ledger, where `j***@example.com` proves nothing.

```python
audit = AdapterTransport(name='audit-journal', adapter=UniversalAdapter(executor=to_ledger))

await slpy.init({
    'logger':  {'transports': [ConsoleTransport(), audit]},
    'masking': {'exempt_transports': ['audit-journal']},
})
# console      → email: "j***@example.com"
# audit-journal → email: "john@example.com"
```

A transport is addressed by its `name`, or by its class name when it has none. The exemption is
**declared in app config, never by a transport about itself** — the check lives in the logger,
where the sink's identity is known. An unknown name raises `UnknownExemptTransportError` at
`init()`: exempting a transport removes masking from it, so a typo would leave the audit sink
masked, silently, exactly where the truth was required. Forgetting the key masks the sink, which
errs safe.

It skips masking and **nothing else**. The Logging Matrix already decided which context fields
exist, and the sanitizer still runs — a forged log line is a forged log line whether or not the
values are masked. Both are pinned by test. Cost when unused is zero: the second entry is built
only if a sink is declared exempt.

**Failsafe.** Masking never throws. If it fails, the failure is counted (`get_stats().masking_failures`), reported through the optional `masking.on_masking_error` hook (which never receives the raw payload), and the entry degrades to a safe payload — `level`/`timestamp`/`message`/`service` plus `_masking_failed: True`. **The raw metadata never leaks.** Rules only ever run against field names (capped at 256 chars), never values — bounded input, bounded regex evaluation.

---

## Compliance routing — retention as data

Declare named policies once; tag loggers with `with_retention(name)`; every tagged entry carries the policy so your transport routes and expires it by rule. slpy attaches the metadata — storage and expiry are the transport's job.

```python
await slpy.init({
    'retention_policies': {
        'SOX_AUDIT_TRAIL': {'years': 7,  'class': 'SOX'},
        'BCRA_A7724':      {'months': 42, 'class': 'BCRA'},
        'GDPR_ACCESS':     {'days': 90,  'class': 'GDPR'},
    },
})

audit = slpy.get_logger('payments').with_retention('SOX_AUDIT_TRAIL')
audit.audit('Manager override', user_id='u-1')
# → retention: "SOX_AUDIT_TRAIL"  retention_class: "SOX"  retention_until: "2033-08-23"
```

**`retention_until` is the point.** The date the mandatory window ends, materialized when the entry
is written, so a sweep is an indexable range scan — `WHERE retention_until < CURRENT_DATE` — instead
of a policy interpretation. It also means a record filed under an older revision of a policy keeps
the window that was in force when it was written. It is **not** an expiry: reaching it ends the
obligation, it does not authorize deletion.

**Declare exactly one unit,** and prefer the calendar one. `days` is exact but drifts: `2555` is
7 × 365, misses two leap days, and ends the window two days before seven actual years. A policy
declaring more than one unit **refuses to start** — an ambiguous compliance window has no safe
default, and a host that will not boot beats records swept on a date nobody chose.

**The rounding errs long, never short.** 31-Jan plus one month has no 31-Feb to land on, so it rolls
forward to 3-Mar rather than clamping back to 28-Feb; 29-Feb plus a year lands on 1-Mar. Ending a
window early is the failure an auditor punishes; a record kept a day too long costs storage.

- The stamped fields are **never filtered by the Logging Matrix** — they are bindings, not context.
  `retention_until` is written per entry, after your kwargs: a caller cannot hand-write the date a
  compliance sweep will read.
- **An unregistered name raises** `RetentionPolicyNotFoundError`, with the registered names listed.
  It raises from `with_retention()` — where you build the logger, once — never from a log call:
  logging still cannot throw. A typo that travelled silently would be a record with no retention at
  all, found at audit time.
- Lookup is case-insensitive, but the field always carries the **registered spelling**. Downstream
  matches an exact string, so one policy must not arrive as `SOX_AUDIT` on some records and
  `sox_audit` on others.
- Inline policies work without a registry entry: `with_retention({'months': 6, 'class': 'PCI'})`.
  They have no name to route on, so nothing lands in `retention` — the window is still computed.
- Composes with the rest of the fluent API: `logger.child(...).with_retention(...).with_meta(...)`.

**Resolving outside the logger** — for a domain write path that persists retention in its own
column, and needs the same answer the log gets:

```python
registry = slpy._retention                       # or build your own RetentionRegistry
registry.policies                                # every policy, frozen, by canonical name
registry.resolve('SOX_AUDIT_TRAIL')              # the policy, or None
registry.require('SOX_AUDIT_TRAIL')              # the policy, or RetentionPolicyNotFoundError
registry.until('SOX_AUDIT_TRAIL', written_at)    # the same date the logger stamps

from slpy import retention_until                 # the pure function underneath
retention_until(date(2026, 1, 31), RetentionPolicy(months=1))   # → date(2026, 3, 3)
```

The registry is frozen: it copies on construction and hands out a read-only view, so neither the
dict you passed in nor the view you get back can redefine a window for records already written
under the old one.

Pair it with `DurableFileTransport` (below) so tagged entries are also *delivered* with guarantees.

---

## Transports

| Transport | Output | Use case |
|---|---|---|
| `ConsoleTransport` | Structured JSON | Production, CI, log collectors — **default** |
| `PrettyConsoleTransport` | Colored human-readable | Local development (auto-falls back to JSON when stdout is not a TTY) |
| `AdapterTransport` | Any destination | Databases, HTTP APIs, queues, fanout |
| `DurableFileTransport` | Wraps any of the above | Audit logs that must survive outages and restarts |

### AdapterTransport + UniversalAdapter

You provide one `executor` function — sync or async — that receives the clean, already-masked entry and sends it anywhere. slpy handles context, masking, level filtering, and error isolation.

```python
from slpy import slpy, AdapterTransport, UniversalAdapter, ConsoleTransport

async def my_executor(data: dict) -> None:
    await asyncio.gather(
        prisma.system_log.create(data=data),
        es.index(index='logs', body=data),
    )

db_transport = AdapterTransport(
    name='db',
    adapter=UniversalAdapter(executor=my_executor),
    # Optional formatter — adapt the entry to your schema:
    formatter=lambda e: {**e, 'timestamp': datetime.fromisoformat(e['timestamp'])},
)

await slpy.init({'logger': {'transports': [db_transport, ConsoleTransport()]}})
```

For full control, extend `Transport` and implement `log(entry)`. Multiple transports are supported — entries are sent to all of them, each isolated from the others' failures.

### Durable delivery — DurableFileTransport

Fire-and-forget is the right default for `info`/`warn` — and exactly wrong for audit entries an auditor will ask for. `DurableFileTransport` wraps any transport with a durability **buffer** (not an archive).

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

Same design as sl4n's `DurableFileTransport`, same goal as SyntropyLog's `DurableAdapterTransport` + `persistPath`.

---

## Testing your code

`slpy.testing.SpyTransport` captures every emitted entry — **including masking output** — so tests assert on what would actually leave the process:

```python
from slpy.testing import SpyTransport

spy = SpyTransport()
await slpy.init({'logger': {'transports': [spy]}})

# ...exercise your code...

assert spy.count == 2
assert spy.last_entry['level'] == 'audit'
assert spy.at_level('error') == []
assert spy.with_field('order_id', 'o-1')
assert spy.any_message_contains('info', 'charged')
assert spy.first_entry['password'] == '*******'   # masking already applied
spy.clear()
```

---

## Self-observability and the safety boundary

The pipeline survives every failure silently — a logging framework must never crash your app. `get_stats()` is how you **see** those survivals; read it from a health endpoint:

```python
stats = slpy.get_stats()
stats.logs_processed      # entries emitted
stats.transport_failures  # transport.log() raised (isolated — healthy sinks unaffected)
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

Runtime changes without restart: `slpy.set_level('debug')` and `slpy.reconfigure_logging_matrix({...})`.

---

## Native engine (Rust)

The optional `slpy-native` addon runs the masking engine in Rust. When installed it is used automatically — no code change; when absent, the pure-Python engine runs the **exact same semantics**. The two engines are locked together by a shared parity fixture (`tests/test_masking_parity.py`) asserting byte-identical output — the regression lock the family adopted after a native/JS divergence in the Node.js sibling leaked PII (its KNOWN-ISSUES #2).

- Rules with a `custom_mask` Python callable can't cross into Rust — the engine transparently stays in Python (parity over speed).
- Disable explicitly with the environment variable `SLPY_NATIVE_DISABLE=1`.
- `slpy.get_stats().native_active` tells you which engine is running.

---

## Performance

Honest framing first: the numbers below compare slpy against loggers that **don't mask, correlate or filter** — their columns are a no-masking reference, not a race.

```
Simple log             Complex object + masking
---------------------  ------------------------------------
slpy        6.2 µs  ①  structlog      10.8 µs  (no masking)
structlog   8.0 µs     slpy           18.0 µs  ② ✅ masking ON
logging    18.8 µs     logging        20.4 µs  (no masking)
loguru     58.9 µs     loguru         61.8 µs  (no masking)
```

> pyperf, null transport, Windows 11 local — conservative numbers.

- On simple logs slpy is the fastest structured logger measured — faster than structlog, the Python performance reference.
- With masking **fully active**, slpy is still faster than stdlib `logging` without masking.
- The Rust addon reduced masking overhead from 29 µs to 12 µs. Without it, the pure-Python engine runs transparently.

Sustained throughput (GitHub Actions, Ubuntu, Python 3.12): 85k logs/sec simple, 33k logs/sec complex+masking, zero degradation from 1M to 10M calls, 0 B heap growth on `child()` and context scopes. Full methodology and reproduction: [benchmark/README.md](benchmark/README.md).

---

## What slpy is not

slpy is a structured logging and context propagation framework. It is not:

- A log aggregation backend (use Elasticsearch, Loki, CloudWatch)
- A distributed tracing system (use OpenTelemetry)
- A metrics collector (use Prometheus, Datadog)

It is the component that makes every log line correct, consistent, and safe before it reaches any of those systems.

---

## Security & supply chain

- **No network I/O at runtime.** slpy contacts no external URLs; the only output is what your transports produce.
- **Zero runtime dependencies.** The core package has no `install_requires`. The optional `[fastapi]` extra adds only `starlette` (already a FastAPI dependency).
- **Log-injection boundary** built in (ANSI/control-char stripping).
- **Masking failsafe** — a masking failure yields a safe payload, never the raw metadata.
- `custom_mask` functions in masking rules are consumer-supplied configuration, not influenced by external input.
- **Both dependency trees are audited on every push and pull request** — `pip-audit` over the
  third-party Python set and `cargo audit` over `slpy-native/Cargo.lock`, which is where the real
  surface is: the core ships zero runtime dependencies, and the addon pulls pyo3 and regex.
  Dependabot files the upgrade PRs weekly; the audit job blocks a merge in between.
- **Custom key patterns are ReDoS-checked when the rule is built**, not on the logging path.
  CPython's `re` cannot be interrupted mid-match, so an explosive pattern is rejected before it can
  ever run — a nested quantifier like `(a+)+$` hangs at 40 characters and the 256-char key cap does
  not bound it. `slpy-native` uses Rust's linear-time `regex` and is immune by construction.

---

## What's in the box

| Feature | One-liner | Where |
|---|---|---|
| **Logging Matrix** | Whitelist of context fields per level; `'*'` wildcard, `default` fallback, runtime reconfigure | `logging_matrix` config |
| **MaskingEngine** | By field name at any depth; non-strings and nested values under a sensitive key included; `MASK_KEYS` + `mask_pattern()` | `masking` config |
| **Native engine (Rust)** | Same semantics as Python, parity-locked; auto-detected | `pip install slpy-native` |
| **Universal Adapter** | One `executor` → any backend | `AdapterTransport` + `UniversalAdapter` |
| **DurableFileTransport** | Self-emptying disk spool; survives outages and restarts; at-least-once | `slpy.durable` |
| **Retention policies** | Named compliance policies stamped per entry, matrix-proof | `retention_policies` config + `with_retention()` |
| **Fluent API** | `child`, `with_meta`, `with_retention`; `audit` level always emits | `Logger` |
| **Context propagation** | `contextvars` scopes; per-source inbound / per-target outbound wire names | `slpy.context()` / `context` config |
| **FastAPI / ASGI** | One-line middleware extracts declared headers into context | `slpy-log[fastapi]` |
| **Observability channel** | `OutboundEvent` on every `get_propagation_headers()` — separate transports, never masked | `observability` config |
| **Safety boundary** | ANSI/control-char stripping; per-transport isolation; guarded hooks | built in |
| **Self-observability** | `get_stats()` — processed/failure counters, uptime, engine in use | `slpy.get_stats()` |
| **Testing toolkit** | `SpyTransport` — assert on emitted, masked entries | `slpy.testing` |

---

## Working on slpy

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,fastapi]' httpx maturin
.venv/bin/maturin build --release -m slpy-native/Cargo.toml -i .venv/bin/python
.venv/bin/pip install --force-reinstall slpy-native/target/wheels/*.whl
git config core.hooksPath .githooks
```

`pytest` alone is not the full gate. Without the optional dependencies the suite reports
`skipped` for the fourteen tests that compare the Rust and Python masking engines — the ones that
exist to catch the two engines drifting apart — plus the FastAPI middleware. With everything
installed there are **no skips**, and that is what CI enforces.

The hooks run the same gate before a commit lands, and catch one thing CI would only catch later:
if you edit `slpy-native/src` and do not rebuild, the suite still passes — against the previous
wheel. The parity tests would be asserting the old binary while your change looks verified.

| | pre-commit |
| :-- | :-- |
| on `main` | refuses (`SLPY_ALLOW_MAIN=1` to override) |
| always | `ruff check` — F (pyflakes) and E9 only, no style |
| `slpy-native/src` staged | `cargo check`, then refuses if the installed wheel is older than the source |
| always | the suite, and it names which optional dependency is missing rather than passing quietly |

CI adds two layers the hook does not: the suite on 3.9 → 3.13 and on the 3.7 floor, and an audit
of both dependency trees (`pip-audit` over the third-party set, `cargo audit` over the addon's
lockfile).

Set `SLPY_PYTHON` if your environment is somewhere other than `.venv`.

---

## Documentation & examples

- **[Data masking](docs/data_masking.md)** · **[Logging matrix](docs/logger_matrix.md)** · **[Lifecycle](docs/lifecycle.md)** · **[Architecture & design decisions](docs/slpy-refactor-plan.md)**
- **Runnable examples** (`examples/01`–`09`): basic setup, named loggers + `child()`, context propagation, masking, `with_meta` + audit, FastAPI middleware, pretty console, adapter transport fanout, observability events.
- **The family:** [SyntropyLog (Node.js)](https://www.npmjs.com/package/syntropylog) — the reference implementation · [sl4n (.NET)](https://www.nuget.org/packages/sl4n/)

```bash
git clone https://github.com/Syntropysoft/syntropylog.py
cd syntropylog.py
python examples/01_basic_setup.py
```

Tests: `pip install slpy-log[dev] && pytest`

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
