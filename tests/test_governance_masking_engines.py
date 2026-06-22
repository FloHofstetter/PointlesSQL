"""Masking-sidecar coverage for the non-pandas frames and fail-closed cells.

``mask_dataframe`` duck-types the query engines: pandas directly, then
anything exposing ``to_pandas`` (polars, pyarrow) or ``df`` (duckdb), and
returns the frame untouched when it can read neither.  ``mask_cell`` is the
fail-closed core — an unknown strategy must raise rather than leak
cleartext, and ``hash`` with no secret must redact rather than pass through.

These exercise those engine adapters and the fail-closed guards directly,
without standing up a route, so a regression in either is caught at the
unit boundary.
"""

from __future__ import annotations

from typing import Any

import pytest

from pointlessql.services.governance import _masking
from pointlessql.services.pii._redactor import REDACTED_PLACEHOLDER

_STRATEGIES = {"email": "partial"}
_MASKED_EMAIL = "***@***.***"


def _assert_email_masked(pdf: Any) -> None:
    """Assert a returned pandas frame has the email column masked, age clear."""
    assert pdf["email"].tolist() == [_MASKED_EMAIL]
    assert pdf["age"].tolist() == [30]


def test_mask_dataframe_polars_via_to_pandas() -> None:
    """A polars frame is read through ``to_pandas`` and comes back masked."""
    pl = pytest.importorskip("polars")
    frame = pl.DataFrame({"email": ["alice@example.com"], "age": [30]})

    out = _masking.mask_dataframe(frame, _STRATEGIES, unmask=False, secret="s")

    _assert_email_masked(out)


def test_mask_dataframe_pyarrow_via_to_pandas() -> None:
    """A pyarrow table is read through ``to_pandas`` and comes back masked."""
    pa = pytest.importorskip("pyarrow")
    frame = pa.table({"email": ["alice@example.com"], "age": [30]})

    out = _masking.mask_dataframe(frame, _STRATEGIES, unmask=False, secret="s")

    _assert_email_masked(out)


def test_mask_dataframe_duckdb_via_df() -> None:
    """A duckdb relation (``df`` only, no ``to_pandas``) comes back masked."""
    duckdb = pytest.importorskip("duckdb")
    rel = duckdb.sql("SELECT 'alice@example.com' AS email, 30 AS age")
    # The ``.df()`` branch is the one under test — guard the assumption that
    # a duckdb relation does not also expose ``to_pandas`` (which would route
    # it through the other branch instead).
    assert not hasattr(rel, "to_pandas")

    out = _masking.mask_dataframe(rel, _STRATEGIES, unmask=False, secret="s")

    _assert_email_masked(out)


def test_mask_dataframe_unknown_frame_returned_unchanged() -> None:
    """A frame exposing neither ``to_pandas`` nor ``df`` is passed through."""

    class _Opaque:
        columns = ["email"]

    frame = _Opaque()

    out = _masking.mask_dataframe(frame, _STRATEGIES, unmask=False, secret="s")

    assert out is frame


def test_mask_cell_unknown_strategy_fails_closed() -> None:
    """An unrecognised strategy raises rather than returning cleartext."""
    with pytest.raises(ValueError, match="unknown masking strategy"):
        _masking.mask_cell("alice@example.com", "bogus_strategy", secret="s")


def test_mask_cell_hash_without_secret_redacts() -> None:
    """``hash`` with no secret redacts instead of leaking cleartext."""
    out = _masking.mask_cell("alice@example.com", "hash", secret=None)

    assert out == REDACTED_PLACEHOLDER
