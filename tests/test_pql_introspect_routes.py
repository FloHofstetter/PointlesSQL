"""Tests for the Sprint 13.11.1 PQL introspection endpoints."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_primitives_returns_five_entries_with_signature_and_doc(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/pql/primitives")
    assert response.status_code == 200, response.text
    payload = response.json()
    primitives = payload["primitives"]
    assert set(primitives.keys()) == {
        "table",
        "sql",
        "write_table",
        "merge",
        "autoload",
    }
    for name, entry in primitives.items():
        assert entry["name"] == name
        # Signatures begin with the method name and include parens —
        # exact text varies between Python versions, but those two
        # invariants are stable.
        assert entry["signature"].startswith(f"{name}(")
        assert ")" in entry["signature"]
        # The Google-style docstrings every primitive carries.
        assert "Args:" in entry["doc"]


@pytest.mark.asyncio
async def test_autoload_signature_carries_source_path_kwarg(admin_client: httpx.AsyncClient) -> None:
    """Regression test for the live-walkthrough bug.

    The 2026-04-25 demo failed because the human reviewer typed
    ``pql.autoload(source=...)`` instead of ``source_path=...``.
    The whole point of ``pql_describe_primitive`` is to surface
    the real kwarg name to a confused agent — so make sure the
    signature we return contains it.
    """
    response = await admin_client.get("/api/pql/primitives")
    assert response.status_code == 200
    autoload = response.json()["primitives"]["autoload"]
    assert "source_path" in autoload["signature"]
    # And the prose contract is in the doc, not just the type.
    assert "source_path" in autoload["doc"]
