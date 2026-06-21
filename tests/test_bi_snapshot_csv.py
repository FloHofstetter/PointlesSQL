"""Tests for the BI-snapshot CSV serialiser."""

from __future__ import annotations

import csv
import io

from pointlessql.services import bi_snapshot_csv


def _parse(csv_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


def test_serialises_data_widgets_and_skips_others() -> None:
    payload = {
        "title": "Sales",
        "widgets": [
            {
                "widget_id": 1,
                "kind": "table",
                "title": "Orders",
                "columns": ["region", "total"],
                "rows": [["EU", 10], ["US", 20]],
            },
            {"widget_id": 2, "kind": "markdown", "title": "Notes", "columns": None, "rows": None},
            {
                "widget_id": 3,
                "kind": "chart",
                "title": "Broken",
                "error": "boom",
                "columns": None,
                "rows": None,
            },
        ],
    }
    out = bi_snapshot_csv.snapshot_to_csv(payload)
    parsed = _parse(out)
    assert ["# Orders"] in parsed
    assert ["region", "total"] in parsed
    assert ["EU", "10"] in parsed
    # The markdown + errored widgets carry no tabular data, so they are absent.
    assert "Notes" not in out
    assert "boom" not in out


def test_escapes_and_handles_nulls() -> None:
    payload = {
        "widgets": [
            {
                "widget_id": 1,
                "title": "T",
                "columns": ["name", "note"],
                "rows": [["a,b", None], ['has "quote"', "x"]],
            }
        ]
    }
    out = bi_snapshot_csv.snapshot_to_csv(payload)
    parsed = _parse(out)
    # csv quoting round-trips the comma + quote, and None becomes empty.
    assert ["a,b", ""] in parsed
    assert ['has "quote"', "x"] in parsed


def test_dict_columns_and_empty_payload() -> None:
    payload = {
        "widgets": [{"widget_id": 1, "title": "T", "columns": [{"name": "id"}], "rows": [[1]]}]
    }
    assert ["id"] in _parse(bi_snapshot_csv.snapshot_to_csv(payload))
    assert bi_snapshot_csv.snapshot_to_csv({"widgets": []}) == ""
    assert bi_snapshot_csv.snapshot_to_csv({}) == ""
