"""Retention policies — registry + with_retention() stamping."""

import pytest

from slpy import slpy
from slpy.retention import RetentionPolicy, RetentionRegistry


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
    registry = RetentionRegistry.create({"SOX_AUDIT": {"days": 2555, "class": "SOX"}})
    assert registry.resolve("sox_audit") == RetentionPolicy(days=2555, klass="SOX")


def test_stamp_registered_name_carries_full_policy():
    registry = RetentionRegistry.create({"GDPR_ACCESS": {"days": 90, "class": "GDPR"}})
    assert registry.stamp("GDPR_ACCESS") == {
        "retention": "GDPR_ACCESS",
        "retention_class": "GDPR",
        "retention_days": 90,
    }


def test_stamp_unregistered_name_still_travels():
    assert RetentionRegistry.create({}).stamp("UNKNOWN") == {"retention": "UNKNOWN"}


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
        "retention_policies": {"SOX_AUDIT_TRAIL": {"days": 2555, "class": "SOX"}},
    })
    audit = fresh_slpy.get_logger("payments").with_retention("SOX_AUDIT_TRAIL")
    audit.audit("Manager override", user_id="u-1")

    entry = spy.entries[0]
    assert entry["retention"] == "SOX_AUDIT_TRAIL"
    assert entry["retention_class"] == "SOX"
    assert entry["retention_days"] == 2555
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
