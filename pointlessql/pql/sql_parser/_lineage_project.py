"""Auto-project ``_lineage_row_id`` onto safe row-preserving SELECTs.

When an agent's SELECT reads a lineage-bearing source but omits the
``_lineage_row_id`` column from its projection, the downstream
``write_table`` / ``merge`` hook has no source IDs to correlate and records
zero row-edges — the silent lineage break the wiring audit found.  For a
SELECT that preserves row identity (no GROUP BY / DISTINCT / aggregate /
set-op, direct table sources, exactly one of which carries the column) the
safe fix is to carry the column forward automatically.  Aggregating or
otherwise collapsing SELECTs are intentional row boundaries and are left
untouched for the caller's drop diagnostic.
"""

from __future__ import annotations

from typing import cast

import sqlglot
from sqlglot import expressions as exp

from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN


def _from_node(select: exp.Select) -> exp.From | None:
    """Return the SELECT's top-level ``FROM`` node, tolerating arg-key spelling."""
    for key in ("from_", "from"):
        node = select.args.get(key)
        if isinstance(node, exp.From):
            return node
    return None


def _direct_sources(select: exp.Select) -> list[str] | None:
    """Return the FROM/JOIN table names, or ``None`` if any source isn't a table."""
    from_node = _from_node(select)
    if from_node is None or not isinstance(from_node.this, exp.Table):
        return None
    names = [from_node.this.name]
    joins = cast("list[exp.Join]", select.args.get("joins") or [])
    for join in joins:
        source = join.this
        if not isinstance(source, exp.Table):
            return None
        names.append(source.name)
    return names


def _already_projects(select: exp.Select) -> bool:
    """Report whether the projection already carries the lineage column or a star."""
    for proj in select.expressions:
        if isinstance(proj, exp.Star):
            return True
        if isinstance(proj, exp.Column) and proj.name == LINEAGE_ROW_ID_COLUMN:
            return True
        if isinstance(proj, exp.Alias) and proj.alias == LINEAGE_ROW_ID_COLUMN:
            return True
    return False


def project_lineage_row_id(rewritten_sql: str, *, lineage_refs: set[str]) -> str | None:
    """Return *rewritten_sql* with ``_lineage_row_id`` appended, or ``None``.

    Appends the lineage column to the top-level projection when the query is
    a single bare SELECT that preserves row identity, all its FROM/JOIN
    sources are direct table references, exactly one of them is in
    *lineage_refs*, and the projection does not already carry the column.
    Returns ``None`` in every other case so the caller falls back to the
    drop diagnostic.

    Args:
        rewritten_sql: The DuckDB-rewritten SELECT (quoted view names).
        lineage_refs: Fully-qualified source names that carry
            ``_lineage_row_id``.

    Returns:
        The rewritten SQL with the lineage column projected, or ``None``
        when auto-projection does not apply.
    """
    if not lineage_refs:
        return None
    try:
        root = sqlglot.parse_one(rewritten_sql, dialect="duckdb")
    except Exception:  # noqa: BLE001
        # bare-broad-ok: unparseable SQL just skips auto-projection; the
        # caller re-executes the original and surfaces any real error.
        return None
    if not isinstance(root, exp.Select):
        return None
    if root.args.get("group") or root.args.get("distinct"):
        return None
    if root.find(exp.AggFunc) is not None:
        return None
    if _already_projects(root):
        return None
    sources = _direct_sources(root)
    if sources is None:
        return None
    if len([s for s in sources if s in lineage_refs]) != 1:
        return None
    return root.select(exp.column(LINEAGE_ROW_ID_COLUMN), append=True).sql(dialect="duckdb")
