"""Metric-view compilation — semantic-layer specs into executable SQL.

soyuz-catalog stores a metric view as opaque dimension / measure
expression strings over one source table; this module turns a
*query* against that definition (pick dimensions, pick measures,
optional extra predicate) into a single DuckDB SELECT that the
normal PQL SQL path executes — so SELECT enforcement, row caps, and
query history all apply unchanged.

Every fragment (dimension expr, measure expr, filter, extra WHERE)
is parsed with sqlglot before it is embedded; a fragment that does
not parse as a lone expression is rejected, so a definition cannot
smuggle additional statements into the compiled query.
"""

from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError
from sqlglot.expressions.core import Expr

_FQN_RE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")

_DIALECT = "duckdb"


def _parse_fragment(fragment: str, *, what: str) -> Expr:
    """Parse one expression fragment or raise.

    Args:
        fragment: SQL expression text from the spec or the caller.
        what: Noun for the error message.

    Returns:
        The parsed sqlglot expression.

    Raises:
        ValueError: When the fragment is empty, fails to parse, or
            parses to something other than a single expression.
    """
    candidate = (fragment or "").strip().rstrip(";")
    if not candidate:
        raise ValueError(f"{what} must be a non-empty SQL expression")
    if ";" in candidate:
        # a lone expression never legitimately contains a statement
        # separator — reject before the parser silently truncates.
        raise ValueError(f"{what} must be a single expression (';' found)")
    try:
        parsed = sqlglot.parse_one(candidate, dialect=_DIALECT, into=exp.Condition)
    except ParseError as exc:
        raise ValueError(f"{what} does not parse: {exc}") from exc
    if isinstance(parsed, exp.Select | exp.Subquery) or parsed.find(exp.Command):
        raise ValueError(f"{what} must be a plain expression, not a statement")
    return parsed


def compile_metric_query(
    *,
    source_table: str,
    spec: dict[str, Any],
    dimensions: list[str],
    measures: list[str],
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> str:
    """Compile a metric-view query into one DuckDB SELECT.

    Args:
        source_table: Three-part ``catalog.schema.table`` reference
            of the view's source.
        spec: The stored metric-view spec (``dimensions`` /
            ``measures`` lists of ``{"name", "expr"}`` plus an
            optional ``filter`` predicate baked into every query).
        dimensions: Requested dimension names (subset; may be empty
            for a grand-total query).
        measures: Requested measure names (at least one).
        where: Optional extra predicate ANDed onto the spec filter.
        order_by: Optional ``<selected-name> [asc|desc]``.
        limit: Optional row limit.

    Returns:
        The compiled SQL string.

    Raises:
        ValueError: On an unknown dimension/measure name, a source
            that is not three-part, a fragment that fails to parse,
            or a malformed order_by/limit.
    """
    if not _FQN_RE.match(source_table or ""):
        raise ValueError(f"source table must be catalog.schema.table, got {source_table!r}")
    if not measures:
        raise ValueError("at least one measure is required")

    dim_specs = {str(d["name"]): str(d["expr"]) for d in spec.get("dimensions", [])}
    measure_specs = {str(m["name"]): str(m["expr"]) for m in spec.get("measures", [])}

    select_exprs: list[Expr] = []
    selected_names: list[str] = []
    for name in dimensions:
        if name not in dim_specs:
            raise ValueError(f"unknown dimension {name!r}")
        parsed = _parse_fragment(dim_specs[name], what=f"dimension {name!r}")
        select_exprs.append(exp.alias_(parsed, name, quoted=True))
        selected_names.append(name)
    for name in measures:
        if name not in measure_specs:
            raise ValueError(f"unknown measure {name!r}")
        parsed = _parse_fragment(measure_specs[name], what=f"measure {name!r}")
        select_exprs.append(exp.alias_(parsed, name, quoted=True))
        selected_names.append(name)

    query = sqlglot.select(*select_exprs).from_(source_table)

    conditions: list[Expr] = []
    spec_filter = spec.get("filter")
    if spec_filter:
        conditions.append(_parse_fragment(str(spec_filter), what="spec filter"))
    if where and where.strip():
        conditions.append(_parse_fragment(where, what="where"))
    for condition in conditions:
        query = query.where(condition)

    if dimensions:
        query = query.group_by(*[str(i + 1) for i in range(len(dimensions))])

    if order_by and order_by.strip():
        parts = order_by.strip().rsplit(" ", 1)
        name = parts[0].strip()
        direction = parts[1].lower() if len(parts) == 2 else "asc"
        if name not in selected_names or direction not in ("asc", "desc"):
            raise ValueError(f"order_by must be '<selected name> [asc|desc]', got {order_by!r}")
        query = query.order_by(f'"{name}" {direction}')

    if limit is not None:
        try:
            limit_value = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"limit must be a positive integer, got {limit!r}") from exc
        if limit_value <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit!r}")
        query = query.limit(limit_value)

    return query.sql(dialect=_DIALECT)
