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

- **A policy declaring more than one unit refuses to start**, where the Node reference lets `years`
  win. JS is lenient for a reason specific to its history: `months` had been an unread key, so
  refusing would have *removed* a date from records that already got one, and taking a compliance
  date away in a minor is worse than resolving an ambiguity the way it had always resolved. In slpy
  both units arrived together in the same release, no config can be carrying both by accident, and
  there is nothing to preserve — so the safer reading wins, the same one sl4n took. Divergence from
  the reference, recorded here per the repo's own rule.

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
- [x] **Retention to JS 2.1.0** — DONE 2026-08-23. `months`/`years` on `RetentionPolicy`; the pure
      `slpy/retention_window.py` (roll forward on a short month — `date.replace()` cannot even
      express 31-Feb, so the roll is explicit); `retention_until` computed in `_emit` from the
      entry's own instant, from the same clock read as `timestamp`, and written after the kwargs
      so a caller cannot hand-write a compliance date; registry copied and frozen
      (`MappingProxyType`); `policies`, `require()` with `RetentionPolicyNotFoundError`,
      `until(name, at)` anchored in UTC, and the pure `retention_until` exported. `2555` is gone
      from every example that taught it, and survives only in the test that pins the drift.
      **`resolve()` stayed quiet** rather than becoming the loud form as sl4n spells it: slpy
      already shipped it returning `None`, and making the same call throw is the worst kind of
      break. The loud one is `require()`.
- [x] **Masking exemption per sink** — DONE 2026-08-23. `masking.exempt_transports` names sinks
      that receive the entry unmasked, validated at `init()` against the configured pool with
      `UnknownExemptTransportError`. A transport is addressed by its `name` or its class name;
      `transport_name()` reads an attribute rather than requiring a base class, because slpy's
      transports are duck-typed and the tests' own sinks do not inherit anything. The check lives
      in the logger, where identity is known — a sink cannot exempt itself, pinned by a test whose
      sink sets `exempt_from_masking = True` and is masked anyway. Exempt skips masking and nothing
      else: matrix and sanitizer still apply, both pinned. Cost when unused is zero, and the proof
      is object identity — with no exemption every sink receives the same entry object.
- [x] **Two contract decisions** — DECIDED 2026-08-23 (Gabriel). (a) An unregistered name
      **raises**, like JS — from `with_retention()`, where the logger is built, so logging still
      cannot throw and there is a test that says so. (b) The emitted label is the **registered
      spelling**; lookup stays case-insensitive. Both tests that pinned the opposite were rewritten
      to pin the new contract.
- [ ] **Rewrite `docs/`** — `data_masking.md`, `lifecycle.md` and `logger_matrix.md` predate the
      refactor and document 11 facade methods that were never in the shipped package
      (`add_masking_rule`, `mask_data`, `get_masking_stats`, `add_shutdown_handler`, `get_status`,
      `add_context`, `add_context_with_matrix`, `configure_logger_matrix`, module-level
      `info`/`debug`/`error`), plus a flatten/unflatten architecture the engine does not use.
      **Decision (Gabriel, 2026-08-23): they stay, bannered, and get rewritten** — not deleted.
      sl4n dropped its equivalents because `docs/` does not travel inside a nupkg, so nobody was
      reading them; here the repo itself is read, and PyPI ships the README. Banner added
      2026-08-23 so no reader is misled in the meantime. `slpy-refactor-plan.md` is historical and
      stays as-is.
- [x] **`llms.txt`** — DONE 2026-08-23, deliberately last so it was written once. Every claim was
      verified against the source, and the verification was kept as
      `tests/test_llms_contract.py` (44 tests) instead of thrown away — the document cannot go
      stale in silence. Ships in the sdist only: a wheel installs the package directory, and a
      second copy under `slpy/` could drift from the canonical one at the repo root. sl4n ships
      its copy inside the nupkg; this is the Python packaging shape, stated rather than hidden.

- [x] **`py.typed` existed only in `pyproject.toml`** — FIXED 2026-08-23. Declared in
      `package-data` from the start, never created, so 1.0.0 shipped with no PEP 561 marker and a
      strict type checker was entitled to ignore every annotation in the package. Both halves are
      now pinned by test. Found while packaging `llms.txt`.

- [ ] **Type checking is not in the gate** — running mypy over the package for the first time
      found four real annotation defects (fixed 2026-08-23: `policies` annotated `Dict` while
      returning a read-only `MappingProxyType`, `colors: bool = None`, a name bound to both a dict
      and a list in `clean_tree`, and an unannotated `_exempt_transports`). What remains is **13
      reports of a single pattern**: `_require_initialized()` narrows the singleton's `Optional`
      attributes and mypy cannot see it, so every access after it reads as `union-attr`. Fixing
      that is a design change — a `_State` object built at `init()`, or asserts at each boundary —
      and adding mypy to the gate is a "what blocks a commit" decision. Both are Gabriel's calls,
      not drift.

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
