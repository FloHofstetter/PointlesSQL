"""Unit tests for :func:`pointlessql.pql._update_delete`.

Two layers:

* Mocked-client tests — patch ``_get_table.sync`` and exercise the
  :func:`update_table` / :func:`delete_table_rows` entry points
  to verify storage-location resolution + error paths.
* Real-Delta integration — bootstrap a tiny Delta table on
  ``tmp_path``, run :meth:`PQL.update` / :meth:`PQL.delete`
  through the full primitive (no audit recorder, since
  ``agent_run_id`` is unset), and assert the deltalake metrics
  + actual row state.

Audit-emission coverage lives in
``tests/test_agent_run_audit.py``-style integration tests; we
avoid duplicating the operation_context plumbing here.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import deltalake
import pyarrow as pa
import pytest
from soyuz_catalog_client.models.table_info import TableInfo

from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.pql import PQL
from pointlessql.pql._update_delete import (
    _coerce_int,
    delete_table_rows,
    update_table,
)

_UD = "pointlessql.pql._update_delete"


# ---------------------------------------------------------------------
# Mocked-client paths
# ---------------------------------------------------------------------


class TestUpdateTableMocked:
    @patch(f"{_UD}._get_table")
    def test_missing_table_raises(self, mock_get: MagicMock) -> None:
        mock_get.sync.return_value = None
        with pytest.raises(CatalogNotFoundError, match="Table not found"):
            update_table(
                client=MagicMock(),
                full_name="cat.sch.missing",
                set_clause={"x": "1"},
                where=None,
                unreachable_msg="unreachable",
            )

    @patch(f"{_UD}._get_table")
    def test_empty_set_clause_raises(self, mock_get: MagicMock) -> None:
        mock_get.sync.return_value = TableInfo(
            storage_location="/tmp/x",
            name="t",
        )
        with pytest.raises(ValueError, match="set_clause must not be empty"):
            update_table(
                client=MagicMock(),
                full_name="cat.sch.t",
                set_clause={},
                where=None,
                unreachable_msg="unreachable",
            )


class TestDeleteTableRowsMocked:
    @patch(f"{_UD}._get_table")
    def test_missing_table_raises(self, mock_get: MagicMock) -> None:
        mock_get.sync.return_value = None
        with pytest.raises(CatalogNotFoundError, match="Table not found"):
            delete_table_rows(
                client=MagicMock(),
                full_name="cat.sch.missing",
                where="id = 1",
                unreachable_msg="unreachable",
            )


# ---------------------------------------------------------------------
# Real-Delta integration via PQL façade (no agent_run_id → no audit emission)
# ---------------------------------------------------------------------


def _bootstrap_delta(target: Path) -> None:
    """Write a small Delta table with three rows + CDF on."""
    rows = pa.table(
        {
            "id": [1, 2, 3],
            "name": ["alice", "bob", "carol"],
            "country": ["AT", "DE", "AT"],
        }
    )
    deltalake.write_deltalake(
        str(target),
        rows,
        configuration={"delta.enableChangeDataFeed": "true"},
    )


@patch(f"{_UD}._get_table")
def test_update_changes_rows(mock_get: MagicMock, tmp_path: Path) -> None:
    target = tmp_path / "customers"
    _bootstrap_delta(target)
    mock_get.sync.return_value = TableInfo(storage_location=str(target), name="customers")

    pql = PQL(client=MagicMock())
    stats = pql.update(
        "main.silver.customers",
        set_clause={"country": "'XX'"},
        where="country = 'AT'",
    )

    assert stats["num_updated_rows"] == 2
    final_rows = deltalake.DeltaTable(str(target)).to_pandas().sort_values("id")
    countries = final_rows["country"].tolist()
    assert countries == ["XX", "DE", "XX"]


@patch(f"{_UD}._get_table")
def test_update_with_no_where_updates_all_rows(
    mock_get: MagicMock, tmp_path: Path
) -> None:
    target = tmp_path / "customers"
    _bootstrap_delta(target)
    mock_get.sync.return_value = TableInfo(storage_location=str(target), name="customers")

    pql = PQL(client=MagicMock())
    stats = pql.update(
        "main.silver.customers",
        set_clause={"country": "'GLOBAL'"},
    )

    assert stats["num_updated_rows"] == 3
    final_rows = deltalake.DeltaTable(str(target)).to_pandas()
    assert set(final_rows["country"]) == {"GLOBAL"}


@patch(f"{_UD}._get_table")
def test_delete_with_predicate(mock_get: MagicMock, tmp_path: Path) -> None:
    target = tmp_path / "customers"
    _bootstrap_delta(target)
    mock_get.sync.return_value = TableInfo(storage_location=str(target), name="customers")

    pql = PQL(client=MagicMock())
    # delta-rs reports `num_deleted_rows: 0` with CDF on (it re-writes
    # every file and tracks the delete only as a CDF entry).  Assert
    # on the post-state which is what users actually care about.
    stats = pql.delete("main.silver.customers", where="country = 'DE'")
    assert "num_deleted_rows" in stats

    remaining = deltalake.DeltaTable(str(target)).to_pandas()
    assert "DE" not in set(remaining["country"])
    assert len(remaining) == 2


@patch(f"{_UD}._get_table")
def test_delete_without_where_clears_table(
    mock_get: MagicMock, tmp_path: Path
) -> None:
    target = tmp_path / "customers"
    _bootstrap_delta(target)
    mock_get.sync.return_value = TableInfo(storage_location=str(target), name="customers")

    pql = PQL(client=MagicMock())
    pql.delete("main.silver.customers")

    remaining = deltalake.DeltaTable(str(target)).to_pandas()
    assert len(remaining) == 0


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (0, 0),
        (5, 5),
        ("7", 7),
        ("not-a-number", None),
        (object(), None),
    ],
)
def test_coerce_int(value: object, expected: int | None) -> None:
    assert _coerce_int(value) == expected
