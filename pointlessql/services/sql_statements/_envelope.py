"""DBX SQL Statement Execution API envelope serializer.

Builds the response shape external clients (databricks-sql-python,
dbt-databricks, raw curl) expect by mirroring the documented schema:

* ``status.state`` ∈ {PENDING, RUNNING, SUCCEEDED, FAILED, CANCELED}
* ``manifest.schema.columns[*].{name,type_text,type_name,position}``
* ``manifest.total_row_count`` / ``manifest.total_chunk_count``
* ``manifest.chunks[*].{chunk_index,row_offset,row_count}``
* ``result.data_array`` — JSON-stringified scalars (DBX preserves
  precision by stringifying numerics; we follow that to keep the
  client adapters happy).

The :class:`SQLResult` produced by :meth:`PQL.sql` carries the
DuckDB-typed result.  This module only knows how to translate it
to DBX shape and how to stringify each cell.
"""

from __future__ import annotations

from typing import Any

from pointlessql.pql import SQLResult

# DBX ``status.error.error_code`` taxonomy.  Frozen tuple so the route
# layer can validate against it without a circular import.
DBX_ERROR_CODES: tuple[str, ...] = (
    "SQL_PARSE_ERROR",
    "INVALID_PARAMETER_VALUE",
    "PERMISSION_DENIED",
    "RESOURCE_NOT_FOUND",
    "REQUEST_LIMIT_EXCEEDED",
    "WORKSPACE_TEMPORARILY_UNAVAILABLE",
    "INTERNAL_ERROR",
)


# Type-text → DBX ``type_name`` mapping.  The :class:`SQLResult`
# column ``type`` field is built from ``str(pyarrow.DataType)`` which
# emits lowercase names (``int64``, ``string``, ``double``).  We
# also accept the DuckDB ``DESCRIBE``-style uppercase forms
# (``BIGINT``, ``VARCHAR``, ``DOUBLE``) so the mapping stays valid
# if the upstream representation ever swaps.  Unknown types fall
# back to STRING so the wire shape stays valid even for exotic
# columns (custom enums, nested STRUCT).
_TYPE_TO_DBX: dict[str, str] = {
    # pyarrow lowercase forms (what SQLResult actually carries today)
    "STRING": "STRING",
    "LARGE_STRING": "STRING",
    "BINARY": "BINARY",
    "LARGE_BINARY": "BINARY",
    "INT8": "BYTE",
    "INT16": "SHORT",
    "INT32": "INT",
    "INT64": "LONG",
    "UINT8": "SHORT",
    "UINT16": "INT",
    "UINT32": "LONG",
    "UINT64": "LONG",
    "FLOAT16": "FLOAT",
    "FLOAT32": "FLOAT",
    "FLOAT64": "DOUBLE",
    "HALFFLOAT": "FLOAT",
    "FLOAT": "FLOAT",
    "DOUBLE": "DOUBLE",
    "BOOL": "BOOLEAN",
    "BOOLEAN": "BOOLEAN",
    "DATE32": "DATE",
    "DATE64": "DATE",
    "DATE": "DATE",
    "TIME32": "STRING",
    "TIME64": "STRING",
    "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMPTZ": "TIMESTAMP",
    "TIMESTAMP_NS": "TIMESTAMP",
    "TIMESTAMP_MS": "TIMESTAMP",
    "TIMESTAMP_S": "TIMESTAMP",
    # DuckDB DESCRIBE uppercase forms (kept for future-proofing)
    "VARCHAR": "STRING",
    "TEXT": "STRING",
    "CHAR": "STRING",
    "BLOB": "BINARY",
    "BIGINT": "LONG",
    "INTEGER": "INT",
    "INT": "INT",
    "INT4": "INT",
    "SMALLINT": "SHORT",
    "TINYINT": "BYTE",
    "REAL": "FLOAT",
    "TIME": "STRING",
    "UUID": "STRING",
    "JSON": "STRING",
    "INTERVAL": "STRING",
    "HUGEINT": "STRING",
    "DECIMAL": "DECIMAL",
    "NUMERIC": "DECIMAL",
}


def duckdb_to_dbx_type(duckdb_type: str) -> str:
    """Translate a column type-text to a DBX ``type_name``.

    Accepts both the pyarrow lowercase representation
    (``int64`` / ``double`` / ``string``) actually carried by
    :class:`SQLResult` today and the DuckDB ``DESCRIBE`` uppercase
    representation (``BIGINT`` / ``VARCHAR``), since the upstream
    naming has shifted over time.  Parameterised forms are trimmed
    (``DECIMAL(18,2)`` → ``DECIMAL``, ``VARCHAR(255)`` → ``VARCHAR``,
    ``timestamp[ns]`` → ``TIMESTAMP``).  Unknown types fall back to
    STRING so the response stays valid.

    Args:
        duckdb_type: Raw type-text from :class:`SQLResult.columns`.

    Returns:
        The DBX ``type_name`` enum string.
    """
    base = duckdb_type.strip().upper()
    # Trim parameterised suffixes from both the ``(`` form (DuckDB)
    # and the ``[`` form (pyarrow, e.g. ``timestamp[ns, tz=UTC]``).
    for sep in ("(", "["):
        if sep in base:
            base = base.split(sep, 1)[0].strip()
    # ARRAY / LIST / MAP / STRUCT — collapse to STRING for v1.
    if base.startswith(("LIST", "ARRAY", "MAP", "STRUCT", "UNION", "FIXED_SIZE_LIST")):
        return "STRING"
    return _TYPE_TO_DBX.get(base, "STRING")


def _stringify_cell(value: Any) -> str | None:
    """Render one cell as the DBX wire form.

    DBX returns every scalar as a JSON string in ``data_array`` (even
    numerics) so JavaScript clients don't truncate ``BIGINT`` and
    Python clients with strict typing can parse precisely.  ``None``
    is preserved as JSON ``null``.

    Args:
        value: One result cell from :class:`SQLResult.rows`.

    Returns:
        The stringified form, or ``None`` for SQL NULL.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Bool MUST come before int — Python bools are ints.
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return str(value)


def build_dbx_envelope(
    *,
    statement_id: str,
    result: SQLResult,
) -> dict[str, Any]:
    """Translate a :class:`SQLResult` to the DBX SUCCEEDED envelope.

    Returned dict is JSON-encodable and ready to ship.  The ``status``
    sub-object always has ``state="SUCCEEDED"`` because failure /
    pending envelopes go through :func:`error_envelope` /
    ``status_envelope`` directly (the executor never invokes this on
    a non-success path).

    Args:
        statement_id: Public statement handle.
        result: DuckDB result from :func:`run_sql_sync`.

    Returns:
        DBX-shape response envelope.
    """
    columns = [
        {
            "name": col["name"],
            "type_text": col["type"],
            "type_name": duckdb_to_dbx_type(col["type"]),
            "position": i,
        }
        for i, col in enumerate(result.columns)
    ]
    data_array = [[_stringify_cell(cell) for cell in row] for row in result.rows]
    chunks = [
        {
            "chunk_index": 0,
            "row_offset": 0,
            "row_count": result.row_count,
        }
    ]
    return {
        "statement_id": statement_id,
        "status": {"state": "SUCCEEDED"},
        "manifest": {
            "format": "JSON_ARRAY",
            "schema": {
                "column_count": len(columns),
                "columns": columns,
            },
            "total_row_count": result.row_count,
            "total_chunk_count": 1,
            "truncated": result.truncated,
            "chunks": chunks,
        },
        "result": {
            "chunk_index": 0,
            "row_offset": 0,
            "row_count": result.row_count,
            "data_array": data_array,
        },
    }


def error_envelope(
    *,
    statement_id: str,
    error_code: str,
    message: str,
) -> dict[str, Any]:
    """Build a DBX FAILED envelope with the given error code + message.

    Args:
        statement_id: Public statement handle.
        error_code: One of :data:`DBX_ERROR_CODES`.  Callers that pass
            an unknown code get ``INTERNAL_ERROR`` substituted so the
            wire shape stays valid.
        message: Human-readable failure detail.

    Returns:
        DBX-shape FAILED envelope.
    """
    code = error_code if error_code in DBX_ERROR_CODES else "INTERNAL_ERROR"
    return {
        "statement_id": statement_id,
        "status": {
            "state": "FAILED",
            "error": {
                "error_code": code,
                "message": message,
            },
        },
    }


def status_envelope(
    *,
    statement_id: str,
    state: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Build a status-only DBX envelope.

    Used for PENDING / RUNNING / CANCELED responses where the caller
    has not yet (or will never) materialise rows.  FAILED rows can
    use this too when the executor wrote ``error_code`` /
    ``error_message`` but the route does not also want to re-derive
    a freshly-built envelope.

    Args:
        statement_id: Public statement handle.
        state: One of ``PENDING`` / ``RUNNING`` / ``FAILED`` /
            ``CANCELED``.  ``SUCCEEDED`` is rejected because it must
            carry a manifest+result — use :func:`build_dbx_envelope`.
        error_code: Optional DBX error code (FAILED only).
        error_message: Optional human-readable detail (FAILED only).

    Returns:
        DBX-shape status envelope.

    Raises:
        ValueError: When called with ``state="SUCCEEDED"``.
    """
    if state == "SUCCEEDED":
        raise ValueError("status_envelope cannot serialise SUCCEEDED; use build_dbx_envelope")
    status: dict[str, Any] = {"state": state}
    if state == "FAILED" and error_code:
        status["error"] = {
            "error_code": error_code if error_code in DBX_ERROR_CODES else "INTERNAL_ERROR",
            "message": error_message or "",
        }
    return {
        "statement_id": statement_id,
        "status": status,
    }
