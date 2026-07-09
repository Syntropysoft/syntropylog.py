"""DurableFileTransport — self-emptying disk spool with restart recovery."""

import json
import os

from slpy import DurableFileTransport


class FlakySink:
    """Inner transport that fails while .down is True."""

    def __init__(self, down: bool = False):
        self.down = down
        self.delivered = []

    def log(self, entry):
        if self.down:
            raise RuntimeError("sink down")
        self.delivered.append(entry)


def _spool(tmp_path):
    return str(tmp_path / "spool.jsonl")


def test_happy_path_never_touches_disk(tmp_path):
    sink = FlakySink()
    durable = DurableFileTransport(sink, _spool(tmp_path))
    durable.log({"message": "one"})
    durable.log({"message": "two"})
    assert [e["message"] for e in sink.delivered] == ["one", "two"]
    assert not os.path.exists(_spool(tmp_path))


def test_outage_spools_to_disk_in_order(tmp_path):
    sink = FlakySink(down=True)
    durable = DurableFileTransport(sink, _spool(tmp_path))
    durable.log({"message": "one"})
    durable.log({"message": "two"})

    assert sink.delivered == []
    lines = open(_spool(tmp_path)).read().splitlines()
    assert [json.loads(l)["message"] for l in lines] == ["one", "two"]


def test_recovery_drains_in_order_and_deletes_spool(tmp_path):
    sink = FlakySink(down=True)
    durable = DurableFileTransport(sink, _spool(tmp_path))
    durable.log({"message": "one"})
    durable.log({"message": "two"})

    sink.down = False
    durable.log({"message": "three"})   # next log probes recovery and drains

    assert [e["message"] for e in sink.delivered] == ["one", "two", "three"]
    assert not os.path.exists(_spool(tmp_path))


def test_restart_recovers_leftover_spool(tmp_path):
    down = FlakySink(down=True)
    durable = DurableFileTransport(down, _spool(tmp_path))
    durable.log({"message": "pre-crash"})
    assert os.path.exists(_spool(tmp_path))

    # "restart": a new instance over the same spool, sink healthy again
    healthy = FlakySink()
    DurableFileTransport(healthy, _spool(tmp_path))

    assert [e["message"] for e in healthy.delivered] == ["pre-crash"]
    assert not os.path.exists(_spool(tmp_path))


def test_partial_progress_rewrites_remainder(tmp_path):
    class FailsOnSecond:
        def __init__(self):
            self.delivered = []

        def log(self, entry):
            if entry["message"] == "two":
                raise RuntimeError("still flaky")
            self.delivered.append(entry)

    sink = FlakySink(down=True)
    durable = DurableFileTransport(sink, _spool(tmp_path))
    durable.log({"message": "one"})
    durable.log({"message": "two"})

    durable._inner = FailsOnSecond()    # delivers 'one', chokes on 'two'
    durable.log({"message": "three"})

    lines = open(_spool(tmp_path)).read().splitlines()
    assert [json.loads(l)["message"] for l in lines] == ["two", "three"]


def test_non_json_values_are_stringified_not_lost(tmp_path):
    sink = FlakySink(down=True)
    durable = DurableFileTransport(sink, _spool(tmp_path))
    durable.log({"message": "x", "weird": {1, 2}})   # a set is not JSON

    sink.down = False
    durable.log({"message": "y"})
    assert len(sink.delivered) == 2
    assert isinstance(sink.delivered[0]["weird"], str)


def test_iso_timestamp_format():
    from slpy.logger import _iso_timestamp
    ts = _iso_timestamp()
    from datetime import datetime
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
    assert "." in ts    # millisecond precision present
