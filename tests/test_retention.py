"""Retention policies — registry + with_retention() stamping."""

from datetime import datetime, timezone

import pytest

from slpy import slpy
from slpy.retention import (RetentionConfigurationError, RetentionPolicy,
                            RetentionPolicyNotFoundError, RetentionRegistry)


class CaptureTransport:
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
# Pure registry semantics
# ---------------------------------------------------------------------------

def test_empty_registry_resolves_nothing():
    assert RetentionRegistry.create(None).resolve("SOX") is None


def test_registry_resolves_case_insensitively():
    registry = RetentionRegistry.create({"SOX_AUDIT": {"years": 7, "class": "SOX"}})
    assert registry.resolve("sox_audit") == RetentionPolicy(years=7, klass="SOX")


def test_stamp_registered_name_carries_full_policy():
    registry = RetentionRegistry.create({"GDPR_ACCESS": {"days": 90, "class": "GDPR"}})
    assert registry.stamp("GDPR_ACCESS") == {
        "retention": "GDPR_ACCESS",
        "retention_class": "GDPR",
        "retention_days": 90,
    }


def test_stamp_unregistered_name_is_refused():
    """A name that resolves to nothing is a typo, and a typo that travels
    silently is a record persisted with no retention — found at audit time."""
    with pytest.raises(RetentionPolicyNotFoundError) as excinfo:
        RetentionRegistry.create({"GDPR_ACCESS": {"days": 90}}).require("GDPR_ACESS")
    assert "GDPR_ACESS" in str(excinfo.value)
    assert "GDPR_ACCESS" in str(excinfo.value)   # the message lists what IS registered


def test_empty_registry_says_none_are_registered():
    with pytest.raises(RetentionPolicyNotFoundError) as excinfo:
        RetentionRegistry.create({}).require("ANY")
    assert "No retention policies are registered" in str(excinfo.value)


def test_stamp_inline_policy_dict():
    assert RetentionRegistry.create({}).stamp({"days": 30, "class": "PCI"}) == {
        "retention_class": "PCI",
        "retention_days": 30,
    }


# ---------------------------------------------------------------------------
# End-to-end through the logger
# ---------------------------------------------------------------------------

async def test_with_retention_stamps_every_entry(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "retention_policies": {"SOX_AUDIT_TRAIL": {"days": 90, "class": "SOX"}},
    })
    audit = fresh_slpy.get_logger("payments").with_retention("SOX_AUDIT_TRAIL")
    audit.audit("Manager override", user_id="u-1")

    entry = spy.entries[0]
    assert entry["retention"] == "SOX_AUDIT_TRAIL"
    assert entry["retention_class"] == "SOX"
    assert entry["retention_days"] == 90   # days still travels when days is the unit
    assert entry["level"] == "audit"
    assert entry["user_id"] == "u-1"


async def test_retention_fields_bypass_the_matrix(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "logging_matrix": {"default": []},   # drop ALL context
        "retention_policies": {"GDPR_ACCESS": {"days": 90, "class": "GDPR"}},
    })
    logger = fresh_slpy.get_logger("svc").with_retention("GDPR_ACCESS")

    async with fresh_slpy.context(request_id="req-1"):
        logger.info("export")

    entry = spy.entries[0]
    assert "request_id" not in entry            # context dropped by matrix
    assert entry["retention"] == "GDPR_ACCESS"  # retention stamp survives
    assert entry["retention_days"] == 90


async def test_with_retention_composes_with_child_and_meta(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "retention_policies": {"PCI": {"days": 365, "class": "PCI-DSS"}},
    })
    logger = (
        fresh_slpy.get_logger("orders")
        .child(order_id="o-9")
        .with_retention("PCI")
        .with_meta({"regulation": "PCI-DSS"})
    )
    logger.audit("Card charged")

    entry = spy.entries[0]
    assert entry["order_id"] == "o-9"
    assert entry["retention_days"] == 365
    assert entry["meta"] == {"regulation": "PCI-DSS"}


# ---------------------------------------------------------------------------
# The registry is frozen — a compliance window cannot be redefined afterwards
# ---------------------------------------------------------------------------

def test_registry_ignores_source_mutation():
    """The caller keeps its dict. Editing it afterwards must not redefine a
    window for records already written under the old one."""
    source = {"GDPR": RetentionPolicy(days=90, klass="GDPR")}
    registry = RetentionRegistry(source)

    source["GDPR"] = RetentionPolicy(days=1, klass="GDPR")
    source["SNEAKED_IN"] = RetentionPolicy(days=1)

    assert registry.resolve("GDPR").days == 90
    assert registry.resolve("SNEAKED_IN") is None


def test_policies_view_is_read_only():
    registry = RetentionRegistry.create({"GDPR": {"days": 90}})
    with pytest.raises(TypeError):
        registry.policies["GDPR"] = RetentionPolicy(days=1)
    with pytest.raises(TypeError):
        registry.policies["NEW"] = RetentionPolicy(days=1)
    assert registry.resolve("GDPR").days == 90


def test_ambiguous_unit_is_refused_when_the_registry_is_built():
    with pytest.raises(RetentionConfigurationError) as excinfo:
        RetentionRegistry.create({"CONFUSED": {"days": 90, "years": 7}})
    assert "CONFUSED" in str(excinfo.value)
    assert "exactly one" in str(excinfo.value)


async def test_ambiguous_unit_refuses_to_start(fresh_slpy):
    """At startup, not from the logging path: an ambiguous window has no safe
    default, and a host that refuses to boot beats records swept on a date
    nobody chose."""
    with pytest.raises(RetentionConfigurationError):
        await fresh_slpy.init({
            "retention_policies": {"CONFUSED": {"months": 6, "years": 7}},
        })
    assert not fresh_slpy.is_initialized


# ---------------------------------------------------------------------------
# One policy, one label value
# ---------------------------------------------------------------------------

async def test_emits_the_registered_spelling(fresh_slpy):
    """Lookup is case-insensitive, but the field carries the canonical name.
    Downstream matches an exact string: the same policy arriving as SOX_AUDIT on
    some records and sox_audit on others means a sweep finds half of them."""
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "retention_policies": {"SOX_AUDIT": {"years": 7, "class": "SOX"}},
    })
    fresh_slpy.get_logger("a").with_retention("sox_audit").info("one")
    fresh_slpy.get_logger("b").with_retention("SOX_AUDIT").info("two")
    fresh_slpy.get_logger("c").with_retention("Sox_Audit").info("three")

    assert {e["retention"] for e in spy.entries} == {"SOX_AUDIT"}


async def test_unregistered_name_raises_where_the_logger_is_built(fresh_slpy):
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [CaptureTransport()]},
        "retention_policies": {"GDPR_ACCESS": {"days": 90}},
    })
    with pytest.raises(RetentionPolicyNotFoundError):
        fresh_slpy.get_logger("svc").with_retention("GDPR_ACESS")


async def test_logging_still_cannot_raise(fresh_slpy):
    """with_retention() may raise; a log call may not. The promise is unchanged."""
    class Exploding:
        def log(self, entry):
            raise RuntimeError("sink is down")

    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [Exploding()]},
        "retention_policies": {"GDPR_ACCESS": {"days": 90, "class": "GDPR"}},
    })
    logger = fresh_slpy.get_logger("svc").with_retention("GDPR_ACCESS")
    logger.info("this must not blow up")   # no raise
    assert fresh_slpy.get_stats().transport_failures == 1


# ---------------------------------------------------------------------------
# retention_until — materialized per entry, from that entry's own timestamp
# ---------------------------------------------------------------------------

class _FrozenClock:
    """Stands in for `datetime` inside slpy.logger, so the entry's instant is ours."""

    def __init__(self, at):
        self.at = at

    def now(self, tz=None):
        return self.at


async def test_until_anchors_to_the_entry_not_to_the_binding(fresh_slpy, monkeypatch):
    """The same logger, built once, logging on two different days: the window
    moves with the entry. A date frozen into the bindings at with_retention()
    time would stamp the startup date on records written months later."""
    import slpy.logger as logger_module

    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "retention_policies": {"OPS": {"years": 6, "class": "BCRA"}},
    })
    audit = fresh_slpy.get_logger("payments").with_retention("OPS")

    monkeypatch.setattr(logger_module, "datetime",
                        _FrozenClock(datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)))
    audit.info("filed in august")

    monkeypatch.setattr(logger_module, "datetime",
                        _FrozenClock(datetime(2027, 1, 15, 12, 0, tzinfo=timezone.utc)))
    audit.info("filed the following january")

    assert spy.entries[0]["retention_until"] == "2032-08-23"
    assert spy.entries[1]["retention_until"] == "2033-01-15"


async def test_until_matches_what_the_registry_answers(fresh_slpy, monkeypatch):
    """The out-of-logger API and the logging path must agree — same registry,
    same arithmetic, or a domain write path files a record under a different
    window than the log that records it."""
    import slpy.logger as logger_module

    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "retention_policies": {"OPS": {"months": 42, "class": "BCRA"}},
    })
    at = datetime(2026, 1, 31, 9, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(logger_module, "datetime", _FrozenClock(at))
    fresh_slpy.get_logger("svc").with_retention("OPS").audit("issued")

    from_registry = fresh_slpy._retention.until("OPS", at)
    assert spy.entries[0]["retention_until"] == from_registry.isoformat()
    assert spy.entries[0]["retention_until"] == "2029-07-31"


async def test_policy_without_a_unit_gets_no_date(fresh_slpy):
    """Nothing to compute, so nothing is written. The framework does not guess a
    date into a compliance column."""
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "retention_policies": {"LABEL_ONLY": {"class": "INTERNAL"}},
    })
    fresh_slpy.get_logger("svc").with_retention("LABEL_ONLY").info("tagged")

    entry = spy.entries[0]
    assert entry["retention"] == "LABEL_ONLY"
    assert entry["retention_class"] == "INTERNAL"
    assert "retention_until" not in entry
    assert "retention_days" not in entry   # declared in no unit: no day count invented


async def test_retention_until_bypasses_the_matrix(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "logging_matrix": {"default": []},   # drop ALL context
        "retention_policies": {"GDPR_ACCESS": {"months": 3, "class": "GDPR"}},
    })
    logger = fresh_slpy.get_logger("svc").with_retention("GDPR_ACCESS")
    async with fresh_slpy.context(request_id="req-1"):
        logger.info("export")

    entry = spy.entries[0]
    assert "request_id" not in entry
    assert entry["retention"] == "GDPR_ACCESS"
    assert "retention_until" in entry


async def test_a_kwarg_cannot_move_a_retention_date(fresh_slpy, monkeypatch):
    """Per-call kwargs win over bindings everywhere else. Not here: the
    framework owns this field, and a caller must not be able to hand-write the
    date a compliance sweep will read."""
    import slpy.logger as logger_module

    spy = CaptureTransport()
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [spy]},
        "retention_policies": {"OPS": {"years": 6}},
    })
    monkeypatch.setattr(logger_module, "datetime",
                        _FrozenClock(datetime(2026, 8, 23, tzinfo=timezone.utc)))
    fresh_slpy.get_logger("svc").with_retention("OPS").info("x", retention_until="1999-01-01")

    assert spy.entries[0]["retention_until"] == "2032-08-23"


async def test_inline_policy_gets_a_date_but_no_name(fresh_slpy, monkeypatch):
    """An inline dict has no name to route on, so nothing lands in `retention`
    — but the window is still computed."""
    import slpy.logger as logger_module

    spy = CaptureTransport()
    await fresh_slpy.init({"logger": {"level": "info", "transports": [spy]}})
    monkeypatch.setattr(logger_module, "datetime",
                        _FrozenClock(datetime(2026, 8, 23, tzinfo=timezone.utc)))
    fresh_slpy.get_logger("svc").with_retention({"months": 6, "class": "PCI"}).info("x")

    entry = spy.entries[0]
    assert "retention" not in entry
    assert entry["retention_class"] == "PCI"
    assert entry["retention_until"] == "2027-02-23"
