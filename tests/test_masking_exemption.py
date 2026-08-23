"""
Masking exemption per sink — the audit ledger gets the truth.

Masking runs once before the transport loop, so every sink receives the same
redacted entry. That is right for consoles and APMs and wrong for exactly one:
the compliance ledger, where `j***@example.com` proves nothing.

The exemption is declared in APP CONFIG and matched by transport name. A
transport cannot exempt itself — the check lives in the logger, where the
transport's identity is known.
"""

import pytest

from slpy import slpy
from slpy.transport import (Transport, UnknownExemptTransportError,
                            resolve_exempt_transports, transport_name)


class Capture:
    """Duck-typed sink: anything with log() is a transport here."""

    def __init__(self, name=""):
        self.name = name
        self.entries = []

    def log(self, entry):
        self.entries.append(entry)


class NamelessCapture:
    """No `name` attribute at all — addressed by its class name."""

    def __init__(self):
        self.entries = []

    def log(self, entry):
        self.entries.append(entry)


@pytest.fixture
async def fresh_slpy():
    if slpy.is_initialized:
        await slpy.shutdown()
    yield slpy
    if slpy.is_initialized:
        await slpy.shutdown()


# ---------------------------------------------------------------------------
# Naming — pure
# ---------------------------------------------------------------------------

def test_named_by_its_name_attribute():
    assert transport_name(Capture("audit-journal")) == "audit-journal"


def test_named_by_its_class_when_it_has_no_name():
    assert transport_name(NamelessCapture()) == "NamelessCapture"


def test_named_by_its_class_when_name_is_empty():
    assert transport_name(Capture("")) == "Capture"


def test_resolving_nothing_yields_an_empty_set():
    assert resolve_exempt_transports([], [Capture("a")]) == frozenset()
    assert resolve_exempt_transports(None, [Capture("a")]) == frozenset()


# ---------------------------------------------------------------------------
# A typo must not silently mask the one sink that needed the truth
# ---------------------------------------------------------------------------

def test_unknown_exempt_transport_fails_loud():
    with pytest.raises(UnknownExemptTransportError) as excinfo:
        resolve_exempt_transports(["audit-jornal"], [Capture("audit-journal")])
    message = str(excinfo.value)
    assert "audit-jornal" in message
    assert "audit-journal" in message   # and it lists what IS configured


async def test_unknown_exempt_transport_refuses_to_start(fresh_slpy):
    with pytest.raises(UnknownExemptTransportError):
        await fresh_slpy.init({
            "logger": {"level": "info", "transports": [Capture("console")]},
            "masking": {"exempt_transports": ["audit-journal"]},
        })
    assert not fresh_slpy.is_initialized


# ---------------------------------------------------------------------------
# The feature itself
# ---------------------------------------------------------------------------

async def test_exempt_sink_receives_cleartext(fresh_slpy):
    console = Capture("console")
    ledger = Capture("audit-journal")
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [console, ledger]},
        "masking": {"enable_default_rules": True, "exempt_transports": ["audit-journal"]},
    })
    fresh_slpy.get_logger("payments").audit(
        "Manager override", email="john@example.com", password="hunter2"
    )

    assert console.entries[0]["email"] == "j***@example.com"
    assert console.entries[0]["password"] == "[REDACTED]"
    assert ledger.entries[0]["email"] == "john@example.com"
    assert ledger.entries[0]["password"] == "hunter2"


async def test_a_transport_cannot_exempt_itself(fresh_slpy):
    """The exemption is app config. A sink declaring anything about itself —
    here, the most optimistic attribute it could set — changes nothing."""
    class SelfDeclaring(Capture):
        exempt_from_masking = True
        exempt = True

    sink = SelfDeclaring("sneaky")
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [sink]},
        "masking": {"enable_default_rules": True},
    })
    fresh_slpy.get_logger("svc").info("login", password="hunter2")

    assert sink.entries[0]["password"] == "[REDACTED]"


async def test_exempt_by_class_name(fresh_slpy):
    sink = NamelessCapture()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [sink]},
        "masking": {"exempt_transports": ["NamelessCapture"]},
    })
    fresh_slpy.get_logger("svc").info("login", password="hunter2")

    assert sink.entries[0]["password"] == "hunter2"


async def test_two_sinks_sharing_a_name_are_both_exempt(fresh_slpy):
    """Names are how config addresses a sink, and nothing enforces uniqueness.
    Pinned so the behaviour is known rather than discovered."""
    a, b = Capture("ledger"), Capture("ledger")
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [a, b]},
        "masking": {"exempt_transports": ["ledger"]},
    })
    fresh_slpy.get_logger("svc").info("x", password="hunter2")

    assert a.entries[0]["password"] == "hunter2"
    assert b.entries[0]["password"] == "hunter2"


# ---------------------------------------------------------------------------
# Exempt skips masking and NOTHING else
# ---------------------------------------------------------------------------

async def test_exempt_sink_is_still_sanitized(fresh_slpy):
    """An audit ledger must not receive ANSI escapes either: a forged log line
    is a forged log line whether or not the values are masked."""
    ledger = Capture("audit-journal")
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [ledger]},
        "masking": {"exempt_transports": ["audit-journal"]},
    })
    fresh_slpy.get_logger("svc").info(
        "login", user_agent="curl\x1b[31m\x1b[2Kfake INFO all good"
    )

    delivered = ledger.entries[0]["user_agent"]
    assert "\x1b" not in delivered
    assert delivered == "curlfake INFO all good"


async def test_exempt_sink_is_still_filtered_by_the_matrix(fresh_slpy):
    """The matrix decides which CONTEXT fields exist at all; it runs before
    masking and the exemption does not reach back past it."""
    ledger = Capture("audit-journal")
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [ledger]},
        "logging_matrix": {"default": ["request_id"]},
        "masking": {"exempt_transports": ["audit-journal"]},
    })
    async with fresh_slpy.context(request_id="req-1", tenant_id="acme"):
        fresh_slpy.get_logger("svc").info("x", password="hunter2")

    entry = ledger.entries[0]
    assert entry["request_id"] == "req-1"
    assert "tenant_id" not in entry          # dropped by the matrix, exempt or not
    assert entry["password"] == "hunter2"    # and the values are still cleartext


async def test_exempt_sink_keeps_the_retention_stamp(fresh_slpy):
    ledger = Capture("audit-journal")
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [ledger]},
        "retention_policies": {"SOX": {"years": 7, "class": "SOX"}},
        "masking": {"exempt_transports": ["audit-journal"]},
    })
    fresh_slpy.get_logger("svc").with_retention("SOX").audit("override", password="hunter2")

    entry = ledger.entries[0]
    assert entry["retention"] == "SOX"
    assert "retention_until" in entry
    assert entry["password"] == "hunter2"


# ---------------------------------------------------------------------------
# Cost when unused
# ---------------------------------------------------------------------------

async def test_no_exemption_means_one_entry_for_everyone(fresh_slpy):
    """Not a micro-benchmark: object identity is the observable proof that the
    second projection was never built."""
    a, b = Capture("a"), Capture("b")
    await fresh_slpy.init({"logger": {"level": "info", "transports": [a, b]}})
    fresh_slpy.get_logger("svc").info("x", password="hunter2")

    assert a.entries[0] is b.entries[0]


async def test_an_exemption_means_two_distinct_entries(fresh_slpy):
    console, ledger = Capture("console"), Capture("audit-journal")
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [console, ledger]},
        "masking": {"exempt_transports": ["audit-journal"]},
    })
    fresh_slpy.get_logger("svc").info("x", password="hunter2")

    assert console.entries[0] is not ledger.entries[0]


# ---------------------------------------------------------------------------
# The base class keeps working for anyone who inherits it
# ---------------------------------------------------------------------------

async def test_a_transport_subclass_can_be_named(fresh_slpy):
    class Ledger(Transport):
        def __init__(self):
            self.name = "audit-journal"
            self.entries = []

        def log(self, entry):
            self.entries.append(entry)

    ledger = Ledger()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [ledger]},
        "masking": {"exempt_transports": ["audit-journal"]},
    })
    fresh_slpy.get_logger("svc").info("x", password="hunter2")

    assert ledger.entries[0]["password"] == "hunter2"
