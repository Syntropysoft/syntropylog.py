"""
slpy benchmark — slpy vs structlog vs loguru vs logging (stdlib)

All loggers write to /dev/null (os.devnull) to measure logic overhead only,
not I/O throughput.

Groups:
  1. Simple log     — plain string, no masking. Baseline comparison.
  2. Complex object — same payload across all loggers.
                      slpy has masking active; others do not.
                      This is the fair comparison.

Run:
    py benchmark/bench.py
    py benchmark/bench.py --fast          # fewer iterations, quick look
"""

import asyncio
import io
import logging
import os
import sys
import pyperf

# ---------------------------------------------------------------------------
# Path setup — run from repo root
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Shared payload
# ---------------------------------------------------------------------------
SIMPLE_MSG = "Hello benchmark"

COMPLEX_OBJ = {
    "user": {
        "id": 123,
        "email": "secret@example.com",
        "name": "John Doe",
        "token": "very-secret-token",
    },
    "meta": {"request_id": "abc-123", "ua": "Mozilla/5.0"},
}

# ---------------------------------------------------------------------------
# Null stream — absorbs all output
# ---------------------------------------------------------------------------
class NullStream(io.RawIOBase):
    def write(self, b):
        return len(b) if isinstance(b, (bytes, bytearray)) else len(b.encode())
    def writable(self):
        return True

null_stream = NullStream()

# ---------------------------------------------------------------------------
# logging (stdlib) setup
# ---------------------------------------------------------------------------
stdlib_logger = logging.getLogger("bench")
stdlib_logger.setLevel(logging.INFO)
stdlib_handler = logging.StreamHandler(null_stream)
stdlib_logger.addHandler(stdlib_handler)
stdlib_logger.propagate = False

# ---------------------------------------------------------------------------
# structlog setup
# ---------------------------------------------------------------------------
import structlog

structlog.configure(
    processors=[
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=null_stream),
    cache_logger_on_first_use=True,
)
sl_log = structlog.get_logger("bench")

# ---------------------------------------------------------------------------
# loguru setup
# ---------------------------------------------------------------------------
from loguru import logger as loguru_logger
loguru_logger.remove()
loguru_logger.add(null_stream, format="{message}", level="INFO", serialize=True)

# ---------------------------------------------------------------------------
# slpy setup
# ---------------------------------------------------------------------------
from slpy import slpy
from slpy.transport import Transport

class NullTransport(Transport):
    def log(self, entry):
        pass

async def setup_slpy():
    await slpy.init({
        "logger": {"level": "info", "transports": [NullTransport()]},
        "masking": {"enable_default_rules": True},
    })

asyncio.run(setup_slpy())
slpy_logger = slpy.get_logger("bench")

# ---------------------------------------------------------------------------
# Benchmark functions
# ---------------------------------------------------------------------------

def bench_stdlib_simple(loops):
    range_ = range(loops)
    t0 = pyperf.perf_counter()
    for _ in range_:
        stdlib_logger.info(SIMPLE_MSG)
    return pyperf.perf_counter() - t0


def bench_structlog_simple(loops):
    range_ = range(loops)
    t0 = pyperf.perf_counter()
    for _ in range_:
        sl_log.info(SIMPLE_MSG)
    return pyperf.perf_counter() - t0


def bench_loguru_simple(loops):
    range_ = range(loops)
    t0 = pyperf.perf_counter()
    for _ in range_:
        loguru_logger.info(SIMPLE_MSG)
    return pyperf.perf_counter() - t0


def bench_slpy_simple(loops):
    range_ = range(loops)
    t0 = pyperf.perf_counter()
    for _ in range_:
        slpy_logger.info(SIMPLE_MSG)
    return pyperf.perf_counter() - t0


def bench_stdlib_complex(loops):
    range_ = range(loops)
    t0 = pyperf.perf_counter()
    for _ in range_:
        stdlib_logger.info("User action", extra=COMPLEX_OBJ)
    return pyperf.perf_counter() - t0


def bench_structlog_complex(loops):
    range_ = range(loops)
    t0 = pyperf.perf_counter()
    for _ in range_:
        sl_log.info("User action", **COMPLEX_OBJ)
    return pyperf.perf_counter() - t0


def bench_loguru_complex(loops):
    range_ = range(loops)
    t0 = pyperf.perf_counter()
    for _ in range_:
        loguru_logger.info("User action", **COMPLEX_OBJ)
    return pyperf.perf_counter() - t0


def bench_slpy_complex(loops):
    """slpy with masking active — the fair comparison."""
    range_ = range(loops)
    t0 = pyperf.perf_counter()
    for _ in range_:
        slpy_logger.info("User action", **COMPLEX_OBJ)
    return pyperf.perf_counter() - t0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

runner = pyperf.Runner()

print("\n=== slpy benchmark (slpy vs structlog vs loguru vs logging) ===\n")

# Group 1 — simple log
runner.bench_time_func("logging (baseline)",   bench_stdlib_simple)
runner.bench_time_func("slpy (simple)",        bench_slpy_simple)
runner.bench_time_func("structlog (simple)",   bench_structlog_simple)
runner.bench_time_func("loguru (simple)",      bench_loguru_simple)

# Group 2 — complex object
runner.bench_time_func("logging (complex)",           bench_stdlib_complex)
runner.bench_time_func("slpy (complex + masking)",    bench_slpy_complex)
runner.bench_time_func("structlog (complex)",         bench_structlog_complex)
runner.bench_time_func("loguru (complex)",            bench_loguru_complex)
