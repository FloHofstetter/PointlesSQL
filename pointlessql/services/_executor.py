"""App-owned thread pool for the request layer's sync/async bridge.

Routes used to dispatch blocking work (PQL reads, audit writes, ORM
queries) through ``asyncio.to_thread``, which submits into asyncio's
per-loop *default* executor — shared with every other ``to_thread``
caller in the process and sized only by Python's heuristic.  This
module gives the application one explicitly owned, settings-sized pool
plus a :func:`run_sync` helper, so request-path latency is isolated
from background work and operators can bound the thread count.

The pool is bound by the FastAPI lifespan via :func:`bind_app_executor`
(single-slot pattern, mirroring the co-edit bus binding).  When no
pool is bound — bare ``httpx.ASGITransport`` test clients and the
fast-test lifespan never run the production startup — :func:`run_sync`
falls back to the loop default executor, which is byte-for-byte the
behaviour ``asyncio.to_thread`` had.

ContextVar propagation is preserved exactly like ``asyncio.to_thread``
does it: the calling context (request id, correlation id, job/task
ids from :mod:`pointlessql.config`) is copied and entered inside the
worker thread.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

# Single-slot mutable binding so the lifespan can swap the pool in and
# out without consumers importing app state.
_executor_slot: list[ThreadPoolExecutor | None] = [None]


def bind_app_executor(executor: ThreadPoolExecutor | None) -> None:
    """Bind (or with ``None`` unbind) the process-wide request pool.

    Args:
        executor: The lifespan-owned pool, or ``None`` on teardown.
    """
    _executor_slot[0] = executor


def get_app_executor() -> ThreadPoolExecutor | None:
    """Return the bound request pool, or ``None`` when unbound.

    Returns:
        The pool installed by the lifespan, or ``None`` outside it.
    """
    return _executor_slot[0]


async def run_sync[**P, T](func: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> T:
    """Run a blocking callable on the app executor without blocking the loop.

    Drop-in replacement for ``asyncio.to_thread`` on the request path:
    same signature, same ContextVar propagation (the CPython recipe
    with the pool swapped), but the work lands on the app-owned pool
    when one is bound instead of the shared loop default.

    Args:
        func: The blocking callable.
        *args: Positional arguments for *func*.
        **kwargs: Keyword arguments for *func*.

    Returns:
        Whatever *func* returns.
    """
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    call = functools.partial(ctx.run, functools.partial(func, *args, **kwargs))
    return await loop.run_in_executor(get_app_executor(), call)
