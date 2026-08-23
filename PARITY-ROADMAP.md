# slpy → SyntropyLog parity roadmap

**Status:** slpy 1.0.0 (PyPI `slpy-log`) has family parity on matrix / durable / safety / testing
and context propagation, and is **behind on masking canon and on retention**. 197 tests green on
`develop` with every optional dependency installed (`slpy-native` + `fastapi` + `httpx`); 174
passed / 15 skipped without them. Verified from CPython 3.7.17 (the declared floor) to 3.13.

This document records what source audits verified — **2026-07-10** while planning the JVM port,
**2026-08-23** aligning against SyntropyLog 2.1.0 and sl4n 1.1.0 — and the remaining gaps vs the
JS reference, so findings live in a roadmap like every family member (sl4n and syntropylog-java
have the same file).

---

## Where slpy already has parity (verified in source, do NOT re-port)

- **Masking, structurally** — one rule table, first match wins, applied by a pure tree walk over
  both engines, with a data-driven fixture asserted against Python **and** Rust
  (`test_masking_parity.py`). What is NOT canonical is the *output*: see the 2026-08-23 audit
  below. This bullet used to claim `MaskSpec` and the shared fixture; it never had either.
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

## Backport analysis — SyntropyLog 1.4.1 / 1.4.2 (native + masking fixes)

Four fixes that shipped in SyntropyLog (JS) 1.4.1/1.4.2 were analysed against slpy (2026-08-08).
**All four are N/A.** slpy *does* have a Rust addon (`slpy_native`), but it does a **different job**
than the JS one — it **masks and returns an object** (`NativeMaskingEngine.process()` → dict/list); it
does not serialize to a string — so it sidesteps the native-serialization bug classes entirely.

| SyntropyLog (JS) fix | slpy | Why |
| :-- | :-- | :-- |
| **UTF-8 panic** in the native `truncate` (byte-index slice split a multi-byte char → `SIGABRT`) | N/A | No `truncate`/`max_string_length` in `slpy-native`. The only byte slices are `&value[..at]` with `at = value.find('@')` (always a char boundary) and ASCII-digit slices. No panic possible. |
| **Masking mutated the caller's object** | N/A | Both engines build new structures: Rust `mask_tree` → `PyDict::new(py)`; Python `_mask_tree` → dict/list comprehensions. Functional and non-mutating; depth-bounded, so a cyclic input can't hang. |
| **Cross-tenant PII leak** from a process-global native config (`OnceCell`) | N/A | `NativeMaskingEngine` is per-instance (`#[new]` holds its own `rules`); there is no global `OnceCell` config to share across instances. |
| **Native path fed a serialized string to object-consuming transports** | N/A | The Rust engine returns an **object** (masked dict), and the pipeline is object-based: `logger.py` calls `transport.log(entry)` with `entry: Dict`, and each transport serializes itself (`json.dumps` in `ConsoleTransport`). No string fast-path to break. |

The JS #4 bug existed *because* the JS native engine serializes to a string (a perf optimisation) that
then leaked into object-consuming transports. slpy's Rust masks→object and each transport serializes
itself, so slpy never had that optimisation — nor the bug. The JS fix brings JS up to what slpy (and
sl4n) already do.

## Security hardening (2026-07-10, family-wide ReDoS audit)

Measured finding: the 256-char key cap did NOT bound nested-quantifier patterns — `(a+)+$`
hangs CPython at 40 chars, and `re` has no timeout API. Fix shipped (`61b4dcc`): a static
star-height scanner (`slpy/_regex_safety.py`, mirror of SyntropyLog's `regexSafety.ts`)
rejects explosive custom patterns at `MaskingRule` construction — init-time fail-fast.
Residual pinned by test: overlapping alternation (`(a|a)*`) is not statically detectable;
slpy-native (Rust `regex` crate, linear-time) remains immune by construction — **lo
declarativo es la salvación**.

## Audit 2026-08-23 — alignment against SyntropyLog 2.1.0 and sl4n 1.1.0

The family moved twice while slpy sat at 1.0.0: JS went to 2.0.0/2.1.0 (retention stops being a
payload and becomes a bridge) and sl4n to 1.1.0 (masking exemption per sink, `retentionUntil`,
out-of-logger resolution). This audit reads slpy against both.

### The masked output is not canonical

`strategyToSpec` in JS expands every built-in strategy into a `MaskSpec`, and the shared
`mask-parity-cases.json` asserts the result. The JS and JVM copies of that fixture are byte
identical (md5 `8eec8a82008d52b22be29e4aebb031d4`); slpy has **no copy** and its 13 cases are a
hand-written Python literal with different expectations. Hand-checked against the real engine:

| value | slpy today | family canon |
| :-- | :-- | :-- |
| `john@example.com` | `j**n@example.com` | `j***@example.com` |
| `4111-1111-1111-1234` | `************1234` | `****-****-****-1234` |
| `123-45-6789` | `*****6789` | `***-**-6789` |
| `+14155551234` | `*******1234` | `+*******1234` |
| `hunter2` (password) | `*******` | `[REDACTED]` |

Two of these have a security edge rather than a cosmetic one. JS redacts credentials whole on
purpose — identifiers keep a format-preserving partial, credentials do not — so slpy's `*******`
publishes the password's length. And slpy's email keeps the **last** character of the local part
as well as the first, revealing one character more than the canon.

`preserve_length` is dead config in both slpy engines: accepted in `core.py`, stored on the rule
in `masking.py`, and read by neither (`slpy-native/src/lib.rs` is at least explicit about it —
`let _ = preserve_length; // API parity with Python engine`). Adopting the canonical spec makes
it mean something for the first time (`MASK_DEFAULT_CAP_LENGTH = 8`).

**Decision (Gabriel, 2026-08-23): adopt the canon — breaking, ships in 2.0.0.** Both engines get
transliterated from the pair that already exists and is already asserted: the Rust core from
`syntropylog-native/src/lib.rs` (the spec block is binding-free — no napi in it — so it drops into
the pyo3 crate without serde), and the Python side from `src/masking/maskSpec.ts` (123 lines, no
dependencies). One trap to pin with its own test: Python's `str.isdigit()` is **not**
`is_ascii_digit()` — it is true for `'²'` and `'٣'` — so a literal transliteration of
`mask_digits` would diverge from Rust on non-ASCII digits, and all 17 fixture cases are ASCII.

### Retention is a version behind

| capability | JS 2.1.0 | sl4n 1.1.0 | slpy 1.0.0 |
| :-- | :-- | :-- | :-- |
| `retention` is the policy name, always a string | yes | yes | yes |
| materialized end-of-window date | `retentionUntil` | `retentionUntil` | **missing** |
| `months` / `years` units | yes | yes | **`days` only** |
| rounding errs long, never short | yes | yes | n/a |
| resolution outside the logger | `getRetentionPolicy` / `getRetentionUntil` | `Resolve` / `Until` | `resolve()` returns `None` quietly |
| unregistered name | raises | raises | stamps the name and continues |
| registry genuinely immutable | frozen | copied + read-only view | **holds the caller's dict by reference** |
| `policyVersion` / `emitRules` / `emitUntil` | yes | — | no |

Two findings that are slpy's own, not inherited from the family gap:

- **The same policy can travel under two different labels.** `resolve()` lowercases the lookup
  (`retention.py:53`) but `stamp()` emits the spelling the caller passed (`retention.py:68,70`),
  so `with_retention('SOX_AUDIT')` and `with_retention('sox_audit')` resolve to one policy and
  emit two label values. Everything downstream matches on an exact low-cardinality string, so a
  sweep on one does not find the other. Pinned as intended behavior today by
  `test_registry_resolves_case_insensitively`.
- **`with_retention()` stamps at binding time, not at emit time** (`logger.py:111` → `child()`).
  A date cannot live in the bindings: a logger built at startup would stamp the same
  `retention_until` forever. It has to be computed in `_emit` from the entry's own timestamp —
  the anchor JS and sl4n both chose, precisely so the window is reproducible from the record.

**Decision (Gabriel, 2026-08-23): full parity with JS 2.1.0**, in the same 2.0.0.

### The engine-drift lock never ran

The 14 tests that compare the Rust and Python engines are the regression lock against the bug
family that hit SyntropyLog (Node) #2 — two engines drifting until one leaks PII. They had never
executed in CI: `benchmark.yml` builds the addon and never calls pytest, `publish.yml` calls
pytest and never builds the addon, and there was no workflow at all on push or PR. Built the
addon locally and ran them: **they pass**. The gap was never coverage, it was execution — a
control nobody runs is not a control. Closed by `ci.yml` (`parity-native`), where a skipped test
is a failed job.

## Python salvedades (intentional — keep them)

- **`SerializationManager` and `BrokerManager` were deliberately removed** in the slpy refactor
  ("over-engineered / integration layer, not core" — see `docs/slpy-refactor-plan.md`). Their
  absence is a decision, not drift. `get_propagation_headers()` is the kept broker primitive.
- No prototype-pollution defense needed (JS-specific threat model).

## Gaps vs JS (backlog — mount on mature Python machinery, never bespoke)

**Directive (Gabriel):** *no inventar la pólvora* — every gap below is closed by leaning on
something Python has done well for many years, not by building new machinery.

### Toward 2.0.0 (decided 2026-08-23 — see the audit above)

- [x] **The floor stops being a claim** — DONE 2026-08-23. `ci.yml` runs the suite on push and PR
      (3.9 / 3.11 / 3.12 / 3.13), on CPython **3.7** (ubuntu-22.04, the last runner that has it —
      verified green at 3.7.17 before the job existed), and with the Rust addon built, where a
      skipped test fails the job. Git hooks in `.githooks/` (`git config core.hooksPath .githooks`)
      run the same gate locally; every path was verified to fail on a broken tree, not just to
      pass on a clean one. Note: enabling `core.hooksPath` overrides a *global* hooks path, so the
      refuse-on-`main` guard is replicated inside the repo's own hook.
- [x] **Canonical masking (breaking)** — DONE 2026-08-23. `MaskSpec` + `apply_mask` in both
      engines, transliterated from the family pair rather than re-derived: the Rust core from
      SyntropyLog's addon (the spec block is binding-free, so it dropped into the pyo3 crate
      without serde) and the Python side from `maskSpec.ts`. `mask-parity-cases.json` copied byte
      identical (md5 `8eec8a82008d52b22be29e4aebb031d4`) and asserted three ways: the pure
      primitive, the Python engine, and the Rust engine — 17 cases each. The 13 tree-walk cases
      stayed, with canonical expectations.
      **Two things fell out of doing it properly.** The Rust engine no longer owns a rule table or
      knows what a strategy is: Python resolves every strategy to a spec and pushes every rule,
      defaults included, so there is one rule list and one mapping in the project and neither can
      drift. And the boundary is versioned — `ENGINE_API`, checked at import — so an addon from an
      older wheel makes slpy fall back to the Python engine instead of silently masking by other
      rules. `preserve_length` went from dead config to live. 252 tests green, 0 skipped;
      209 green on CPython 3.7.
- [ ] **Retention to JS 2.1.0** — `months`/`years` on `RetentionPolicy`; a pure
      `retention_window` module (roll forward on a short month, `date.replace()` raises on 31-Feb
      so it must be explicit); `retention_until` stamped **in `_emit`** from the entry timestamp,
      never in the bindings; registry copied and frozen (`MappingProxyType`); `policies`,
      a loud `resolve()` with `RetentionPolicyNotFoundError`, `try_resolve()`, `until(name, at)`;
      more than one unit declared → refuse to start. Drop `2555` from every example
      (`retention.py`, `config.py`, `README.md`) — it is 7 × 365 and misses two leap days.
- [ ] **Masking exemption per sink** — the audit ledger is the one sink where `j***@example.com`
      proves nothing. JS names transports in app config (`masking.exemptTransports`), validated at
      `init()`, *never* declared by a transport about itself. Blocking prerequisite: slpy's
      transports have no `name` (`transport.py:60`). Exempt skips masking and nothing else —
      matrix and sanitizer still apply.
- [ ] **Two contract decisions, still open** — (a) an unregistered policy name: stamp and continue
      (today, pinned by `test_stamp_unregistered_name_still_travels`) or raise like JS; (b) the
      label a policy travels under: emit the registered canonical name, or make the lookup
      case-sensitive. Both change a test that currently pins the opposite.
- [ ] **`docs/` describes a library that does not exist** — `data_masking.md`, `lifecycle.md` and
      `logger_matrix.md` predate the refactor and document 11 facade methods that were never
      implemented in the shipped package (`add_masking_rule`, `mask_data`, `get_masking_stats`,
      `add_shutdown_handler`, `get_status`, `add_context`, `add_context_with_matrix`,
      `configure_logger_matrix`, module-level `info`/`debug`/`error`), plus a flatten/unflatten
      architecture the engine does not use. Banner added 2026-08-23 so no reader is misled;
      rewrite-or-delete is still a decision. `slpy-refactor-plan.md` is historical and stays.
- [ ] **`llms.txt`** — the compact API contract for code-generating agents, like the JS and .NET
      siblings ship. Deliberately last: writing it before the 2.0.0 surface settles means writing
      it twice.

### Standing backlog

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

- [x] **Perf: per-field-name decision cache in masking** — DONE 2026-07-11, same day as the
      finding (family fix, from the Java port's JMH suite). Bounded dict (truncated key name →
      rule-or-none, cap 4096 so hostile key floods can't grow memory; invalidated on `add_rule`;
      nested keys covered because the walk consults it at every depth) passed as an explicit
      parameter through the pure `_mask_tree`/`_find_rule` functions — no module state.
      Measured: **5,576 → 1,697 ns/op (3.3x)** on the Python path, 188 tests green, masked
      output byte-for-byte identical. The whole family now has it: Java 4,497→1,187 (JMH),
      JS 442→183, Python 5,576→1,697. The Rust twin keeps its own hot path — profile before
      mirroring anything there.
