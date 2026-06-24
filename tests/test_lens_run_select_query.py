"""Test the public ``run_select_query`` wrapper over the gated executor."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.services.lens.tools import query as query_mod


@pytest.mark.asyncio
async def test_run_select_query_forwards_sql_and_limit(monkeypatch: Any) -> None:
    """The wrapper builds QueryArgs(sql, limit) and forwards to the executor."""
    captured: dict[str, Any] = {}

    async def fake_exec(ctx: Any, args: Any) -> query_mod.QueryResult:
        captured["sql"] = args.sql
        captured["limit"] = args.limit
        return query_mod.QueryResult(executed_sql=args.sql)

    monkeypatch.setattr(query_mod, "_execute_query", fake_exec)
    result = await query_mod.run_select_query(SimpleNamespace(), "SELECT 1", limit=7)  # type: ignore[arg-type]

    assert captured == {"sql": "SELECT 1", "limit": 7}
    assert result.executed_sql == "SELECT 1"

    # the default limit (None) is forwarded too
    await query_mod.run_select_query(SimpleNamespace(), "SELECT 2")  # type: ignore[arg-type]
    assert captured == {"sql": "SELECT 2", "limit": None}
