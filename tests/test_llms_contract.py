"""
`llms.txt` is the contract a code-generating agent reads, and a wrong line there
becomes wrong code in somebody else's repository. These tests pin the claims it
makes that are easy to get wrong or easy to break — so the document cannot go
stale in silence.

Each test name states the claim. If one fails, either the code regressed or
`llms.txt` needs the same edit.
"""

import inspect
import os
import pathlib
import re
from datetime import date

import pytest

import slpy
from slpy import slpy as facade
from slpy.config import ConfigManager
from slpy.masking import (MASK_KEYS, MaskingEngine, MaskingRule, MaskingStrategy,
                          _safe_payload, mask_pattern)


@pytest.fixture
async def uninitialized():
    if facade.is_initialized:
        await facade.shutdown()
    yield facade
    if facade.is_initialized:
        await facade.shutdown()


@pytest.fixture
def python_engine():
    engine = MaskingEngine(enable_default_rules=True)
    engine._native = None
    return engine


# ---------------------------------------------------------------------------
# "warn, not warning"
# ---------------------------------------------------------------------------

def test_the_level_method_is_warn_not_warning():
    assert hasattr(slpy.Logger, "warn")
    assert not hasattr(slpy.Logger, "warning")


def test_the_logger_has_exactly_these_public_methods():
    public = {n for n, _ in inspect.getmembers(slpy.Logger) if not n.startswith("_")}
    assert public == {
        "debug", "info", "warn", "error", "audit",
        "child", "with_meta", "with_retention",
    }


# ---------------------------------------------------------------------------
# "Any public call before init() raises RuntimeError — except is_initialized"
# ---------------------------------------------------------------------------

async def test_is_initialized_is_the_only_call_that_works_before_init(uninitialized):
    assert uninitialized.is_initialized is False


@pytest.mark.parametrize("call", [
    lambda s: s.get_logger("x"),
    lambda s: s.get("correlation_id"),
    lambda s: s.get_propagation_headers(),
    lambda s: s.get_propagation_header_name("correlation_id"),
    lambda s: s.set_level("debug"),
    lambda s: s.reconfigure_logging_matrix({}),
    lambda s: s.get_stats(),
], ids=["get_logger", "get", "propagation_headers", "header_name",
        "set_level", "reconfigure_matrix", "get_stats"])
async def test_every_facade_call_refuses_before_init(uninitialized, call):
    with pytest.raises(RuntimeError):
        call(uninitialized)


async def test_context_refuses_before_init(uninitialized):
    with pytest.raises(RuntimeError):
        async with uninitialized.context(a=1):
            pass


async def test_init_twice_refuses(uninitialized):
    await uninitialized.init({})
    with pytest.raises(RuntimeError):
        await uninitialized.init({})


async def test_shutdown_is_safe_to_repeat(uninitialized):
    await uninitialized.init({})
    await uninitialized.shutdown()
    await uninitialized.shutdown()
    assert uninitialized.is_initialized is False


# ---------------------------------------------------------------------------
# The default-rules table, exactly as llms.txt and the README print it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,value,expected", [
    ("email",       "john@example.com",     "j***@example.com"),
    ("password",    "hunter2",              "[REDACTED]"),
    ("token",       "abc123xyz",            "[REDACTED]"),
    ("credit_card", "4111-1111-1111-1234",  "****-****-****-1234"),
    ("ssn",         "123-45-6789",          "***-**-6789"),
    ("phone",       "+1 (555) 123-4567",    "+* (***) ***-4567"),
])
def test_the_documented_masking_table(python_engine, key, value, expected):
    assert python_engine.process({key: value})[key] == expected


def test_default_rules_are_greedy_as_documented(python_engine):
    """'a key that CONTAINS the word matches' — the README and llms.txt both
    promise `user_password` and `sessionKey` are covered."""
    result = python_engine.process({"user_password": "x", "sessionKey": "y"})
    assert result["user_password"] == "[REDACTED]"
    assert result["sessionKey"] == "[REDACTED]"


def test_the_documented_strategy_enum():
    assert {s.name for s in MaskingStrategy} == {
        "CREDIT_CARD", "SSN", "EMAIL", "PHONE", "PASSWORD", "TOKEN", "CUSTOM"
    }


def test_the_documented_mask_pattern_expansion():
    assert mask_pattern(*MASK_KEYS["token"]) == "^(token|key|auth|jwt|bearer)$"


def test_the_documented_cuit_example():
    """The custom-spec example printed in both README and llms.txt."""
    rule = MaskingRule(pattern=r"^cuit$", strategy=MaskingStrategy.CUSTOM,
                       spec=slpy.MaskSpec(scope="digits", unmask_end=1))
    engine = MaskingEngine(enable_default_rules=False, extra_rules=[rule])
    engine._native = None
    assert engine.process({"cuit": "20-12345678-9"})["cuit"] == "**-********-9"


def test_redacted_constant_and_the_preserve_length_cap():
    assert slpy.REDACTED == "[REDACTED]"
    assert slpy.apply_mask("secret-value", slpy.MaskSpec(preserve_length=False)) == "*" * 8


def test_a_failed_masking_pass_leaks_no_metadata():
    """llms.txt promises the degraded entry is exactly these five fields."""
    safe = _safe_payload({"level": "info", "message": "m", "timestamp": "t",
                          "service": "s", "email": "real@example.com"})
    assert set(safe) == {"level", "message", "timestamp", "service", "_masking_failed"}
    assert "real@example.com" not in str(safe)


# ---------------------------------------------------------------------------
# The errors table
# ---------------------------------------------------------------------------

def test_an_unsafe_key_pattern_raises_when_the_rule_is_built():
    with pytest.raises(ValueError):
        MaskingRule(pattern=r"(a+)+$", strategy=MaskingStrategy.TOKEN)


def test_an_invalid_level_raises_value_error():
    with pytest.raises(ValueError):
        ConfigManager({"logger": {"level": "nope"}}).validate()


@pytest.mark.parametrize("level", ["debug", "info", "warn", "error", "audit", "silent"])
def test_every_documented_level_is_accepted(level):
    ConfigManager({"logger": {"level": level}}).validate()


# ---------------------------------------------------------------------------
# Documented signatures and surface
# ---------------------------------------------------------------------------

def test_documented_constructor_signatures():
    assert list(inspect.signature(slpy.AdapterTransport.__init__).parameters)[1:] == \
        ["name", "adapter", "formatter"]
    assert list(inspect.signature(slpy.DurableFileTransport.__init__).parameters)[1:] == \
        ["inner", "spool_path"]
    assert inspect.signature(
        slpy.PrettyConsoleTransport.__init__).parameters["colors"].default is None


def test_everything_in_all_actually_exists():
    missing = [name for name in slpy.__all__ if not hasattr(slpy, name)]
    assert missing == []


def test_the_documented_stats_fields():
    from slpy.stats import StatsSnapshot
    assert set(StatsSnapshot.__dataclass_fields__) == {
        "logs_processed", "transport_failures", "masking_failures",
        "uptime_seconds", "native_active",
    }


def test_the_documented_outbound_event_fields():
    assert set(slpy.OutboundEvent.__dataclass_fields__) == {
        "target", "headers", "correlation_id", "trace_id", "timestamp",
    }


def test_the_documented_spy_transport_surface():
    from slpy.testing import SpyTransport
    public = {n for n, _ in inspect.getmembers(SpyTransport) if not n.startswith("_")}
    assert public == {
        "log", "entries", "count", "first_entry", "last_entry",
        "clear", "at_level", "with_field", "any_message_contains",
    }


# ---------------------------------------------------------------------------
# "SLPY_LOG_LEVEL is the only environment variable slpy reads for configuration"
# ---------------------------------------------------------------------------

def test_the_only_environment_variables_slpy_reads():
    """A negation, so it is asserted over the whole package rather than claimed."""
    package = os.path.dirname(slpy.__file__)
    source = "".join(
        open(os.path.join(package, name)).read()
        for name in sorted(os.listdir(package))
        if name.endswith(".py")
    )
    found = set(re.findall(r'(?:getenv|environ\.get|environ\[)\(?["\']([A-Z_]+)', source))
    assert found == {"SLPY_LOG_LEVEL", "SLPY_NATIVE_DISABLE"}


# ---------------------------------------------------------------------------
# Retention examples printed in llms.txt
# ---------------------------------------------------------------------------

def test_the_documented_rounding_examples():
    assert slpy.retention_until(date(2026, 1, 31), slpy.RetentionPolicy(months=1)) == date(2026, 3, 3)
    assert slpy.retention_until(date(2024, 2, 29), slpy.RetentionPolicy(years=1)) == date(2025, 3, 1)


async def test_the_documented_quick_start_output_shape(uninitialized):
    """The entry shape llms.txt prints, field for field."""
    from slpy.testing import SpyTransport

    spy = SpyTransport()
    await uninitialized.init({
        "logger": {"level": "info", "transports": [spy]},
        "masking": {"enable_default_rules": True},
    })
    async with uninitialized.context(request_id="req-1"):
        uninitialized.get_logger("payments").info(
            "Card charged", amount=299.9, email="john@example.com"
        )

    entry = spy.first_entry
    assert list(entry)[:4] == ["level", "message", "timestamp", "service"]
    assert entry["level"] == "info"
    assert entry["service"] == "payments"
    assert entry["request_id"] == "req-1"
    assert entry["amount"] == 299.9
    assert entry["email"] == "j***@example.com"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+00:00$", entry["timestamp"])


# ---------------------------------------------------------------------------
# Packaging promises
# ---------------------------------------------------------------------------

def test_the_py_typed_marker_exists():
    """`pyproject.toml` has declared `slpy = ["py.typed"]` in package-data since
    the beginning and the file was never created, so 1.0.0 shipped without the
    PEP 561 marker: a type checker is entitled to ignore every annotation in the
    package. Declaring it and not having it is the failure mode this pins.
    """
    package = pathlib.Path(slpy.__file__).parent
    assert (package / "py.typed").is_file()


def test_py_typed_is_declared_as_package_data():
    """The other half of the promise: the file must also be told to ship."""
    root = pathlib.Path(slpy.__file__).parent.parent
    pyproject = (root / "pyproject.toml").read_text()
    assert "[tool.setuptools.package-data]" in pyproject
    assert 'slpy = ["py.typed"]' in pyproject


def test_llms_txt_ships_in_the_sdist():
    root = pathlib.Path(slpy.__file__).parent.parent
    assert (root / "llms.txt").is_file()
    assert "include llms.txt" in (root / "MANIFEST.in").read_text()


def test_the_version_is_the_same_in_both_places():
    """`pyproject.toml` is what the build stamps on the artifact; `__version__` is
    what the running program reports, and `setup.py` reads it. Move one without the
    other and the wheel says one number while `slpy.__version__` says another —
    silently, because nothing imports the manifest at runtime.
    """
    root = pathlib.Path(slpy.__file__).parent.parent
    declared = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(),
                         re.MULTILINE).group(1)
    assert slpy.__version__ == declared


def test_every_python_ci_runs_is_declared_as_a_classifier():
    """The `pyversions` badge is generated from these, so a version CI tests and
    the manifest omits becomes a README that undersells the package."""
    root = pathlib.Path(slpy.__file__).parent.parent
    classifiers = re.findall(r"Programming Language :: Python :: (\d+\.\d+)",
                             (root / "pyproject.toml").read_text())
    ci = re.search(r'python-version: \[([^\]]+)\]',
                   (root / ".github/workflows/ci.yml").read_text()).group(1)
    tested = re.findall(r'"(\d+\.\d+)"', ci)
    assert set(tested) <= set(classifiers), (
        "CI tests %s which is not declared as a classifier" % (set(tested) - set(classifiers))
    )
