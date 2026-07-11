# slpy → SyntropyLog parity roadmap

**Status:** slpy 0.4.0 already sits at family parity for the core pillars (matrix / retention /
durable / safety / testing / canonical masking) — 158 tests green on `develop`. This document
records what a **source audit (2026-07-10**, done while planning the JVM port**)** verified, and
the remaining gaps vs the JS reference, so findings live in a roadmap like every family member
(sl4n and syntropylog-java have the same file).

---

## Where slpy already has parity (verified in source, do NOT re-port)

- **Canonical masking** — data-driven `MaskSpec`/apply, asserts the shared 17-case
  `mask-parity-cases.json` (`test_masking_parity.py`). Same contract as JS/Rust/JVM.
- **Nested masking with depth budget** (`max_depth=10`, fixed-width replacement when the budget
  runs out so nothing leaks). slpy follows the **JS coherent pair** (nested serialize + nested
  mask); .NET follows flat+flat; the JVM chose flat+flat. Both pairs are safe — mixing them is not.
- **Native Rust addon (optional)** — `slpy_native` via maturin; custom-mask callables can't cross
  to Rust so the engine stays in parity mode; `get_stats().native_active` reports it.
- **Logging Matrix** — same invariant: core fields, `child()` bindings and per-call kwargs are
  never filtered.
- **Fluent API (partial)** — `child`, `with_meta`, `with_retention`.
- **Context propagation** — `contextvars`, inbound/outbound wire-name maps, `custom_headers`,
  FastAPI/ASGI middleware with per-source mapping.
- **Audit level, always-on** — `logger.audit()` emits with `_force=True` regardless of configured
  level. **Only sibling besides JS that has it** (.NET lacks it; JVM plans an `AUDIT` Marker).
- **Broker propagation primitive** — `get_propagation_headers("kafka")` applies the outbound map
  for manual producer-side propagation. More distributed story than .NET/JVM have.
- **Safety** — `on_log_failure`, `on_masking_error` (never-throw, counted), `get_stats()`,
  durable spool transport, `AdapterTransport` fallback-to-console, `SpyTransport` testing kit.

## Security hardening (2026-07-10, family-wide ReDoS audit)

Measured finding: the 256-char key cap did NOT bound nested-quantifier patterns — `(a+)+$`
hangs CPython at 40 chars, and `re` has no timeout API. Fix shipped (`61b4dcc`): a static
star-height scanner (`slpy/_regex_safety.py`, mirror of SyntropyLog's `regexSafety.ts`)
rejects explosive custom patterns at `MaskingRule` construction — init-time fail-fast.
Residual pinned by test: overlapping alternation (`(a|a)*`) is not statically detectable;
slpy-native (Rust `regex` crate, linear-time) remains immune by construction — **lo
declarativo es la salvación**.

## Python salvedades (intentional — keep them)

- **`SerializationManager` and `BrokerManager` were deliberately removed** in the slpy refactor
  ("over-engineered / integration layer, not core" — see `docs/slpy-refactor-plan.md`). Their
  absence is a decision, not drift. `get_propagation_headers()` is the kept broker primitive.
- No prototype-pollution defense needed (JS-specific threat model).

## Gaps vs JS (backlog — mount on mature Python machinery, never bespoke)

**Directive (Gabriel):** *no inventar la pólvora* — every gap below is closed by leaning on
something Python has done well for many years, not by building new machinery.

- [ ] **stdlib `logging` bridge (the structural one)** — slpy today does not touch stdlib
      `logging` at all: every third-party library's logs (uvicorn, SQLAlchemy, requests…) bypass
      the pipeline entirely. .NET rides MEL and the JVM rides SLF4J; Python's 20-year standard is
      stdlib `logging`. Fix is **additive, not a rewrite** (slpy's own API stays, it's published
      1.0.0): a `logging.Handler` subclass that funnels stdlib records through the slpy pipeline
      (matrix → mask → retention → sanitize) — the Python twin of the JVM's Logback appender.
- [ ] **"No death by log" bound** — instead of a bespoke `TimeoutStep` (JS model; and signal-based
      timeouts are a main-thread-only trap), use **stdlib `reprlib`** for non-scalar rendering:
      bounded output *by construction*, in the stdlib since forever. Same philosophy as the JVM's
      flat decision — immune by design beats guarded at runtime. Add size caps on strings; done.
- [ ] **W3C `traceparent`** in the FastAPI middleware — the header format is a fixed 4-field spec
      (a few lines to parse); if `opentelemetry-python` is installed, prefer delegating to its
      propagator (mature, maintained). Part of the "JS-only trio".
- [ ] **OpenTelemetry export recipe** — docs + example only, no code: an existing
      `UniversalAdapter` executor emitting via `opentelemetry-python`'s logs API ("JS-only trio").
- [ ] **Fluent API completion** — `with_source`, `with_transaction_id`: thin sugar over the
      existing `contextvars` store; no new machinery.
- [ ] **Per-call transport routing** — if the stdlib bridge lands, stdlib `logging` filters give
      declarative routing for free; only the slpy-native path needs the small `override` sugar.
- [~] **Hot reconfiguration** — PARTIAL: `reconfigure_logging_matrix()` already exists (core.py);
      extend the same pattern to level/transports. Multi-instance stays a salvedad (module
      singleton is Pythonic; JS needed the factory for test isolation slpy gets via fixtures).

**Family-wide note:** the "JS-only trio" (traceparent, OTel export, full hot reconfig) is missing
in every port — sl4n's roadmap lists the same three. Whoever closes them first should leave the
pattern for the others.

- [ ] **Perf: per-field-name decision cache in masking** (family finding, 2026-07-11, from the
      Java port's JMH suite): every field is scanned against all default rules per log, and the
      catch-all alternation runs on every non-sensitive field. Java fixed it with a BOUNDED
      decision cache (field name → rule-or-none, cap 4096 so hostile key floods can't grow
      memory; ReDoS/transient failures never cached) — 4,497→1,187 ns/op. slpy shares the same
      scan structure in `_find_rule`; same fix applies (a plain dict + cap; also mirrors to the
      Rust twin if profiling warrants). Mind: slpy masks nested keys — cache on the leaf key name.
