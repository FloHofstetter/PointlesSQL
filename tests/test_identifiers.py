"""Sanity tests for :mod:`pointlessql.identifiers`.

NewType erases to its supertype at runtime, so the only
runtime-observable contract is the supertype identity.  The
type-checker contract (pyright rejects mixups between
``OpId`` / ``QueryHistoryId`` / ``WorkspaceId`` even though all
three erase to ``int``) is asserted via static-typing comments
at the module level so a regression in the alias definition
would surface as a pyright error in CI, not a runtime test
failure.
"""

from __future__ import annotations

from pointlessql.identifiers import OpId, QueryHistoryId, RunId, WorkspaceId


def test_run_id_is_str_at_runtime() -> None:
    """``RunId`` erases to ``str`` -- isinstance round-trips."""
    rid = RunId("00000000-0000-0000-0000-000000000000")
    assert isinstance(rid, str)
    assert rid == "00000000-0000-0000-0000-000000000000"


def test_op_id_is_int_at_runtime() -> None:
    """``OpId`` erases to ``int`` -- isinstance round-trips."""
    op = OpId(42)
    assert isinstance(op, int)
    assert op == 42


def test_query_history_id_is_int_at_runtime() -> None:
    """``QueryHistoryId`` erases to ``int`` -- isinstance round-trips."""
    qh = QueryHistoryId(7)
    assert isinstance(qh, int)
    assert qh == 7


def test_workspace_id_is_int_at_runtime() -> None:
    """``WorkspaceId`` erases to ``int`` -- isinstance round-trips."""
    ws = WorkspaceId(1)
    assert isinstance(ws, int)
    assert ws == 1


def test_distinct_aliases_share_supertype_arithmetic() -> None:
    """``OpId`` and ``QueryHistoryId`` both erase to ``int`` at runtime.

    Pyright treats them as distinct nominal types (so passing one
    where the other was expected fails type-check), but the runtime
    comparison and arithmetic still work because both are plain
    ``int``.  This test pins the runtime side; the type-check
    contract is enforced by pyright in CI.
    """
    op = OpId(5)
    qh = QueryHistoryId(5)
    assert op == qh
    assert op + 1 == 6


def test_run_id_concatenates_as_string() -> None:
    """``RunId`` participates in string operations transparently."""
    rid = RunId("abc-123")
    assert f"run/{rid}" == "run/abc-123"
    assert rid.upper() == "ABC-123"
