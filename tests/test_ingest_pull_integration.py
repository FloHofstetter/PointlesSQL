"""In-process integration tests for the ``pull_mapping`` shell.

Drives the orchestrator end-to-end against a real in-memory DuckDB
reading a temp CSV, with a fake PQL recording the write plane.  These
exercise the wiring the pure ``_pull_logic`` decisions feed into: the
DuckDB read, the high-water MAX query, and the write-strategy dispatch.
No live server — runs in the default suite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pointlessql.services.ingest.pull import PullResult, pull_mapping


class _FakePQL:
    """Records ``write_table`` / ``merge`` calls instead of writing Delta."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any], int]] = []

    def write_table(self, df: Any, fqn: str, **kwargs: Any) -> None:
        self.calls.append(("write_table", fqn, kwargs, len(df)))

    def merge(self, df: Any, fqn: str, **kwargs: Any) -> None:
        self.calls.append(("merge", fqn, kwargs, len(df)))


def _csv(tmp_path: Path) -> str:
    """Write a 3-row CSV with an integer high-water column."""
    p = tmp_path / "src.csv"
    p.write_text("id,name\n1,a\n2,b\n3,c\n")
    return str(p)


def _pull(csv_path: str, mapping: dict[str, Any]) -> tuple[PullResult, _FakePQL]:
    pql = _FakePQL()
    result = pull_mapping(
        kind="file_upload",
        config={"path": csv_path},
        secrets={},
        mapping=mapping,
        pql_instance=pql,
    )
    return result, pql


def test_full_pull_overwrites_all_rows(tmp_path: Path) -> None:
    result, pql = _pull(_csv(tmp_path), {"target_fqn": "c.s.t", "mode": "full"})

    assert result.mode == "full"
    assert result.rows_written == 3
    assert result.new_high_water_value is None
    assert pql.calls == [("write_table", "c.s.t", {"mode": "overwrite"}, 3)]


def test_incremental_first_pull_bootstraps_with_overwrite(tmp_path: Path) -> None:
    result, pql = _pull(
        _csv(tmp_path),
        {
            "target_fqn": "c.s.t",
            "mode": "incremental",
            "high_water_col": "id",
            "last_high_water_value": None,
        },
    )

    # No watermark yet → full write_table, and the new watermark is the
    # MAX of the column.
    assert result.rows_written == 3
    assert result.new_high_water_value == "3"
    assert pql.calls == [("write_table", "c.s.t", {"mode": "overwrite"}, 3)]


def test_incremental_delta_merges_only_new_rows(tmp_path: Path) -> None:
    result, pql = _pull(
        _csv(tmp_path),
        {
            "target_fqn": "c.s.t",
            "mode": "incremental",
            "high_water_col": "id",
            "last_high_water_value": "1",
        },
    )

    # Only id > 1 (rows 2 and 3) qualify, merged on the watermark column.
    assert result.rows_written == 2
    assert result.new_high_water_value == "3"
    assert pql.calls == [("merge", "c.s.t", {"on": ["id"], "strategy": "upsert"}, 2)]


def test_incremental_empty_window_keeps_previous_watermark(tmp_path: Path) -> None:
    result, pql = _pull(
        _csv(tmp_path),
        {
            "target_fqn": "c.s.t",
            "mode": "incremental",
            "high_water_col": "id",
            "last_high_water_value": "999",
        },
    )

    # Nothing newer than 999 → empty merge, watermark unchanged.
    assert result.rows_written == 0
    assert result.new_high_water_value == "999"
    assert pql.calls == [("merge", "c.s.t", {"on": ["id"], "strategy": "upsert"}, 0)]


def test_missing_path_surfaces_pull_error(tmp_path: Path) -> None:
    from pointlessql.services.ingest.pull import PullError

    pql = _FakePQL()
    with pytest.raises(PullError):
        pull_mapping(
            kind="file_upload",
            config={},  # no 'path'
            secrets={},
            mapping={"target_fqn": "c.s.t", "mode": "full"},
            pql_instance=pql,
        )
    assert pql.calls == []
