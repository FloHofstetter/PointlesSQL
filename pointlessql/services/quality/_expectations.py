"""Extended data-quality expectations.

Six new assertion kinds beyond the base contract-test vocabulary, each a
pure ``(spec, table) -> AssertionVerdict`` function matching the shape of
:mod:`pointlessql.services.contract_tests._assertions` so they are drop-in
when the dispatcher is extended (a follow-up gated behind a CHECK-constraint
migration that admits the new kind names):

* ``uniqueness`` — a column has no duplicate values;
* ``monotonic`` — a column is monotonically increasing/decreasing;
* ``set_membership`` — every value is in an allowed set;
* ``cross_column`` — a per-row comparison between two columns holds;
* ``conditional`` — when one column matches, another must be non-null;
* ``regex_match`` — every non-null string value matches a pattern.

Pure + deterministic: no I/O, no DB, no soyuz.  Each returns a ``pass`` /
``fail`` / ``error`` verdict with an observation dict the UI can render.
"""

from __future__ import annotations

import re
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from pointlessql.services.contract_tests._assertions import AssertionVerdict

EXTENDED_ASSERTION_KINDS: tuple[str, ...] = (
    "uniqueness",
    "monotonic",
    "set_membership",
    "cross_column",
    "conditional",
    "regex_match",
)


def _require_column(column: str, table: pa.Table) -> AssertionVerdict | None:
    """Return an ``error`` verdict if *column* is absent, else ``None``."""
    if not column:
        return AssertionVerdict(status="error", observation={"reason": "missing 'column'"})
    if column not in table.column_names:
        return AssertionVerdict(
            status="error", observation={"reason": f"column '{column}' not in table"}
        )
    return None


def assert_uniqueness(spec: dict[str, Any], table: pa.Table) -> AssertionVerdict:
    """Assert a column's non-null values are all distinct."""
    column = str(spec.get("column", ""))
    err = _require_column(column, table)
    if err is not None:
        return err
    col = table[column].drop_null()
    distinct = int(pc.count_distinct(col).as_py() or 0)  # type: ignore[attr-defined]
    total = int(len(col))
    duplicates = total - distinct
    status = "pass" if duplicates == 0 else "fail"
    return AssertionVerdict(
        status=status,
        observation={
            "column": column,
            "non_null": total,
            "distinct": distinct,
            "duplicates": duplicates,
        },
    )


def assert_monotonic(spec: dict[str, Any], table: pa.Table) -> AssertionVerdict:
    """Assert a column is monotonic in ``direction`` (``increasing``/``decreasing``)."""
    column = str(spec.get("column", ""))
    err = _require_column(column, table)
    if err is not None:
        return err
    direction = str(spec.get("direction", "increasing"))
    strict = bool(spec.get("strict", False))
    values = [v for v in table[column].to_pylist() if v is not None]
    breaches = 0
    for prev, cur in zip(values, values[1:], strict=False):
        if direction == "increasing":
            ok = cur > prev if strict else cur >= prev
        else:
            ok = cur < prev if strict else cur <= prev
        if not ok:
            breaches += 1
    status = "pass" if breaches == 0 else "fail"
    return AssertionVerdict(
        status=status,
        observation={
            "column": column,
            "direction": direction,
            "strict": strict,
            "breaches": breaches,
        },
    )


def assert_set_membership(spec: dict[str, Any], table: pa.Table) -> AssertionVerdict:
    """Every non-null value of a column is within ``allowed``."""
    column = str(spec.get("column", ""))
    err = _require_column(column, table)
    if err is not None:
        return err
    allowed = set(spec.get("allowed", []) or [])
    if not allowed:
        return AssertionVerdict(status="error", observation={"reason": "missing 'allowed' set"})
    violations = sorted(
        {v for v in table[column].to_pylist() if v is not None and v not in allowed}
    )
    status = "pass" if not violations else "fail"
    return AssertionVerdict(
        status=status,
        observation={
            "column": column,
            "violations": violations[:25],
            "violation_count": len(violations),
        },
    )


def assert_cross_column(spec: dict[str, Any], table: pa.Table) -> AssertionVerdict:
    """Assert a per-row comparison ``left <op> right`` holds for every row."""
    left, right, op = (
        str(spec.get("left", "")),
        str(spec.get("right", "")),
        str(spec.get("op", "<=")),
    )
    for col in (left, right):
        err = _require_column(col, table)
        if err is not None:
            return err
    ops = {
        "<=": pc.less_equal,  # type: ignore[attr-defined]
        "<": pc.less,  # type: ignore[attr-defined]
        ">=": pc.greater_equal,  # type: ignore[attr-defined]
        ">": pc.greater,  # type: ignore[attr-defined]
        "==": pc.equal,  # type: ignore[attr-defined]
        "!=": pc.not_equal,  # type: ignore[attr-defined]
    }
    if op not in ops:
        return AssertionVerdict(status="error", observation={"reason": f"unknown op '{op}'"})
    mask = ops[op](table[left], table[right])
    holds = int(pc.sum(pc.cast(mask, pa.int64())).as_py() or 0)  # type: ignore[attr-defined]
    total = int(table.num_rows)
    breaches = total - holds
    status = "pass" if breaches == 0 else "fail"
    return AssertionVerdict(
        status=status,
        observation={"expr": f"{left} {op} {right}", "rows": total, "breaches": breaches},
    )


def assert_conditional(spec: dict[str, Any], table: pa.Table) -> AssertionVerdict:
    """When ``when_column == when_value``, ``then_column`` must be non-null."""
    when_col, then_col = str(spec.get("when_column", "")), str(spec.get("then_column", ""))
    for col in (when_col, then_col):
        err = _require_column(col, table)
        if err is not None:
            return err
    when_value = spec.get("when_value")
    when = table[when_col].to_pylist()
    then = table[then_col].to_pylist()
    breaches = sum(1 for w, t in zip(when, then, strict=False) if w == when_value and t is None)
    status = "pass" if breaches == 0 else "fail"
    return AssertionVerdict(
        status=status,
        observation={
            "when": f"{when_col}=={when_value!r}",
            "then_non_null": then_col,
            "breaches": breaches,
        },
    )


def assert_regex_match(spec: dict[str, Any], table: pa.Table) -> AssertionVerdict:
    """Every non-null string value of a column matches ``pattern``."""
    column = str(spec.get("column", ""))
    err = _require_column(column, table)
    if err is not None:
        return err
    pattern = str(spec.get("pattern", ""))
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return AssertionVerdict(status="error", observation={"reason": f"bad regex: {exc}"})
    breaches = sum(
        1 for v in table[column].to_pylist() if v is not None and compiled.fullmatch(str(v)) is None
    )
    status = "pass" if breaches == 0 else "fail"
    return AssertionVerdict(
        status=status, observation={"column": column, "pattern": pattern, "breaches": breaches}
    )


# kind name -> evaluator, for the dispatcher extension (wiring deferred).
EXTENDED_ASSERTIONS = {
    "uniqueness": assert_uniqueness,
    "monotonic": assert_monotonic,
    "set_membership": assert_set_membership,
    "cross_column": assert_cross_column,
    "conditional": assert_conditional,
    "regex_match": assert_regex_match,
}
