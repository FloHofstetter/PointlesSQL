"""Evaluate one of the six declarative contract assertions.

The CHECK constraint on ``data_product_contract_tests.assertion_kind``
admits six shapes; this module dispatches on the kind and returns a
:class:`AssertionVerdict` with the status + an observation dict the
runner persists into ``observation_json``.

Asserter conventions:

* A missing required key in *spec* is a configuration error and the
  asserter raises :class:`ValueError`.  The runner translates that
  into an ``error``-status result row.
* A failed assertion returns ``fail`` with the observed metric — the
  runner does not treat ``fail`` as exceptional.
* ``pass`` carries the observed metric too so the surface can render
  it.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc


@dataclasses.dataclass(slots=True, frozen=True)
class AssertionVerdict:
    """Outcome of one assertion evaluation.

    Attributes:
        status: ``pass`` / ``fail`` / ``error``.
        observation: Free-form metric dict the surface renders.
    """

    status: str
    observation: dict[str, Any]


def evaluate_assertion(
    *, assertion_kind: str, spec_json: str | dict[str, Any], table: pa.Table
) -> AssertionVerdict:
    """Dispatch one assertion against *table*.

    Args:
        assertion_kind: One of the six CHECK-bounded kinds.
        spec_json: The raw JSON string from the DB or the decoded dict.
        table: The Arrow table the assertion runs against — either the
            live storage table the runner loaded, or a synthetic
            fixture.

    Returns:
        :class:`AssertionVerdict`.

    Raises:
        ValueError: For unknown kinds or malformed specs.
    """
    spec = _decode_spec(spec_json)
    if assertion_kind == "row_count_range":
        return _assert_row_count_range(spec, table)
    if assertion_kind == "column_present":
        return _assert_column_present(spec, table)
    if assertion_kind == "value_distribution":
        return _assert_value_distribution(spec, table)
    if assertion_kind == "null_rate":
        return _assert_null_rate(spec, table)
    if assertion_kind == "referential":
        return _assert_referential(spec, table)
    if assertion_kind == "freshness":
        return _assert_freshness(spec, table)
    raise ValueError(f"unknown assertion kind: {assertion_kind}")


def _decode_spec(spec_json: str | dict[str, Any]) -> dict[str, Any]:
    """Decode the assertion spec into a dict."""
    if isinstance(spec_json, dict):
        return spec_json
    try:
        decoded = json.loads(spec_json)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"spec is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ValueError("assertion spec must be a JSON object")
    return decoded


def _assert_row_count_range(
    spec: dict[str, Any], table: pa.Table
) -> AssertionVerdict:
    """Row count is between ``min`` and ``max`` (inclusive)."""
    lo = int(spec.get("min", 0))
    hi = int(spec.get("max", 10**12))
    observed = int(table.num_rows)
    status = "pass" if lo <= observed <= hi else "fail"
    return AssertionVerdict(
        status=status,
        observation={"observed": observed, "min": lo, "max": hi},
    )


def _assert_column_present(
    spec: dict[str, Any], table: pa.Table
) -> AssertionVerdict:
    """Every column in ``columns`` exists on the table (case-sensitive)."""
    required = list(spec.get("columns", []) or [])
    if not required:
        raise ValueError("column_present requires 'columns' list")
    present = set(table.column_names)
    missing = [c for c in required if c not in present]
    status = "pass" if not missing else "fail"
    return AssertionVerdict(
        status=status,
        observation={"required": required, "missing": missing},
    )


def _assert_value_distribution(
    spec: dict[str, Any], table: pa.Table
) -> AssertionVerdict:
    """Distinct value count for ``column`` falls within ``min``/``max``."""
    column = str(spec.get("column", ""))
    if not column:
        raise ValueError("value_distribution requires 'column'")
    if column not in table.column_names:
        return AssertionVerdict(
            status="error",
            observation={"reason": f"column '{column}' not in table"},
        )
    distinct_count = int(pc.count_distinct(table[column]).as_py() or 0)  # type: ignore[attr-defined]
    lo = int(spec.get("min_distinct", 1))
    hi = int(spec.get("max_distinct", 10**12))
    status = "pass" if lo <= distinct_count <= hi else "fail"
    return AssertionVerdict(
        status=status,
        observation={
            "column": column,
            "distinct_count": distinct_count,
            "min_distinct": lo,
            "max_distinct": hi,
        },
    )


def _assert_null_rate(
    spec: dict[str, Any], table: pa.Table
) -> AssertionVerdict:
    """Null fraction for ``column`` is at most ``max_rate``."""
    column = str(spec.get("column", ""))
    max_rate = float(spec.get("max_rate", 0.0))
    if not column:
        raise ValueError("null_rate requires 'column'")
    if column not in table.column_names:
        return AssertionVerdict(
            status="error",
            observation={"reason": f"column '{column}' not in table"},
        )
    col = table[column]
    total = int(col.length() or 0)
    if total == 0:
        return AssertionVerdict(
            status="pass",
            observation={"column": column, "observed_rate": 0.0, "rows": 0},
        )
    null_count = int(col.null_count or 0)
    observed_rate = null_count / total
    status = "pass" if observed_rate <= max_rate else "fail"
    return AssertionVerdict(
        status=status,
        observation={
            "column": column,
            "observed_rate": observed_rate,
            "max_rate": max_rate,
            "rows": total,
        },
    )


def _assert_referential(
    spec: dict[str, Any], table: pa.Table
) -> AssertionVerdict:
    """Every value in ``column`` is in ``allowed_values``."""
    column = str(spec.get("column", ""))
    allowed = spec.get("allowed_values")
    if not column or not isinstance(allowed, list):
        raise ValueError("referential requires 'column' and 'allowed_values' list")
    if column not in table.column_names:
        return AssertionVerdict(
            status="error",
            observation={"reason": f"column '{column}' not in table"},
        )
    allowed_set = {str(v) for v in allowed}
    col = table[column].to_pylist()
    violations = [v for v in col if v is not None and str(v) not in allowed_set]
    status = "pass" if not violations else "fail"
    return AssertionVerdict(
        status=status,
        observation={
            "column": column,
            "violation_count": len(violations),
            "sample_violations": violations[:5],
        },
    )


def _assert_freshness(
    spec: dict[str, Any], table: pa.Table
) -> AssertionVerdict:
    """Max value in ``timestamp_column`` is within ``max_lag_minutes`` of now."""
    column = str(spec.get("timestamp_column", ""))
    max_lag_minutes = float(spec.get("max_lag_minutes", 60))
    if not column:
        raise ValueError("freshness requires 'timestamp_column'")
    if column not in table.column_names:
        return AssertionVerdict(
            status="error",
            observation={"reason": f"column '{column}' not in table"},
        )
    values = [v for v in table[column].to_pylist() if v is not None]
    if not values:
        return AssertionVerdict(
            status="fail",
            observation={"reason": "no non-null timestamps"},
        )
    parsed = sorted(
        [m for v in values if (m := _parse_iso8601(v)) is not None]
    )
    if not parsed:
        return AssertionVerdict(
            status="error",
            observation={"reason": "no parseable ISO-8601 timestamps"},
        )
    latest = parsed[-1]
    now = datetime.datetime.now(datetime.UTC)
    lag_minutes = (now - latest).total_seconds() / 60.0
    status = "pass" if lag_minutes <= max_lag_minutes else "fail"
    return AssertionVerdict(
        status=status,
        observation={
            "latest": latest.isoformat(),
            "lag_minutes": lag_minutes,
            "max_lag_minutes": max_lag_minutes,
        },
    )


def _parse_iso8601(value: Any) -> datetime.datetime | None:
    """Best-effort ISO-8601 parse returning timezone-aware UTC moments."""
    if isinstance(value, datetime.datetime):
        return (
            value
            if value.tzinfo is not None
            else value.replace(tzinfo=datetime.UTC)
        )
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    return (
        parsed
        if parsed.tzinfo is not None
        else parsed.replace(tzinfo=datetime.UTC)
    )
