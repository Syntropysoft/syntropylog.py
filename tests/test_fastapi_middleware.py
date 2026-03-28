"""Tests for SyntropyMiddleware."""

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("httpx", reason="httpx not installed")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from slpy import slpy
from slpy.fastapi import SyntropyMiddleware
from slpy.transport import Transport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class CaptureTransport(Transport):
    def __init__(self):
        self.entries = []

    def log(self, entry):
        self.entries.append(entry)


def make_app(transport: CaptureTransport) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await slpy.init({
            "logger": {"level": "debug", "transports": [transport]},
        })
        yield
        await slpy.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(SyntropyMiddleware)

    @app.get("/ping")
    async def ping():
        slpy.get_logger("api").info("pong")
        return JSONResponse({"ok": True})

    @app.get("/orders/{order_id}")
    async def get_order(order_id: str):
        slpy.get_logger("api").info("fetching", order_id=order_id)
        return JSONResponse({"order_id": order_id})

    return app


# ---------------------------------------------------------------------------
# Context propagation
# ---------------------------------------------------------------------------

def test_correlation_id_added_to_logs():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        client.get("/ping")
    assert len(transport.entries) == 1
    assert "correlation_id" in transport.entries[0]


def test_method_added_to_logs():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        client.get("/ping")
    assert transport.entries[0]["method"] == "GET"


def test_path_added_to_logs():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        client.get("/ping")
    assert transport.entries[0]["path"] == "/ping"


def test_incoming_correlation_id_is_used():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        client.get("/ping", headers={"X-Correlation-ID": "my-id-123"})
    assert transport.entries[0]["correlation_id"] == "my-id-123"


def test_generated_correlation_id_when_no_header():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        client.get("/ping")
    cid = transport.entries[0]["correlation_id"]
    assert cid and len(cid) == 36  # UUID format


# ---------------------------------------------------------------------------
# Response header
# ---------------------------------------------------------------------------

def test_correlation_id_forwarded_in_response():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        resp = client.get("/ping", headers={"X-Correlation-ID": "fwd-test"})
    assert resp.headers["x-correlation-id"] == "fwd-test"


def test_generated_id_forwarded_in_response():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        resp = client.get("/ping")
    assert "x-correlation-id" in resp.headers
    assert len(resp.headers["x-correlation-id"]) == 36


# ---------------------------------------------------------------------------
# Per-request isolation
# ---------------------------------------------------------------------------

def test_each_request_gets_own_correlation_id():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        client.get("/ping")
        client.get("/ping")
    ids = [e["correlation_id"] for e in transport.entries]
    assert ids[0] != ids[1]


def test_path_params_logged_correctly():
    transport = CaptureTransport()
    with TestClient(make_app(transport)) as client:
        client.get("/orders/ORD-999")
    entry = transport.entries[0]
    assert entry["path"] == "/orders/ORD-999"
    assert entry["order_id"] == "ORD-999"
