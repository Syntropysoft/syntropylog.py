"""Safety boundary: sanitizer, on_log_failure hook, get_stats()."""

import pytest

from slpy import slpy
from slpy.sanitize import clean, clean_tree


class CaptureTransport:
    def __init__(self):
        self.entries = []

    def log(self, entry):
        self.entries.append(entry)


class BrokenTransport:
    def log(self, entry):
        raise RuntimeError("sink down")


@pytest.fixture
async def fresh_slpy():
    if slpy.is_initialized:
        await slpy.shutdown()
    yield slpy
    if slpy.is_initialized:
        await slpy.shutdown()


# ---------------------------------------------------------------------------
# Sanitizer — pure function semantics
# ---------------------------------------------------------------------------

def test_clean_string_returns_same_reference():
    value = "totally clean"
    assert clean(value) is value


def test_control_chars_are_stripped():
    assert clean("a\x00b\x07c\x7fd") == "abcd"


def test_ansi_csi_sequence_is_dropped_whole():
    assert clean("\x1b[31mred\x1b[0m") == "red"


def test_lone_esc_is_dropped():
    assert clean("a\x1bb") == "ab"


def test_newline_and_tab_are_stripped_from_values():
    # log-injection: a crafted value can't fake a second log line
    assert clean("line1\nfake-entry") == "line1fake-entry"


def test_clean_tree_walks_nested_and_keeps_clean_reference():
    dirty = {"a": "x\x1b[2Jy", "nested": {"b": ["ok", "bad\x00"]}}
    assert clean_tree(dirty) == {"a": "xy", "nested": {"b": ["ok", "bad"]}}
    pristine = {"a": "ok", "nested": {"b": ["fine"]}}
    assert clean_tree(pristine) is pristine


# ---------------------------------------------------------------------------
# End-to-end: sanitization applies before transports
# ---------------------------------------------------------------------------

async def test_entries_are_sanitized_before_transport(fresh_slpy):
    spy = CaptureTransport()
    await fresh_slpy.init({"logger": {"level": "info", "transports": [spy]}})
    fresh_slpy.get_logger("svc").info("hello\x1b[31m", user_agent="evil\nfake")
    entry = spy.entries[0]
    assert entry["message"] == "hello"
    assert entry["user_agent"] == "evilfake"


# ---------------------------------------------------------------------------
# on_log_failure + stats
# ---------------------------------------------------------------------------

async def test_broken_transport_is_isolated_and_reported(fresh_slpy):
    spy = CaptureTransport()
    failures = []
    await fresh_slpy.init({
        "logger": {
            "level": "info",
            "transports": [BrokenTransport(), spy],
            "on_log_failure": lambda exc, transport: failures.append((exc, transport)),
        },
    })
    fresh_slpy.get_logger("svc").info("still delivered")

    assert spy.entries[0]["message"] == "still delivered"   # healthy sink unaffected
    assert len(failures) == 1
    assert isinstance(failures[0][0], RuntimeError)


async def test_failure_hook_that_raises_never_breaks_logging(fresh_slpy):
    spy = CaptureTransport()

    def bad_hook(exc, transport):
        raise ValueError("hook is broken too")

    await fresh_slpy.init({
        "logger": {
            "level": "info",
            "transports": [BrokenTransport(), spy],
            "on_log_failure": bad_hook,
        },
    })
    fresh_slpy.get_logger("svc").info("survives")
    assert spy.entries[0]["message"] == "survives"


async def test_get_stats_counts_the_pipeline(fresh_slpy):
    await fresh_slpy.init({
        "logger": {"level": "info", "transports": [BrokenTransport()]},
    })
    logger = fresh_slpy.get_logger("svc")
    logger.info("one")
    logger.info("two")

    stats = fresh_slpy.get_stats()
    assert stats.logs_processed == 2
    assert stats.transport_failures == 2
    assert stats.masking_failures == 0
    assert stats.uptime_seconds >= 0
    assert isinstance(stats.native_active, bool)


async def test_get_stats_requires_init(fresh_slpy):
    with pytest.raises(RuntimeError):
        fresh_slpy.get_stats()
