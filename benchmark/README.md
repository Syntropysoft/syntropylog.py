# slpy Benchmark

> slpy vs structlog vs loguru vs logging (stdlib)
> All loggers write to a null stream — pure logic overhead, no I/O.

## Results

```
logging (baseline):        18.8 µs ± 1.7 µs
slpy (simple):              6.2 µs ± 0.4 µs   ← Rust addon active
structlog (simple):         8.0 µs ± 0.9 µs
loguru (simple):           58.9 µs ± 6.7 µs

logging (complex):         20.4 µs ± 2.2 µs   no masking
slpy (complex + masking):  18.0 µs ± 2.7 µs   ← Rust addon active, masking ON
structlog (complex):       10.8 µs ± 1.2 µs   no masking
loguru (complex):          61.8 µs ± 5.0 µs   no masking
```

## Reading the results

### Simple log — slpy is the fastest

| # | Logger | µs | Notes |
|---|--------|----|-------|
| 1 | **slpy** | **6.2** | Rust addon active |
| 2 | structlog | 8.0 | |
| 3 | logging (stdlib) | 18.8 | Python baseline |
| 4 | loguru | 58.9 | |

slpy with the Rust addon is **faster than structlog** on simple logs — and structlog is considered the performance reference for structured logging in Python.

### Complex object — the fair comparison

| # | Logger | µs | Masking |
|---|--------|----|---------|
| 1 | structlog | 10.8 | ❌ |
| **2** | **slpy** | **18.0** | **✅** |
| 3 | logging | 20.4 | ❌ |
| 4 | loguru | 61.8 | ❌ |

**slpy with masking fully active is faster than the stdlib `logging` module without masking.**
It is 3.4x faster than loguru without masking.

The only logger above slpy in this group is structlog — which does not mask, does not propagate context automatically, and requires manual processor pipeline configuration to do either.

### What the overhead is

The gap between slpy simple (6.2 µs) and slpy complex+masking (18.0 µs) is **11.8 µs** — that is the cost of the Rust masking engine processing a nested object with sensitive fields:

- Flatten nested dict to dotted-key map
- Regex match each leaf key against 6+ compiled patterns
- Apply masking strategy per matched field
- Reconstruct the original nested structure

Before the Rust addon, that cost was **29 µs** in pure Python. The Rust core reduced masking overhead by **59%**.

### Python fallback

If `slpy-native` is not installed, slpy falls back to the pure Python engine transparently. No code changes required. Disable native explicitly with `SLPY_NATIVE_DISABLE=1`.

---

## How to run

```bash
# Install dependencies
pip install slpy[dev] structlog loguru pyperf

# Build and install the Rust addon (optional — slpy works without it)
cd slpy-native
pip install maturin
python -m maturin build --release
pip install target/wheels/*.whl

# Run
cd ..
py benchmark/bench.py --fast       # quick look
py benchmark/bench.py              # full pyperf run (more stable)

# Compare: native vs Python only
py benchmark/bench.py --fast
SLPY_NATIVE_DISABLE=1 py benchmark/bench.py --fast
```

---

## Stress test — official results (GitHub Actions, Ubuntu, Python 3.12)

> 1M iterations per scenario, Rust addon active, null transport.

```
Simple log  (slpy.info — no masking payload)
  1M    1.166s    85,774 logs/sec    11.66 µs/log    1.30 KB heap

Complex log  (slpy.info + nested object — masking ON)
  1M    2.988s    33,472 logs/sec    29.88 µs/log   11.30 KB heap

MaskingEngine.process() only  (hot path isolation)
  1M    1.684s    59,369 logs/sec    16.84 µs/log    4.03 KB heap

child() + log  (new binding per iteration)
  1M    1.719s    58,165 logs/sec    17.19 µs/log       0 B heap

Async context scope  (open+close per iteration)
  1M    4.497s    22,237 logs/sec    44.97 µs/log       0 B heap
  10M  44.762s    22,340 logs/sec    44.76 µs/log       0 B heap
```

**child() and async context scope allocate 0 bytes at 1M iterations** — no GC pressure.
**Async context scope: zero degradation from 1M to 10M** (44.97 → 44.76 µs).

---

## Environment

- **Official (CI):** Ubuntu latest, Python 3.12, GitHub Actions — use these numbers for comparisons.
- **Local reference:** Windows 11, Python 3.14.3, AMD64 — ~1.7–2x slower due to OS jitter.

To reproduce the official numbers locally on Linux:
```bash
python -m pyperf system tune   # reduce OS jitter
python benchmark/bench.py
SLPY_BENCH_VOLUMES=1000000 python benchmark/stress.py
```
