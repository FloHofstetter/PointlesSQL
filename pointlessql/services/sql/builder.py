"""Visual Query Builder.

Two pure-functional pieces:

* :func:`build_sql_from_state` — turn a structured filter / group-by
  / aggregate spec into SELECT SQL via sqlglot.
* :func:`parse_sql_to_state` — best-effort the reverse: a SELECT
  that only uses shapes the builder understands round-trips back
  to state; anything else returns ``None`` and the UI falls back
  to raw-SQL-only.

The builder deliberately rejects multi-table queries (CTEs, JOINs,
subqueries).  Single-table "filter + group + agg" is the supported
shape; richer queries land as follow-ups.
"""

from __future__ import annotations

from typing import Any, cast

from sqlglot import exp, parse_one
from sqlglot.expressions.core import Expression

# Operators the builder accepts.  Kept in sync with the dropdown in
# ``sql_editor.html``.
SUPPORTED_OPS: tuple[str, ...] = (
    "=",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "LIKE",
    "ILIKE",
    "IN",
    "IS NULL",
    "IS NOT NULL",
)

SUPPORTED_AGGS: tuple[str, ...] = ("COUNT", "SUM", "AVG", "MIN", "MAX")

_OP_TO_SQLGLOT = {
    "=": exp.EQ,
    "!=": exp.NEQ,
    "<": exp.LT,
    "<=": exp.LTE,
    ">": exp.GT,
    ">=": exp.GTE,
}


def build_sql_from_state(state: dict[str, Any]) -> str:
    """Render a structured builder state to SELECT SQL.

    Args:
        state: ``{table_fqn, filters, group_by, aggregates,
            order_by, limit}``.  Missing keys default to empty.

    Returns:
        A formatted SELECT statement.

    Raises:
        ValueError: When ``table_fqn`` is missing / not 3-part, or
            a filter / aggregate references an unknown operator.
    """
    table_fqn = (state.get("table_fqn") or "").strip()
    if not table_fqn:
        raise ValueError("table_fqn is required.")
    parts = table_fqn.split(".")
    if len(parts) != 3:
        raise ValueError(f"table_fqn must be three-part (catalog.schema.table); got {table_fqn!r}.")

    select_items: list[Expression] = []
    aggregates = cast(list[dict[str, Any]], state.get("aggregates") or [])
    group_by_cols = cast(list[str], state.get("group_by") or [])

    for col in group_by_cols:
        select_items.append(exp.column(col))

    for agg in aggregates:
        fn = str(agg.get("fn") or "").upper()
        if fn not in SUPPORTED_AGGS:
            raise ValueError(f"Unsupported aggregate function: {fn!r}")
        col = agg.get("column") or "*"
        alias = agg.get("alias")
        if col == "*":
            arg = exp.Star()
        else:
            arg = exp.column(str(col))
        agg_expr = cast(Expression, exp.func(fn, arg))
        if isinstance(alias, str) and alias.strip():
            agg_expr = cast(Expression, agg_expr.as_(alias.strip()))
        select_items.append(agg_expr)

    if not select_items:
        select_items.append(exp.Star())

    select = exp.Select(
        expressions=select_items,
    ).from_(exp.to_table(table_fqn))

    filters = cast(list[dict[str, Any]], state.get("filters") or [])
    where_expr: Expression | None = None
    for f in filters:
        col = str(f.get("column") or "").strip()
        op = str(f.get("op") or "=").upper()
        if not col or op not in SUPPORTED_OPS:
            continue
        clause = _filter_to_expression(col, op, f.get("value"))
        if clause is None:
            continue
        where_expr = (
            clause if where_expr is None else cast(Expression, exp.and_(where_expr, clause))
        )
    if where_expr is not None:
        select = select.where(where_expr)

    if group_by_cols:
        select = select.group_by(*[exp.column(c) for c in group_by_cols])

    order_by = cast(list[dict[str, Any]], state.get("order_by") or [])
    for ob in order_by:
        col = ob.get("column")
        if not isinstance(col, str) or not col.strip():
            continue
        direction = str(ob.get("dir") or "asc").lower()
        order_expr = exp.column(col).asc() if direction == "asc" else exp.column(col).desc()
        select = select.order_by(order_expr)

    limit = state.get("limit")
    if isinstance(limit, int) and limit > 0:
        select = select.limit(limit)

    return select.sql(dialect="duckdb", pretty=True)


def _filter_to_expression(column: str, op: str, value: Any) -> Expression | None:
    """Map one builder filter row to a sqlglot expression.

    Args:
        column: Column name.
        op: Operator string (already upper-cased).
        value: Caller-supplied value (may be ``None``).

    Returns:
        The sqlglot expression, or ``None`` when the operator's
        required value is missing.
    """
    col = exp.column(column)
    if op == "IS NULL":
        return exp.Is(this=col, expression=exp.Null())
    if op == "IS NOT NULL":
        return exp.Not(this=exp.Is(this=col, expression=exp.Null()))
    if value is None or value == "":
        return None
    if op == "IN":
        if isinstance(value, str):
            items: list[Any] = [v.strip() for v in value.split(",") if v.strip()]
        elif isinstance(value, list):
            items = cast(list[Any], value)
        else:
            return None
        return exp.In(this=col, expressions=[_literal(v) for v in items])
    if op == "LIKE":
        return exp.Like(this=col, expression=_literal(value))
    if op == "ILIKE":
        return exp.ILike(this=col, expression=_literal(value))
    klass = _OP_TO_SQLGLOT.get(op)
    if klass is None:
        return None
    return klass(this=col, expression=_literal(value))


def _literal(value: Any) -> Expression:
    """Wrap *value* in the appropriate sqlglot literal node.

    Args:
        value: Caller-supplied scalar.

    Returns:
        A sqlglot Literal / Boolean node.
    """
    if isinstance(value, bool):
        return exp.Boolean(this=value)
    if isinstance(value, (int, float)):
        return exp.Literal.number(value)
    return exp.Literal.string(str(value))


def parse_sql_to_state(sql: str) -> dict[str, Any] | None:
    """Best-effort inverse of :func:`build_sql_from_state`.

    Returns ``None`` when the SQL falls outside the builder's
    supported subset.  Supported subset:

    * Single SELECT against one 3-part table reference.
    * WHERE built from AND-joined simple ``col OP value`` /
      ``col IS [NOT] NULL`` / ``col IN (…)`` clauses.
    * GROUP BY of simple column names.
    * SELECT items = column refs or ``FN(col|*) [AS alias]`` where
      FN ∈ :data:`SUPPORTED_AGGS`.
    * Single ORDER BY clause; LIMIT.

    Args:
        sql: The SQL text.

    Returns:
        The reconstructed state dict, or ``None`` when round-trip
        is not possible.
    """
    try:
        tree = parse_one(sql, dialect="duckdb")
    except Exception:  # noqa: BLE001 — anything sqlglot raises means "give up"
        # bare-broad-ok: sqlglot reverse-mapping silently returns None on failure
        return None
    if not isinstance(tree, exp.Select):
        return None
    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1:
        return None
    table = tables[0]
    fqn_parts = [
        p.name
        for p in [table.args.get("catalog"), table.args.get("db"), table.this]
        if p is not None
    ]
    if len(fqn_parts) != 3:
        return None
    table_fqn = ".".join(fqn_parts)

    state: dict[str, Any] = {
        "table_fqn": table_fqn,
        "filters": [],
        "group_by": [],
        "aggregates": [],
        "order_by": [],
        "limit": None,
    }

    group_by = tree.args.get("group")
    if group_by is not None:
        for col_expr in group_by.expressions:
            if not isinstance(col_expr, exp.Column):
                return None
            state["group_by"].append(col_expr.name)

    for select_expr in tree.expressions:
        if isinstance(select_expr, exp.Star):
            continue
        if isinstance(select_expr, exp.Column):
            if select_expr.name not in state["group_by"]:
                # Bare column outside GROUP BY → builder cannot
                # represent; bail out so caller falls back.
                return None
            continue
        agg_expr = select_expr.unalias() if isinstance(select_expr, exp.Alias) else select_expr
        alias_str = select_expr.alias if isinstance(select_expr, exp.Alias) else None
        fn_name = type(agg_expr).__name__.upper() if isinstance(agg_expr, exp.Func) else None
        if fn_name not in SUPPORTED_AGGS:
            return None
        inner = agg_expr.this if isinstance(agg_expr, exp.Func) else None
        if isinstance(inner, exp.Star):
            col_name = "*"
        elif isinstance(inner, exp.Column):
            col_name = inner.name
        else:
            return None
        state["aggregates"].append({"fn": fn_name, "column": col_name, "alias": alias_str})

    where = tree.args.get("where")
    if where is not None:
        for clause in _split_conjunction(where.this):
            f = _expression_to_filter(clause)
            if f is None:
                return None
            state["filters"].append(f)

    order_by = tree.args.get("order")
    if order_by is not None:
        for ordered in order_by.expressions:
            inner = ordered.this if isinstance(ordered, exp.Ordered) else ordered
            if not isinstance(inner, exp.Column):
                return None
            desc_flag = isinstance(ordered, exp.Ordered) and ordered.args.get("desc")
            direction = "desc" if desc_flag else "asc"
            state["order_by"].append({"column": inner.name, "dir": direction})

    limit_expr = tree.args.get("limit")
    if isinstance(limit_expr, exp.Limit) and isinstance(limit_expr.expression, exp.Literal):
        try:
            state["limit"] = int(limit_expr.expression.this)
        except TypeError, ValueError:
            state["limit"] = None

    return state


def _split_conjunction(expr: Expression) -> list[Expression]:
    """Flatten a tree of ``AND`` nodes into a list of leaf clauses.

    Args:
        expr: Root of the WHERE tree.

    Returns:
        Leaves in document order.
    """
    out: list[Expression] = []
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, exp.And):
            stack.append(node.expression)
            stack.append(node.this)
        else:
            out.append(node)
    return out


def _expression_to_filter(node: Expression) -> dict[str, Any] | None:
    """Reverse one leaf of the WHERE conjunction into a filter dict.

    Args:
        node: Sqlglot leaf node.

    Returns:
        ``{column, op, value}``, or ``None`` when the shape is too
        rich for the builder.
    """
    if isinstance(node, exp.Is):
        if isinstance(node.this, exp.Column) and isinstance(node.expression, exp.Null):
            return {"column": node.this.name, "op": "IS NULL", "value": None}
        return None
    if isinstance(node, exp.Not):
        inner = node.this
        if (
            isinstance(inner, exp.Is)
            and isinstance(inner.this, exp.Column)
            and isinstance(inner.expression, exp.Null)
        ):
            return {"column": inner.this.name, "op": "IS NOT NULL", "value": None}
        return None
    inv_ops = {v: k for k, v in _OP_TO_SQLGLOT.items()}
    for cls, op_str in inv_ops.items():
        if isinstance(node, cls):
            if not isinstance(node.this, exp.Column):
                return None
            value = _literal_to_python(node.expression)
            if value is None:
                return None
            return {"column": node.this.name, "op": op_str, "value": value}
    if isinstance(node, exp.Like):
        if not isinstance(node.this, exp.Column):
            return None
        v = _literal_to_python(node.expression)
        return None if v is None else {"column": node.this.name, "op": "LIKE", "value": v}
    if isinstance(node, exp.ILike):
        if not isinstance(node.this, exp.Column):
            return None
        v = _literal_to_python(node.expression)
        return None if v is None else {"column": node.this.name, "op": "ILIKE", "value": v}
    if isinstance(node, exp.In):
        if not isinstance(node.this, exp.Column):
            return None
        values: list[Any] = []
        for e in node.expressions:
            v = _literal_to_python(e)
            if v is None:
                return None
            values.append(v)
        return {"column": node.this.name, "op": "IN", "value": values}
    return None


def _literal_to_python(node: Expression) -> Any | None:
    """Extract the Python scalar a sqlglot literal/boolean carries.

    Args:
        node: A sqlglot literal/boolean expression node.

    Returns:
        The Python value, or ``None`` when the node isn't a leaf
        literal the builder understands.
    """
    if isinstance(node, exp.Literal):
        raw: Any = node.this
        if node.is_string:
            return str(raw)
        try:
            i = int(raw)
            if str(i) == str(raw):
                return i
        except TypeError, ValueError:
            pass
        try:
            return float(raw)
        except TypeError, ValueError:
            return raw
    if isinstance(node, exp.Boolean):
        return bool(node.this)
    if isinstance(node, exp.Null):
        return None
    return None
