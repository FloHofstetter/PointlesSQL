"""PQL introspection endpoints.

Closes the agent read-loop: agents already write into
``agent_run_operations`` / ``agent_run_tool_calls`` / Delta logs,
but they also need tools to *read state* before *acting*.

This module hosts every ``GET /api/pql/...`` route that lets a
working agent (Family A) check state mid-run:

* ``GET /api/pql/primitives`` — introspection over the :class:`PQL`
  public methods so an agent that gets a ``TypeError`` from
  ``pql.autoload(source=...)`` can ask for the real signature.
* ``GET /api/pql/target-state`` — table existence, columns, and
  recent-write history fused into one response.
* ``GET /api/pql/lineage`` — upstream + downstream lineage in one
  response.
"""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from pointlessql.api.dependencies import get_uc_client
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import AgentRunOperation
from pointlessql.pql.pql import PQL

router = APIRouter(tags=["pql-introspect"])

# Public primitive surface of :class:`PQL` exposed to agents.  Order
# mirrors the medallion authoring flow: read → query → write/update →
# bootstrap.  Helper methods (``list_*``, the private ``_unreachable_msg``)
# are deliberately omitted — agents reach catalog metadata through
# ``pql_list_tables`` / ``pql_get_table`` instead.
_PRIMITIVES: tuple[str, ...] = (
    "table",
    "sql",
    "write_table",
    "merge",
    "autoload",
)


def _build_primitive_specs() -> dict[str, dict[str, Any]]:
    """Snapshot signatures and docstrings for the public PQL primitives.

    Computed once at import time and frozen — the PQL surface is part
    of the package, not a runtime-mutable contract, so a process-level
    cache is the right granularity.  The route handler returns the
    same dict on every call without re-introspecting.

    Returns:
        ``{name: {"name", "signature", "doc"}}`` for each primitive in
        :data:`_PRIMITIVES`.
    """
    specs: dict[str, dict[str, Any]] = {}
    for name in _PRIMITIVES:
        method = getattr(PQL, name)
        signature = str(inspect.signature(method))
        doc = inspect.getdoc(method) or ""
        specs[name] = {
            "name": name,
            "signature": f"{name}{signature}",
            "doc": doc,
        }
    return specs


_PRIMITIVE_SPECS: dict[str, dict[str, Any]] = _build_primitive_specs()


@router.get("/api/pql/primitives")
async def api_pql_primitives() -> dict[str, Any]:
    """Return the introspected signature + docstring for every PQL primitive.

    Designed for the ``pql_describe_primitive`` Hermes tool.  The
    plugin filters the response client-side so the LLM
    only sees one primitive at a time, but the server returns the
    full set in one round-trip — five entries fit comfortably in a
    single response and avoid a per-name HTTP hop when an agent
    wants to compare ``write_table`` vs ``merge`` vs ``autoload``
    before picking one.

    Returns:
        ``{"primitives": {"autoload": {...}, ...}}`` — the inner dicts
        carry ``name``, ``signature`` (e.g.
        ``"autoload(self, source_path: str, target: str, *, ...)"``),
        and ``doc`` (the Google-style docstring verbatim).
    """
    return {"primitives": _PRIMITIVE_SPECS}


def _split_three_part(full_name: str) -> tuple[str, str, str]:
    """Validate and split a ``catalog.schema.table`` UC reference.

    Args:
        full_name: Three-part dot-separated identifier.

    Returns:
        ``(catalog, schema, table)``.

    Raises:
        ValidationError: When the identifier is empty or has fewer
            than three non-empty parts.
    """
    parts = [p.strip() for p in full_name.split(".")]
    if len(parts) != 3 or not all(parts):
        raise ValidationError("table must be a three-part UC name 'catalog.schema.table'")
    return parts[0], parts[1], parts[2]


def _serialize_columns(columns_raw: Any) -> list[dict[str, Any]]:
    """Project the soyuz column payload to a tool-friendly subset.

    Soyuz returns rich column metadata; the agent only needs name +
    type to decide on join keys, so we trim aggressively to keep the
    LLM transcript small.

    Args:
        columns_raw: ``columns`` field from
            ``UnityCatalogClient.get_table``.

    Returns:
        List of ``{name, type_text, nullable, comment}`` dicts.
        Empty when the input is missing or malformed.
    """
    if not isinstance(columns_raw, list):
        return []
    out: list[dict[str, Any]] = []
    for col in columns_raw:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(col, dict):
            continue
        col_dict: dict[str, Any] = {
            str(k): v  # type: ignore[reportUnknownArgumentType]
            for k, v in col.items()  # type: ignore[reportUnknownVariableType]
        }
        out.append(
            {
                "name": col_dict.get("name"),
                "type_text": col_dict.get("type_text"),
                "nullable": col_dict.get("nullable"),
                "comment": col_dict.get("comment"),
            }
        )
    return out


def _last_writes_for_target(
    request: Request, full_name: str, *, limit: int = 5
) -> list[dict[str, Any]]:
    """Return the most recent ``agent_run_operations`` rows for *full_name*.

    Args:
        request: Incoming FastAPI request.
        full_name: Three-part UC identifier the operation targeted.
        limit: Hard cap on the rows returned (default 5).

    Returns:
        Newest-first list of compact dicts shaped for the
        ``target-state`` payload.  Operations without a
        ``finished_at`` timestamp (in-flight or crashed mid-run) sort
        last because ``finished_at DESC NULLS LAST`` is the SQL
        standard ordering.
    """
    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AgentRunOperation)
            .where(AgentRunOperation.target_table == full_name)
            .order_by(AgentRunOperation.finished_at.desc())
            .limit(limit)
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "ordinal": row.ordinal,
                    "op_name": row.op_name,
                    "agent_run_id": row.agent_run_id,
                    "rows_affected": row.rows_affected,
                    "delta_version_before": row.delta_version_before,
                    "delta_version_after": row.delta_version_after,
                    "finished_at": (row.finished_at.isoformat() if row.finished_at else None),
                    "error_message": row.error_message,
                }
            )
    return out


@router.get("/api/pql/target-state")
async def api_pql_target_state(
    request: Request,
    table: str = Query(..., description="catalog.schema.table"),
) -> dict[str, Any]:
    """Return the current state + recent-write history for one target table.

    Backs the ``pql_target_state`` Hermes tool.  An agent about to
    call ``pql.merge`` against a non-existent target can avoid a
    crash with one call to this route: an ``exists=False`` response
    tells the agent to pick ``write_table`` as the bootstrap path
    instead.

    The route fuses two reads into one response so the agent doesn't
    need to chain ``pql_get_table`` + a hypothetical operations-
    history call.  ``schema`` is ``None`` when the table doesn't
    exist; ``last_5_writes`` is empty when no agent run has touched
    the table yet (or when the catalog predates the forced
    audit-trail schema).

    Args:
        request: Incoming FastAPI request — supplies the
            principal-scoped UC client.
        table: Three-part UC identifier.

    Returns:
        ``{"table", "exists", "schema", "last_5_writes"}``.
        :func:`_split_three_part` raises :class:`ValidationError`
        when ``table`` lacks three non-empty parts; FastAPI's
        exception handlers translate that into a 400.
    """
    catalog, schema_name, table_name = _split_three_part(table)
    client = get_uc_client(request)
    exists = True
    columns: list[dict[str, Any]] = []
    try:
        info = await client.get_table(catalog, schema_name, table_name)
    except CatalogNotFoundError:
        exists = False
        info = {}
    if exists and info:
        columns = _serialize_columns(info.get("columns"))
    elif exists and not info:
        # UC returned an empty dict for an existing-but-unparseable
        # row — surface the table as existing but with no schema so
        # the agent doesn't reason from a fake "exists=False".
        columns = []
    return {
        "table": table,
        "exists": exists,
        "schema": columns if exists else None,
        "last_5_writes": _last_writes_for_target(request, table),
    }


_LINEAGE_MAX_DEPTH = 5


@router.get("/api/pql/lineage")
async def api_pql_lineage(
    request: Request,
    table: str = Query(..., description="catalog.schema.table"),
    depth: int = Query(default=2, ge=1, le=_LINEAGE_MAX_DEPTH),
) -> dict[str, Any]:
    """Return upstream + downstream lineage for a table in one response.

    Backs the ``pql_lineage`` Hermes tool.  Wraps
    :meth:`pointlessql.services.unitycatalog._lineage.LineageMixin.get_lineage`,
    which already fans out concurrently to soyuz's
    ``GET /lineage/upstream/{full_name}`` and
    ``GET /lineage/downstream/{full_name}`` JSON endpoints — pure
    PointlesSQL plumbing on top of an existing soyuz contract.

    The depth is capped at ``_LINEAGE_MAX_DEPTH`` (5) to keep the
    payload bounded for an LLM transcript even though soyuz tolerates
    up to 10 hops.

    Args:
        request: Incoming FastAPI request — supplies the
            principal-scoped UC client.
        table: Three-part UC identifier.
        depth: Hop count (1-5, default 2).

    Returns:
        ``{"table", "depth", "upstream": {...}, "downstream": {...}}``.
        Each direction carries the ``LineageGraphResponse`` shape from
        soyuz: ``{root, direction, nodes: [...], edges: [...]}``.
        Empty dicts when no lineage data exists for the table.
    """
    # Validate the three-part shape eagerly so the caller gets a 422
    # before the soyuz call runs.
    _split_three_part(table)
    client = get_uc_client(request)
    graph = await client.get_lineage(table, depth=depth)
    return {
        "table": table,
        "depth": depth,
        "upstream": graph.get("upstream", {}),
        "downstream": graph.get("downstream", {}),
    }


__all__ = ["router"]
