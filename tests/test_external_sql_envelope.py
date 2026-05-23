"""Phase 117 — DBX envelope serializer + type mapping."""

from __future__ import annotations

import pytest

from pointlessql.pql import SQLResult
from pointlessql.services.sql_statements._envelope import (
    DBX_ERROR_CODES,
    build_dbx_envelope,
    duckdb_to_dbx_type,
    error_envelope,
    status_envelope,
)


@pytest.mark.parametrize(
    ("duckdb_type", "expected"),
    [
        ("VARCHAR", "STRING"),
        ("VARCHAR(255)", "STRING"),
        ("BIGINT", "LONG"),
        ("INTEGER", "INT"),
        ("DOUBLE", "DOUBLE"),
        ("BOOLEAN", "BOOLEAN"),
        ("TIMESTAMP", "TIMESTAMP"),
        ("DATE", "DATE"),
        ("DECIMAL(18,2)", "DECIMAL"),
        ("LIST(VARCHAR)", "STRING"),
        ("STRUCT(a INT, b INT)", "STRING"),
        ("UNKNOWN_FUTURE_TYPE", "STRING"),
    ],
)
def test_duckdb_to_dbx_type_mapping(duckdb_type: str, expected: str) -> None:
    assert duckdb_to_dbx_type(duckdb_type) == expected


def test_build_dbx_envelope_shape() -> None:
    """The envelope mirrors Databricks' SQL Statement Execution response."""
    result = SQLResult(
        columns=[
            {"name": "id", "type": "BIGINT"},
            {"name": "label", "type": "VARCHAR"},
            {"name": "ratio", "type": "DOUBLE"},
            {"name": "active", "type": "BOOLEAN"},
        ],
        rows=[
            [1, "alpha", 0.5, True],
            [2, "beta", 1.25, False],
            [3, None, None, None],
        ],
        row_count=3,
        truncated=False,
        duration_ms=42,
        executed_sql="SELECT 1",
        rewritten_sql="SELECT 1",
        referenced_tables=[],
    )
    envelope = build_dbx_envelope(statement_id="abc-123", result=result)
    assert envelope["statement_id"] == "abc-123"
    assert envelope["status"] == {"state": "SUCCEEDED"}
    manifest = envelope["manifest"]
    assert manifest["format"] == "JSON_ARRAY"
    assert manifest["schema"]["column_count"] == 4
    assert manifest["schema"]["columns"][0]["type_name"] == "LONG"
    assert manifest["schema"]["columns"][3]["type_name"] == "BOOLEAN"
    assert manifest["total_row_count"] == 3
    assert manifest["total_chunk_count"] == 1
    assert manifest["truncated"] is False
    # Numerics stringified per DBX convention; booleans as true/false; null preserved.
    data = envelope["result"]["data_array"]
    assert data[0] == ["1", "alpha", "0.5", "true"]
    assert data[1] == ["2", "beta", "1.25", "false"]
    assert data[2] == ["3", None, None, None]


def test_error_envelope_clamps_to_known_codes() -> None:
    """Unknown error codes collapse to INTERNAL_ERROR to keep the shape valid."""
    env = error_envelope(
        statement_id="x", error_code="MADE_UP", message="something broke"
    )
    assert env["status"]["state"] == "FAILED"
    assert env["status"]["error"]["error_code"] == "INTERNAL_ERROR"
    assert env["status"]["error"]["message"] == "something broke"


def test_error_envelope_passes_known_codes() -> None:
    for code in DBX_ERROR_CODES:
        env = error_envelope(statement_id="x", error_code=code, message="m")
        assert env["status"]["error"]["error_code"] == code


def test_status_envelope_refuses_succeeded() -> None:
    with pytest.raises(ValueError):
        status_envelope(statement_id="x", state="SUCCEEDED")


def test_status_envelope_pending_shape() -> None:
    env = status_envelope(statement_id="x", state="PENDING")
    assert env == {"statement_id": "x", "status": {"state": "PENDING"}}
