"""Tests for ContextManager — contextvars propagation."""

import asyncio
import pytest
from slpy.context import ContextManager


@pytest.fixture
def ctx():
    return ContextManager()


async def test_scope_sets_and_clears(ctx):
    assert ctx.get() == {}
    async with ctx.scope(user_id="123"):
        assert ctx.get()["user_id"] == "123"
    assert ctx.get() == {}


async def test_nested_scopes(ctx):
    async with ctx.scope(request_id="req-1"):
        assert ctx.get()["request_id"] == "req-1"
        async with ctx.scope(user_id="usr-1"):
            data = ctx.get()
            assert data["request_id"] == "req-1"
            assert data["user_id"] == "usr-1"
        # inner scope closed — user_id gone, request_id still there
        assert ctx.get()["request_id"] == "req-1"
        assert "user_id" not in ctx.get()
    assert ctx.get() == {}


async def test_concurrent_scopes_are_isolated(ctx):
    results = {}

    async def task(name: str, value: str):
        async with ctx.scope(**{name: value}):
            await asyncio.sleep(0)  # yield to let other task run
            results[name] = ctx.get().get(name)

    await asyncio.gather(
        task("user_a", "Alice"),
        task("user_b", "Bob"),
    )

    assert results["user_a"] == "Alice"
    assert results["user_b"] == "Bob"


async def test_scope_does_not_leak_to_outer(ctx):
    async with ctx.scope(outer="yes"):
        async with ctx.scope(inner="yes"):
            pass
        assert "inner" not in ctx.get()
        assert ctx.get()["outer"] == "yes"


async def test_scope_propagates_to_nested_coroutine(ctx):
    async def nested():
        return ctx.get().get("request_id")

    async with ctx.scope(request_id="abc-123"):
        value = await nested()

    assert value == "abc-123"
