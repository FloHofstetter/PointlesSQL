"""Overflow mutation-killing tests for ``pql.aggregate``.

The primary suite (``test_pql_aggregate_mutkill.py``) is already past
the per-file budget, so this round's new case lives here.  It pins the
``unreachable_msg`` argument that ``aggregate_table`` forwards into
:func:`pointlessql.pql._aggregate._resolve_or_plan_target` — a value
that only surfaces when the catalog get-table hop fails to connect, a
path the round-1 ``_resolve_or_plan_target`` direct test never reached
through the end-to-end primitive.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import httpx
import pandas as pd
import pytest

from pointlessql.pql import _aggregate as agg
from pointlessql.services.agent_runs.operations._common import OperationRecorder

if TYPE_CHECKING:
    from collections.abc import Iterator


class _NoopEngine:
    """Engine stub whose write/columns hops are never reached here."""

    def write(self, frame: Any, location: str, mode: str) -> None:  # noqa: D102
        raise AssertionError("write must not run when the get hop fails")

    def columns_info(self, frame: Any) -> list[tuple[str, str, str, bool]]:  # noqa: D102
        raise AssertionError("columns_info must not run when the get hop fails")


def test_aggregate_forwards_unreachable_msg_into_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A get-table connect error must surface the *forwarded* unreachable_msg.

    ``aggregate_table`` calls ``_resolve_or_plan_target(...,
    unreachable_msg=unreachable_msg)``.  When the catalog get-table hop
    raises ``httpx.ConnectError`` the resolver re-raises
    ``CatalogUnavailableError(unreachable_msg)``.  If the primitive
    passed ``None`` for that argument instead of the real message the
    surfaced error would stringify to ``"None"``; pinning the exact
    text proves the caller-supplied message flows through.
    """
    from pointlessql.exceptions import CatalogUnavailableError

    class _FakeGetRaises:
        @staticmethod
        def sync(*, client: Any, full_name: str) -> Any:
            raise httpx.ConnectError("no route")

    monkeypatch.setattr(agg, "_get_table", _FakeGetRaises)

    @contextlib.contextmanager
    def _fake_ctx(
        factory: Any,
        *,
        agent_run_id: Any,
        op_name: Any,
        params: dict[str, Any],
        target_table: str | None = None,
    ) -> Iterator[OperationRecorder]:
        yield OperationRecorder()

    monkeypatch.setattr(agg, "operation_context", _fake_ctx)
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: object(), raising=False)

    df = pd.DataFrame({"k": ["a"], "amount": [1]})
    with pytest.raises(CatalogUnavailableError) as ei:
        agg.aggregate_table(
            client=object(),
            engine=_NoopEngine(),
            source_df=df,
            target="main.gold.t",
            group_by=["k"],
            aggs={"total": ("amount", "sum")},
            source_table_fqn="main.silver.src",
            unreachable_msg="aggregate cannot reach the catalog right now",
            agent_run_id=None,
        )
    assert str(ei.value) == "aggregate cannot reach the catalog right now"
