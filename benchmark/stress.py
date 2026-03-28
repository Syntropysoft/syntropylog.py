"""
slpy stress test — 100k, 1M, 5M, 10M iterations

Measures:
  - Total time
  - Throughput (logs/sec)
  - Memory heap delta
  - Sustained performance (no degradation across iterations)

Run:
    py benchmark/stress.py
"""

import asyncio
import gc
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slpy import slpy
from slpy.transport import Transport
from slpy.masking import MaskingEngine


class NullTransport(Transport):
    def log(self, entry):
        pass


async def setup():
    await slpy.init({
        "logger": {"level": "info", "transports": [NullTransport()]},
        "masking": {"enable_default_rules": True},
    })


SIMPLE_MSG = "Hello stress test"
COMPLEX_OBJ = {
    "user": {
        "id": 123,
        "email": "secret@example.com",
        "name": "John Doe",
        "token": "very-secret-token",
    },
    "meta": {"request_id": "abc-123", "ua": "Mozilla/5.0"},
}


def format_num(n: int) -> str:
    if n >= 100_000:
        return f"{n // 100_000}M"
    return f"{n // 1_000}k"


def format_bytes(b: int) -> str:
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.2f} MB"
    if b >= 1024:
        return f"{b / 1024:.2f} KB"
    return f"{b} B"


def run_batch(fn, n: int):
    gc.collect()
    mem_before = get_heap()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    elapsed = time.perf_counter() - t0
    gc.collect()
    mem_after = get_heap()
    return elapsed, mem_after - mem_before


def get_heap() -> int:
    try:
        import tracemalloc
        if tracemalloc.is_tracing():
            _, peak = tracemalloc.get_traced_memory()
            return peak
    except Exception:
        pass
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except Exception:
        pass
    # Windows fallback via psutil
    try:
        import psutil, os as _os
        return psutil.Process(_os.getpid()).memory_info().rss
    except Exception:
        return 0


# Override from env: SLPY_BENCH_VOLUMES=100000,1000000
_env_volumes = os.environ.get("SLPY_BENCH_VOLUMES")
VOLUMES = (
    [int(v) for v in _env_volumes.split(",")]
    if _env_volumes
    else [100_000, 1_000_000]
)
COL_W = 14


def header(title: str):
    print(f"\n{'-' * 70}")
    print(f"  {title}")
    print('-' * 70)
    print(
        f"  {'iterations':<12}"
        f"{'time (s)':>{COL_W}}"
        f"{'logs/sec':>{COL_W}}"
        f"{'µs/log':>{COL_W}}"
        f"{'heap delta':>{COL_W}}"
    )
    print('-' * 70)


def row(n: int, elapsed: float, heap_delta: int):
    throughput = n / elapsed
    us_per_log = (elapsed / n) * 1e6
    print(
        f"  {format_num(n):<12}"
        f"{elapsed:>{COL_W}.3f}"
        f"{throughput:>{COL_W},.0f}"
        f"{us_per_log:>{COL_W}.2f}"
        f"{format_bytes(max(heap_delta, 0)):>{COL_W}}"
    )


async def main():
    await setup()

    logger = slpy.get_logger("stress")
    masking_engine = MaskingEngine(enable_default_rules=True)

    print(f"\n{'=' * 70}")
    print(f"  slpy stress test — sustained throughput under high volume")
    print(f"  Native Rust addon: {'YES' if masking_engine.is_native else 'NO (Python fallback)'}")
    print(f"{'=' * 70}")

    # -- Group 1: Simple log ----------------------------------------------
    import tracemalloc
    tracemalloc.start()

    header("Simple log  (slpy.info — no masking payload)")
    for n in VOLUMES:
        elapsed, heap = run_batch(lambda: logger.info(SIMPLE_MSG), n)
        row(n, elapsed, heap)

    # -- Group 2: Complex log with masking --------------------------------
    header("Complex log  (slpy.info + nested object — masking ON)")
    for n in VOLUMES:
        elapsed, heap = run_batch(
            lambda: logger.info("User action", **COMPLEX_OBJ), n
        )
        row(n, elapsed, heap)

    # -- Group 3: MaskingEngine only --------------------------------------
    header("MaskingEngine.process() only  (hot path isolation)")
    obj = dict(COMPLEX_OBJ)
    for n in VOLUMES:
        elapsed, heap = run_batch(
            lambda: masking_engine.process(dict(obj)), n
        )
        row(n, elapsed, heap)

    # -- Group 4: child() + log -------------------------------------------
    header("child() + log  (new binding per iteration)")
    for n in VOLUMES:
        elapsed, heap = run_batch(
            lambda: logger.child(order_id="ORD-001").info("Processing"), n
        )
        row(n, elapsed, heap)

    # -- Group 5: Async context scope -------------------------------------
    header("Async context scope  (open+close per iteration)")

    async def one_scope():
        async with slpy.context(request_id="req-001", user_id="usr-42"):
            logger.info("In scope")

    for n in [100_000, 1_000_000]:  # async overhead — 5M/10M takes too long in --fast mode
        gc.collect()
        mem_before = get_heap()
        t0 = time.perf_counter()
        for _ in range(n):
            await one_scope()
        elapsed = time.perf_counter() - t0
        gc.collect()
        heap = get_heap() - mem_before
        row(n, elapsed, heap)

    tracemalloc.stop()
    print(f"\n{'=' * 70}\n")
    await slpy.shutdown()


asyncio.run(main())
