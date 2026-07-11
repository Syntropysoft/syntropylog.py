# Changelog

All notable changes to slpy are documented here.

---

## [Unreleased]

### Performance

- **Masking is 3.3x faster in the Python engine (5,576 → 1,697 ns/op) via a bounded
  per-key-name decision cache.** Field names repeat across log entries while values change,
  yet `_find_rule` re-scanned every rule regex per key on every log. The engine now caches
  the *decision* (truncated key name → rule-or-none), never the value. Safety properties:
  bounded at 4096 entries (hostile payloads generating unique key names cannot grow memory —
  past the cap, new keys still mask correctly, uncached); invalidated on `add_rule()` (a name
  cached as "no rule" is re-evaluated); deterministic by construction (keyed on the same
  truncated name the scan matches against); covers nested keys (the walk consults it at every
  depth). Masked output is byte-for-byte identical — shared parity fixture still green.
  `MaskingEngine.decision_cache_size` exposes it. The Rust engine is unaffected (it has its
  own hot path); this speeds up the always-available Python fallback and custom-callable mode.
  Family fix: found by the Java port's JMH suite (4,497→1,187 ns/op there), applied to
  SyntropyLog (JS, 442→183 ns/op) and slpy the same day.

### Security

- **ReDoS: explosive custom key patterns are rejected at rule construction** (shipped in
  `61b4dcc`, documented here). CPython's `re` has no timeout API and the 256-char key cap does
  NOT bound a nested quantifier — measured: `(a+)+$` hangs at 40 chars. `MaskingRule` now runs
  a static star-height check (`slpy/_regex_safety.py`, mirror of SyntropyLog's
  `regexSafety.ts`) and fails fast on nested unbounded quantifiers and counted repetition of
  unbounded bodies. Default rules and safe custom patterns are unaffected. Residual, pinned by
  test: overlapping alternation (`(a|a)*`) is not statically detectable; slpy-native (Rust
  `regex` crate, linear-time) remains immune by construction.

---

## [1.0.0] — 2026-07-09

**First stable release.** 0.4.0 brought slpy to conceptual parity with its siblings —
[SyntropyLog](https://www.npmjs.com/package/syntropylog) (Node.js, the reference implementation)
and [sl4n](https://www.nuget.org/packages/sl4n/) (.NET); 1.0.0 declares that surface stable.
From here the project adheres to semantic versioning: breaking changes only in major versions.

No API or behavior changes since 0.4.0. (0.4.1 was version-bumped but never published;
its docs-only change ships here.)

### Changed

- Development status: Alpha → **Production/Stable** (PyPI classifiers).
- README family links now point at the published packages only
  ([syntropylog on npm](https://www.npmjs.com/package/syntropylog),
  [sl4n on NuGet](https://www.nuget.org/packages/sl4n/)) — the criterion used across the family.
- Project URLs fixed to the actual repository (`Syntropysoft/syntropylog.py`) — the previous
  links pointed at a repo that does not exist.

---

## [0.4.0] — 2026-07-09

Parity release: slpy now covers the same conceptual surface as its siblings —
SyntropyLog (Node.js) and sl4n (.NET).

### Added

- **Logging Matrix** (`logging_matrix` config + `slpy.reconfigure_logging_matrix()`):
  a per-level whitelist of context fields. `default` fallback, `'*'` wildcard,
  strict-whitelist semantics. Filters only the auto-propagating context — core
  fields, `child()` bindings and per-call kwargs are never filtered.
- **Retention policies** (`retention_policies` config + `logger.with_retention(name)`):
  named compliance policies stamped as `retention` / `retention_class` /
  `retention_days` on every tagged entry. Inline `{'days', 'class'}` dicts work
  without a registry entry; an unregistered name still stamps `retention`.
  Stamps bypass the Logging Matrix (they are bindings, not context).
- **DurableFileTransport**: wraps any transport with a self-emptying disk spool.
  Happy path never touches disk; an outage spools the undelivered backlog to
  JSONL (order preserved); subsequent logs probe recovery and drain; the file
  deletes itself when drained; a leftover spool is recovered on construction
  (restart survival). Delivery is at-least-once — keep the executor idempotent.
- **Safety boundary**: ANSI escape sequences and control characters are stripped
  from every string value before transports (log-injection defense).
- **`slpy.get_stats()`**: pipeline health counters — `logs_processed`,
  `transport_failures`, `masking_failures`, `uptime_seconds`, `native_active`.
- **Hooks**: `logger.on_log_failure(exc, transport)` and
  `masking.on_masking_error(exc)` — both guarded; a broken hook can't break logging.
- **`MASK_KEYS` + `mask_pattern()`**: grouped sensitive-key aliases for building
  custom rules without string literals (the family's `maskEnum` / `MaskKeys`).
- **Testing toolkit**: `slpy.testing.SpyTransport` — `entries`, `count`,
  `first_entry` / `last_entry`, `clear()`, `at_level()`, `with_field()`,
  `any_message_contains()`. Captures post-masking output.

### Fixed (PII / data-integrity — in BOTH engines, Python and Rust)

- **Non-string values under a sensitive key leaked unmasked** (`password=12345`).
  Now stringified and masked by the matching strategy.
- **Nested structures under a sensitive key leaked unmasked**
  (`password={'hash': ...}`). Rules now inherit down the tree: once a key
  matches, everything beneath it is masked; a deeper matching key overrides.
- **Lists were corrupted to dicts** (`[1,2,3]` → `{'0':1,...}`) by the
  flatten/unflatten round-trip. Both engines are now a pure recursive walk
  that preserves structure.
- **Masking failure no longer returns the raw payload.** On failure the entry
  degrades to a safe payload (`_masking_failed: True` + core fields only).
- **Bare `credit_card` / `ssn` / `phone` field names were not covered** by the
  default rules (they required a `number`/`num`/`id` suffix, so `ssn='123-45-6789'`
  leaked). The defaults now also match the anchored bare aliases — the same
  coverage as sl4n's `MaskingPatterns`, plus the derived forms.
- Native `add_rule` patterns are now case-insensitive, matching Python.
- A shared parity fixture (`tests/test_masking_parity.py`) asserts both engines
  byte-identical — the regression lock against engine drift.

### Changed

- **Timestamps are ISO-8601** with milliseconds and offset
  (`2026-07-09T14:00:00.123+00:00`) — the family format. Previously epoch-ms
  int. `PrettyConsoleTransport` renders both; if your executor/formatter
  parsed the epoch number, switch to `datetime.fromisoformat(entry['timestamp'])`.
- Masking depth is bounded by `masking.max_depth` (default 10, now actually
  enforced). At the boundary, values under a sensitive key are replaced by a
  fixed-width mask; values outside pass unchanged.

---

## [0.3.2] — 2026-03-28

### Breaking changes

- **`context.outbound` is now a flat dict, symmetric with `context.inbound`.**
  The `propagation`/`targets` split inside `outbound` is replaced by a single flat
  dict where each key is a target name — exactly like `inbound` where each key is a
  source name.

  ```python
  # Before (0.3.1)
  'outbound': {
      'propagation': {'correlation_id': 'X-Correlation-ID'},
      'targets': {
          'kafka': {'correlation_id': 'correlationId'},
      },
  }

  # After (0.3.2)
  'outbound': {
      'http':  {'correlation_id': 'X-Correlation-ID'},  # TARGET_HTTP = 'http'
      'kafka': {'correlation_id': 'correlationId'},
  }
  ```

- **`get_propagation_headers()` with no argument uses the `'http'` key** in `outbound`.
  `get_propagation_headers('kafka')` uses the `'kafka'` key. No fallback for unknown
  targets — an unconfigured target returns `{}`.

- **`get_propagation_headers('unknown')` now returns `{}`** instead of using field names
  as keys. If a target is not in `outbound`, nothing is sent to it.

### Philosophy

`inbound` and `outbound` now have identical structure: `{name: {field: wire_name}}`.
One is keyed by source, the other by destination. The internal context is the translation
layer between them. Application code works exclusively with conceptual field names.

The only framework opinion kept: `'http'` is the default target key used when
`get_propagation_headers()` is called with no argument. Define `TARGET_HTTP = 'http'`
in your constants if you want explicit, IDE-friendly usage.

### Testing

- 101 tests, all updated for the new flat `outbound` structure.
- Renamed `test_get_propagation_headers_unknown_target_uses_field_name` →
  `test_get_propagation_headers_unknown_target_returns_empty`.

---

## [0.3.1] — 2026-03-28

### Breaking changes

- **`context.propagation` and `context.targets` moved under `context.outbound`.**
  The flat structure from 0.3.0 is replaced by an explicit `inbound`/`outbound` split.

  ```python
  # Before (0.3.0)
  await slpy.init({
      'context': {
          'propagation': {'correlation_id': 'X-Correlation-ID'},
          'targets': {'kafka': {'correlation_id': 'correlationId'}},
      }
  })

  # After (0.3.1)
  await slpy.init({
      'context': {
          'inbound': {
              'default': {'correlation_id': 'X-Correlation-ID'},
          },
          'outbound': {
              'propagation': {'correlation_id': 'X-Correlation-ID'},
              'targets': {'kafka': {'correlation_id': 'correlationId'}},
          },
      }
  })
  ```

- **`SyntropyMiddleware` now requires a `source` parameter** (default: `"default"`).
  The middleware reads inbound headers from `context.inbound[source]` instead of
  `context.propagation`.

  ```python
  # Before (0.3.0)
  app.add_middleware(SyntropyMiddleware)

  # After (0.3.1) — explicit source
  app.add_middleware(SyntropyMiddleware, source='frontend')
  ```

### New

- **Multi-source inbound mapping.** `context.inbound` is a dict of sources — each source
  declares its own header-name-to-field mapping. A BFF or API gateway that receives traffic
  from multiple origins (frontend, partner API, legacy internal) can declare each source
  separately with different wire names mapping to the same conceptual fields.

  ```python
  'context': {
      'inbound': {
          SOURCE_FRONTEND: {FIELD_CORRELATION: 'X-Correlation-ID'},
          SOURCE_PARTNER:  {FIELD_CORRELATION: 'x-request-id'},
          SOURCE_LEGACY:   {FIELD_CORRELATION: 'correlationid'},
      },
      'outbound': {
          'propagation': {FIELD_CORRELATION: 'X-Correlation-ID'},
      },
  }
  app.add_middleware(SyntropyMiddleware, source=SOURCE_FRONTEND)
  ```

### Philosophy

The inbound/outbound split makes the data flow explicit:
- **`context.inbound`** — what comes in, by source.
- **`context.outbound`** — what goes out, by destination.

Internal context is the translation layer between them. Application code only works with
conceptual field names and never sees wire names directly.

### Testing

- 101 tests (was 99). Added `test_inbound_config` in `test_config.py`.
- All tests updated for the new `inbound`/`outbound` config structure.

---

## [0.3.0] — 2026-03-28

### Breaking changes

- **No built-in propagation defaults.** `context.propagation` is now empty by default.
  In 0.2.0, four fields (`correlation_id`, `trace_id`, `session_id`, `transaction_id`)
  were pre-configured with HTTP header names. Now you declare exactly the fields your
  service needs — nothing is assumed.

  ```python
  # Before (0.2.0) — worked without any propagation config
  # After (0.3.0) — must declare explicitly:
  await slpy.init({
      'context': {
          'propagation': {
              'correlation_id': 'X-Correlation-ID',
          },
      },
  })
  ```

- **`get_correlation_id()`, `get_trace_id()`, `get_session_id()`, `get_transaction_id()` removed.**
  Replaced by the generic `slpy.get(key)` method.

  ```python
  # Before
  slpy.get_correlation_id()

  # After
  slpy.get('correlation_id')
  ```

- **`DEFAULT_PROPAGATION`, `FIELD_CORRELATION`, `FIELD_TRACE`, `FIELD_SESSION`,
  `FIELD_TRANSACTION` removed.** These were framework opinions about naming. slpy provides
  the mechanism — you declare the meaning. Define your own constants if you want IDE
  autocompletion and typo safety (the `FIELD_` prefix in the docs is a suggestion, not
  part of the framework).

### New

- **`slpy.get(key)`** — generic context accessor. Reads any field from the active context
  by its conceptual name. Works with any string key, including your own custom fields.

  ```python
  slpy.get('correlation_id')   # -> 'req-001'
  slpy.get('tenant_id')        # -> 'acme'
  slpy.get('unknown')          # -> None
  ```

### Philosophy

slpy provides the mechanism. You declare the meaning. No built-in opinions about what
fields your service should propagate, what they should be called, or what wire names
they should map to. One declaration in one file — the framework does the rest.

---

## [0.2.0] — 2026-03-28

### Propagation headers

- **`context.propagation`** — declare conceptual field names and their HTTP header names once.
  Default mapping: `correlation_id → X-Correlation-ID`, `trace_id → X-Trace-ID`,
  `session_id → X-Session-ID`, `transaction_id → X-Transaction-ID`.
  Fully overridable per `init()`.

- **`context.targets`** — per-destination key name mapping. Each target (Kafka, S3, Azure,
  gRPC, any protocol) gets its own field naming convention declared in config.
  ```python
  'context': {
      'targets': {
          'kafka': {'correlation_id': 'correlationId', 'trace_id': 'traceId'},
          's3':    {'correlation_id': 'Correlation_ID'},
          'azure': {'correlation_id': 'CorrelationID', 'trace_id': 'TraceID'},
      }
  }
  ```

- **`get_propagation_headers(target=None)`** — returns a dict with the key names for the
  given target, ready to pass directly to any outbound call. No boilerplate per destination.
  ```python
  await httpx.get(url, headers=slpy.get_propagation_headers())
  await kafka.send(topic, headers=slpy.get_propagation_headers("kafka"))
  await s3.put_object(Metadata=slpy.get_propagation_headers("s3"))
  ```
  Only fields that have a value in the current context are included.

- **Context accessors** — new methods on the singleton:
  - `get_correlation_id()` — current `correlation_id` or `None`
  - `get_trace_id()` — current `trace_id` or `None`
  - `get_session_id()` — current `session_id` or `None`
  - `get_transaction_id()` — current `transaction_id` or `None`
  - `get_propagation_header_name(field_name)` — the configured HTTP header name for a field

- **`SyntropyMiddleware` updated** — now reads all fields declared in `context.propagation`
  from inbound headers (not just `correlation_id`). Forwards all propagation headers in
  the response. `correlation_id` is the only field auto-generated when absent.

### Observability layer

A new observability channel, completely separate from the logging pipeline. Tracks what
context left the service, to which target, with which headers, and when. Not logs —
trazability records. Fields are never masked.

- **`OutboundEvent`** — emitted automatically by `get_propagation_headers()` on every call.
  Fields: `target`, `headers`, `correlation_id`, `trace_id`, `timestamp` (epoch ms).
  `to_dict()` returns a serializable dict with `event: "outbound"`.

- **`ObservabilityTransport`** — base class. Implement `emit(event)` to route outbound
  events to any backend: Jaeger, Zipkin, Datadog APM, a custom store, all at once.

- **`ConsoleObservabilityTransport`** — writes outbound events to stdout as structured JSON.
  Default when no observability transport is configured.

- **`ObservabilityEngine`** — fans out to all configured transports. Silent observer —
  a broken transport never propagates errors to the application.

- **`observability.enabled`** — set to `False` to disable the entire observability layer.
  Zero overhead, zero events emitted.

- **Fanout** — multiple `ObservabilityTransport` instances are all invoked per event.
  Connect to Jaeger + Zipkin + a custom store simultaneously with zero extra code.

### FastAPI middleware — breaking change

`SyntropyMiddleware` no longer accepts a `correlation_header` constructor parameter.
Header names are now read from `context.propagation` in the slpy config — declared once,
applied everywhere. Update your init config if you were using a non-default header name.

### Package name

The PyPI package name is **`slpy-log`** (not `slpy`, which was already taken).

```bash
pip install slpy-log
pip install slpy-log[fastapi]
```

The import name is unchanged: `from slpy import slpy`.

### Testing

- 99 tests (was 77). Added:
  - `tests/test_observability.py` — 9 tests covering `OutboundEvent` emission, target naming,
    header mapping, timestamp, `trace_id`, multiple events, disabled mode, silent observer,
    `to_dict()`.
  - `tests/test_fastapi_middleware.py` — 9 tests for the updated middleware.
  - `tests/test_adapter_transport.py` — 11 tests for `AdapterTransport` + `UniversalAdapter`.
- 85% coverage (unchanged — new lines are balanced by new tests).

### Examples

- `09_observability.py` — 5 scenarios: HTTP propagation, multi-target key naming
  (kafka/s3/azure), fanout to 3 simultaneous transports, `to_dict()` serialization,
  disabled mode. All 9 examples run clean via `py run_examples.py`.

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
