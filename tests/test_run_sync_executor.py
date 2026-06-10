"""Tests for the app-owned executor behind ``run_sync``."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from pointlessql.config import request_id_var
from pointlessql.services._executor import (
    bind_app_executor,
    get_app_executor,
    run_sync,
)


@pytest.fixture
def bound_executor():
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pql-test-exec")
    previous = get_app_executor()
    bind_app_executor(pool)
    yield pool
    bind_app_executor(previous)
    pool.shutdown(wait=True)


@pytest.mark.asyncio
async def test_result_and_kwargs_passthrough(bound_executor: ThreadPoolExecutor) -> None:
    def add(a: int, *, b: int) -> int:
        return a + b

    assert await run_sync(add, 2, b=40) == 42


@pytest.mark.asyncio
async def test_exception_passthrough(bound_executor: ThreadPoolExecutor) -> None:
    def boom() -> None:
        raise ValueError("expected")

    with pytest.raises(ValueError, match="expected"):
        await run_sync(boom)


@pytest.mark.asyncio
async def test_runs_on_the_bound_pool(bound_executor: ThreadPoolExecutor) -> None:
    name = await run_sync(lambda: threading.current_thread().name)
    assert name.startswith("pql-test-exec")


@pytest.mark.asyncio
async def test_contextvars_propagate_like_to_thread() -> None:
    """The hard constraint: request-scoped log correlation must survive.

    ``run_sync`` must behave exactly like ``asyncio.to_thread`` for
    ContextVar propagation — the value set in the request context must
    be visible inside the worker thread, bound pool or not.
    """
    token = request_id_var.set("req-ctx-check")
    try:
        control = await asyncio.to_thread(request_id_var.get)
        unbound = await run_sync(request_id_var.get)
        pool = ThreadPoolExecutor(max_workers=1)
        previous = get_app_executor()
        bind_app_executor(pool)
        try:
            bound = await run_sync(request_id_var.get)
        finally:
            bind_app_executor(previous)
            pool.shutdown(wait=True)
        assert control == unbound == bound == "req-ctx-check"
    finally:
        request_id_var.reset(token)


@pytest.mark.asyncio
async def test_unbound_falls_back_to_default_pool() -> None:
    previous = get_app_executor()
    bind_app_executor(None)
    try:
        assert get_app_executor() is None
        # Default-pool threads carry asyncio's name prefix, proving the
        # fallback path is the loop default executor (= old to_thread).
        name = await run_sync(lambda: threading.current_thread().name)
        assert name.startswith("asyncio")
    finally:
        bind_app_executor(previous)


def test_lifespan_binds_and_unbinds_the_pool() -> None:
    """The production lifespan must install and tear down the binding."""
    import httpx

    from pointlessql.api.main import app

    async def _exercise() -> tuple[str, object]:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://t"
            ):
                pool = get_app_executor()
                assert pool is not None
                inside = await run_sync(lambda: threading.current_thread().name)
        return inside, get_app_executor()

    inside_name, after = asyncio.run(_exercise())
    assert inside_name.startswith("pql-app-exec")
    assert after is None
