"""Mutation-kill tests for ``pointlessql.pql._hooks.run_after_read``."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from pointlessql.pql import _hooks


@pytest.fixture
def _clean_after_read() -> Iterator[None]:
    """Save/restore the module-global after-read hook registry."""
    saved = list(_hooks._after_read)
    _hooks._after_read.clear()
    yield
    _hooks._after_read.clear()
    _hooks._after_read.extend(saved)


@pytest.mark.usefixtures("_clean_after_read")
def test_run_after_read_passes_context_to_each_hook() -> None:
    """Each after-read hook receives the real context dict, not ``None``."""
    # kills hook(current, context) -> hook(current, None)
    seen: dict[str, Any] = {}

    def hook(frame: Any, context: dict[str, Any]) -> None:
        seen["context"] = context
        return None

    _hooks.register_after_read(hook)
    ctx = {"branch": "b1"}
    _hooks.run_after_read("frame", ctx)
    assert seen["context"] == ctx
