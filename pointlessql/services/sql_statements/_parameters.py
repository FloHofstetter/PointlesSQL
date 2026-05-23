"""Typed parameter binding for the public SQL API.

DBX-compatible request bodies carry ``:name`` placeholders + a
``parameters`` array of typed entries.  We bind via sqlglot AST
substitution so the resulting SQL is injection-safe: the literal
value goes through sqlglot's quoting / typed-literal helpers,
not naïve string formatting.

Types supported in v1 (mirroring DBX naming):

* STRING / VARCHAR / TEXT
* INT / INTEGER
* LONG / BIGINT
* DOUBLE / FLOAT
* BOOLEAN / BOOL
* DATE          — ISO 8601 ``YYYY-MM-DD``
* TIMESTAMP     — ISO 8601 ``YYYY-MM-DD HH:MM:SS[.fff][±HH:MM]``
* NULL          — value field ignored

DECIMAL deferred to v2 (precision/scale handling is non-trivial and
the existing surface has no decimal-using callers yet).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import sqlglot
from sqlglot import exp

SUPPORTED_PARAM_TYPES: frozenset[str] = frozenset(
    {
        "STRING",
        "VARCHAR",
        "TEXT",
        "INT",
        "INTEGER",
        "LONG",
        "BIGINT",
        "DOUBLE",
        "FLOAT",
        "BOOLEAN",
        "BOOL",
        "DATE",
        "TIMESTAMP",
        "NULL",
    }
)


def _coerce(type_name: str, raw_value: Any) -> Any:
    """Coerce a raw parameter value to a sqlglot literal expression.

    Args:
        type_name: DBX type name (upper-cased).
        raw_value: Whatever the client sent for ``value``.

    Returns:
        A sqlglot Expression suitable for AST substitution.

    Raises:
        ValueError: When the value cannot be coerced to the
            declared type (e.g. ``"abc"`` for INT).
    """
    if type_name == "NULL" or raw_value is None:
        return exp.Null()
    if type_name in ("STRING", "VARCHAR", "TEXT"):
        return exp.Literal.string(str(raw_value))
    if type_name in ("INT", "INTEGER", "LONG", "BIGINT"):
        try:
            return exp.Literal.number(int(str(raw_value)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"value {raw_value!r} is not a valid {type_name}") from exc
    if type_name in ("DOUBLE", "FLOAT"):
        try:
            return exp.Literal.number(float(str(raw_value)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"value {raw_value!r} is not a valid {type_name}") from exc
    if type_name in ("BOOLEAN", "BOOL"):
        if isinstance(raw_value, bool):
            return exp.Boolean(this=raw_value)
        as_str = str(raw_value).strip().lower()
        if as_str in ("true", "1", "yes"):
            return exp.Boolean(this=True)
        if as_str in ("false", "0", "no"):
            return exp.Boolean(this=False)
        raise ValueError(f"value {raw_value!r} is not a valid BOOLEAN")
    if type_name == "DATE":
        try:
            parsed = date.fromisoformat(str(raw_value))
        except ValueError as exc:
            raise ValueError(f"value {raw_value!r} is not a valid DATE (ISO 8601)") from exc
        return exp.Cast(
            this=exp.Literal.string(parsed.isoformat()),
            to=exp.DataType.build("DATE"),
        )
    if type_name == "TIMESTAMP":
        try:
            parsed_ts = datetime.fromisoformat(str(raw_value))
        except ValueError as exc:
            raise ValueError(
                f"value {raw_value!r} is not a valid TIMESTAMP (ISO 8601)"
            ) from exc
        return exp.Cast(
            this=exp.Literal.string(parsed_ts.isoformat(sep=" ")),
            to=exp.DataType.build("TIMESTAMP"),
        )
    raise ValueError(f"unsupported parameter type {type_name!r}")


def bind_parameters(
    sql: str,
    parameters: list[dict[str, Any]],
) -> str:
    """Substitute ``:name`` placeholders in *sql* with typed literals.

    Walks the sqlglot AST for ``:name`` placeholder nodes
    (:class:`sqlglot.expressions.Placeholder` and its parameter
    cousin) and replaces each with the coerced literal from
    ``parameters``.

    Args:
        sql: Raw user SQL with ``:name`` placeholders.
        parameters: List of ``{"name", "value", "type"}`` dicts.
            ``type`` defaults to ``STRING`` when omitted to match
            DBX defaults.

    Returns:
        The rewritten SQL with all placeholders substituted.

    Raises:
        ValueError: When a placeholder has no matching entry, when an
            entry's ``type`` is not in :data:`SUPPORTED_PARAM_TYPES`,
            or when coercion fails.  sqlglot's own
            :class:`sqlglot.errors.ParseError` also propagates from
            ``parse_one`` for malformed SQL — callers map both to the
            DBX ``SQL_PARSE_ERROR`` / ``INVALID_PARAMETER_VALUE``
            envelopes.
    """
    # Build the {name: literal-expression} map first so a bad type
    # surfaces before we touch the AST.
    bindings: dict[str, Any] = {}
    for entry in parameters:
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("each parameter entry must have a non-empty 'name'")
        type_name = str(entry.get("type") or "STRING").upper()
        if type_name not in SUPPORTED_PARAM_TYPES:
            raise ValueError(
                f"unsupported parameter type {type_name!r} for {name!r}; "
                f"supported: {sorted(SUPPORTED_PARAM_TYPES)}"
            )
        bindings[name] = _coerce(type_name, entry.get("value"))

    parsed = sqlglot.parse_one(sql, read="duckdb")
    seen_names: set[str] = set()
    # ``Placeholder(this='name')`` covers the ``:name`` form sqlglot
    # produces for named placeholders.  ``Parameter`` is the AT-sign
    # variant some dialects use; included so a request that crosses
    # both styles still binds cleanly.
    for node in list(parsed.find_all(exp.Placeholder, exp.Parameter)):
        ident = node.name or (
            node.this.name if isinstance(node.this, exp.Identifier) else None
        )
        if not ident:
            continue
        if ident not in bindings:
            raise ValueError(f"missing binding for placeholder :{ident}")
        seen_names.add(ident)
        node.replace(bindings[ident].copy())

    unused = set(bindings) - seen_names
    if unused:
        # Unused params are not a hard error in DBX, but we surface
        # them so a client typo (``:regin`` vs ``:region``) doesn't
        # silently substitute nothing.  Keep the message close to
        # the DBX equivalent so adapters can pattern-match.
        raise ValueError(
            f"parameters {sorted(unused)} have no matching placeholder in the statement"
        )
    return parsed.sql(dialect="duckdb")
