"""Mutation-kill tests for ``pointlessql.pql.context``.

Pins the ``agent_run_id`` write in ``_set_context`` — the value, the dict
key, and the ``or None`` normalisation — which the suite executed but did
not detect mutations in.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pointlessql.pql import context as ctx


@pytest.fixture
def _restore_ctx() -> Iterator[None]:
    """Snapshot and restore the module-global context dict around a test."""
    saved = dict(ctx._CTX)
    yield
    ctx._CTX.clear()
    ctx._CTX.update(saved)


@pytest.mark.usefixtures("_restore_ctx")
def test_set_context_round_trips_agent_run_id() -> None:
    """``_set_context`` stores agent_run_id under its exact key and value."""
    # kills _CTX["agent_run_id"] = None / wrong-key / `agent_run_id and None`
    ctx._set_context(branch="b1", notebook_id="n1", agent_run_id="r1")
    snap = ctx.snapshot()
    assert snap["agent_run_id"] == "r1"
    assert snap["branch"] == "b1"
    assert snap["notebook_id"] == "n1"
