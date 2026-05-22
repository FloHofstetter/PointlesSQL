# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""Shared helpers for the row-trace and column-trace route surfaces.

The row-trace and column-trace endpoints each go through the same
auth gate, op-metadata join, value-change attachment, CDF-event
attachment, and PII-masking pass.  Pulling all of that into one
``_helpers`` module keeps the route bodies short and the test surface
narrow (single import path for each helper).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
)
from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.models import AgentRunOperation
from pointlessql.services.authorization import SELECT, check_privilege
from pointlessql.services.cdf_tail import fetch_events_for_row as fetch_cdf_events_for_row
from pointlessql.services.lineage_edges import (
    LineageStep,
    PredecessorRef,
    fetch_value_changes_for_row,
    lookup_bronze_source_file,
)
from pointlessql.services.pii import _mask as pii_mask
from pointlessql.services.pii import _resolver as pii_resolver

logger = logging.getLogger(__name__)

_MAX_HOPS = 20


def _get_session_factory() -> Any:
    """Return the global SQLAlchemy session factory.

    Wrapped in a helper so the route bodies stay readable and so
    tests can patch the lookup without monkey-patching the dotted
    path inside two separate handlers.
    """
    from pointlessql.db import get_session_factory

    return get_session_factory()


async def _enforce_select(request: Request, full_name: str) -> None:
    """Reject the request when the caller lacks SELECT on *full_name*.

    Args:
        request: Incoming FastAPI request.
        full_name: Three-part UC name to authorise against.
    """  # noqa: DOC502 — propagates AuthorizationError from check_privilege
    client = get_uc_client(request)
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )


def _predecessor_to_dict(
    pred: PredecessorRef, op_meta: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """Project a :class:`PredecessorRef` into the JSON payload shape.

    Args:
        pred: One predecessor edge feeding a step.
        op_meta: Joined op metadata; see :func:`_step_to_dict`.

    Returns:
        Dict with ``table`` / ``row_id`` / ``op_id`` / ``op_name`` /
        ``run_id`` keys.  ``op_name`` is ``None`` when the join row
        is missing (deleted run, FK orphan).
    """
    meta = op_meta.get(pred.op_id) if pred.op_id is not None else None
    return {
        "table": pred.table,
        "row_id": pred.row_id,
        "op_id": pred.op_id,
        "op_name": meta.get("op_name") if meta else None,
        "run_id": pred.run_id,
    }


def _step_to_dict(step: LineageStep, op_meta: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Project a :class:`LineageStep` into the JSON payload shape.

    Args:
        step: One walkback step.
        op_meta: ``{op_id: {"op_name": str, "agent_run_id": str |
            None}}`` joined off ``agent_run_operations`` for every
            distinct ``op_id`` referenced by the steps **or** by
            their predecessors.

    Returns:
        Dict with ``depth`` / ``table`` / ``row_id`` / ``op_id`` /
        ``op_name`` / ``run_id`` / ``source_file`` /
        ``predecessors`` / ``value_changes`` / ``cdf_events`` keys.
        ``predecessors`` is the full list of edges feeding this row
        — length > 1 indicates fan-in (aggregate op or repeated
        re-runs).  ``value_changes`` is the per-cell
        preimage/postimage list for this step's ``(table, row_id)``
        pair, empty when no merge with ``track_value_changes=True``
        has touched this row.  ``cdf_events`` is the captured
        foreign-Delta CDF tail history for the same pair, empty
        when no subscription has captured events for this row.
    """
    meta = op_meta.get(step.op_id) if step.op_id is not None else None
    return {
        "depth": step.depth,
        "table": step.table,
        "row_id": step.row_id,
        "op_id": step.op_id,
        "op_name": meta.get("op_name") if meta else None,
        "run_id": step.run_id,
        "source_file": step.source_file,
        "predecessors": [_predecessor_to_dict(p, op_meta) for p in step.predecessors],
        "value_changes": [],
        "cdf_events": [],
    }


def _attach_value_changes(factory: Any, step_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Populate the ``value_changes`` key on each step from the metadata DB.

    best-effort lookup that runs once per row-trace
    render.  Each step probe is one indexed query on
    ``(target_table, target_row_id)``; max-hops is 20, so the call
    is bounded to ≤20 lightweight reads.

    every emitted change carries ``is_pii=False``
    initially and ``display_old`` / ``display_new`` mirror the raw
    values; :func:`_apply_pii_masking` mutates those fields in
    place after the soyuz tag lookup completes.

    Args:
        factory: SQLAlchemy session factory.
        step_dicts: Already-projected step dicts (output of
            :func:`_step_to_dict`).

    Returns:
        The same list, mutated in place — each step's
        ``value_changes`` list is replaced with the ``[{column,
        old_value, new_value, run_id, op_id, created_at, is_pii,
        display_old, display_new}]`` entries for its ``(table,
        row_id)``.
    """
    for step in step_dicts:
        rows = fetch_value_changes_for_row(
            factory,
            target_table=step["table"],
            target_row_id=step["row_id"],
        )
        step["value_changes"] = [
            {
                "target_column": r.target_column,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "run_id": r.run_id,
                "op_id": r.op_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "is_pii": False,
                "display_old": r.old_value if r.old_value is not None else None,
                "display_new": r.new_value if r.new_value is not None else None,
            }
            for r in rows
        ]
    return step_dicts


def _attach_cdf_events(
    factory: Any,
    step_dicts: list[dict[str, Any]],
    *,
    workspace_id: int,
) -> list[dict[str, Any]]:
    """Populate the ``cdf_events`` key on each step from the CDF tail log.

    Mirrors :func:`_attach_value_changes` for the Phase-40.5/40.6
    foreign-Delta CDF capture stream.  Per step a single indexed
    point-lookup on ``(workspace_id, table_full_name, row_id)`` —
    bounded to ≤20 reads at the default ``max_hops``.  Events are
    captured for foreign tables that PointlesSQL didn't write but
    the operator subscribed to; folding them in here gives the
    audit-reviewer a unified view of "everything that ever happened
    to this row".

    Workspace-scoping is mandatory: row identifiers are stringified
    foreign-key values that two installs could collide on by
    accident (e.g. both seed an ``id=1`` row in
    ``demo.silver.orders``).

    Args:
        factory: SQLAlchemy session factory.
        step_dicts: Already-projected step dicts (output of
            :func:`_step_to_dict`).
        workspace_id: Active workspace; passed through to the
            service-layer helper.

    Returns:
        The same list, mutated in place — each step's ``cdf_events``
        list is replaced with ``[{id, delta_version, change_type,
        commit_timestamp, created_at, producer_label}]`` entries.
        Steps with no matching events keep an empty list so
        templates can ``{% if step.cdf_events %}`` without
        :class:`KeyError`.
    """
    for step in step_dicts:
        events = fetch_cdf_events_for_row(
            factory,
            workspace_id=workspace_id,
            table_full_name=step["table"],
            row_id=step["row_id"],
        )
        step["cdf_events"] = [
            {
                "id": e.id,
                "delta_version": e.delta_version,
                "change_type": e.change_type,
                "commit_timestamp": e.commit_timestamp.isoformat() if e.commit_timestamp else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "producer_label": e.producer_label,
            }
            for e in events
        ]
    return step_dicts


async def _apply_pii_masking(
    request: Request,
    step_dicts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve PII tags for every value-change column and mask in place.

    runs once per row-trace render *after*
    :func:`_attach_value_changes` so the mutated ``display_old`` /
    ``display_new`` fields override the raw cleartext when the
    soyuz tag system flags the column as PII.

    Disabled globally when
    :attr:`AuditSettings.pii_mask_default` is ``False`` — the
    whole helper is a no-op in that case.  Otherwise resolves all
    unique ``(target_table, target_column)`` pairs in one batch.

    Args:
        request: Incoming FastAPI request.  Used to pull
            ``app.state.uc_client`` and the audit settings.
        step_dicts: Step list with ``value_changes`` already
            populated by :func:`_attach_value_changes`.

    Returns:
        The same step list, mutated in place.
    """
    settings = request.app.state.settings
    if not getattr(settings.audit, "pii_mask_default", True):
        return step_dicts
    flat_pairs: list[tuple[str, str]] = []
    for step in step_dicts:
        for change in step.get("value_changes", []):
            flat_pairs.append((step["table"], change["target_column"]))
    if not flat_pairs:
        return step_dicts
    uc = getattr(request.app.state, "uc_client", None)
    if uc is None:
        return step_dicts
    pii_map = await pii_resolver.resolve_many(
        uc,
        flat_pairs,
        ttl_seconds=settings.audit.pii_cache_ttl_seconds,
    )
    for step in step_dicts:
        for change in step.get("value_changes", []):
            key = (step["table"], change["target_column"])
            if pii_map.get(key, False):
                change["is_pii"] = True
                change["display_old"] = (
                    pii_mask.mask_value(change["old_value"])
                    if change["old_value"] is not None
                    else None
                )
                change["display_new"] = (
                    pii_mask.mask_value(change["new_value"])
                    if change["new_value"] is not None
                    else None
                )
    return step_dicts


async def _enrich_with_source_file(request: Request, steps: list[LineageStep]) -> list[LineageStep]:
    """Stamp ``source_file`` onto the deepest step from the bronze table.

    Looks the storage location up via the soyuz UC client, then
    probes the Delta table with DuckDB.  Anything that goes wrong
    (table missing, column dropped, library import failure) leaves
    the step unchanged — the trace is still useful without the
    file label.

    Args:
        request: Incoming FastAPI request (for the UC client).
        steps: Walkback steps as returned by
            :func:`pointlessql.services.lineage_edges.walk_back`.

    Returns:
        A new list with the deepest step replaced by an enriched
        copy when the lookup succeeded; otherwise the original
        list, identity-preserving.
    """
    if not steps:
        return steps
    deepest = steps[-1]
    if deepest.source_file is not None:
        return steps

    parts = deepest.table.split(".")
    if len(parts) != 3:
        return steps

    client = get_uc_client(request)
    try:
        info = await client.get_table(parts[0], parts[1], parts[2])
    except (CatalogNotFoundError, CatalogUnavailableError):
        return steps
    except Exception:  # noqa: BLE001 — best-effort enrichment
        logger.debug(
            "row-trace: failed to resolve storage_location for %s",
            deepest.table,
            exc_info=True,
        )
        return steps

    storage_location = info.get("storage_location") if info else None
    if not isinstance(storage_location, str) or not storage_location:
        return steps

    source_file = lookup_bronze_source_file(
        table=deepest.table,
        row_id=deepest.row_id,
        storage_location=storage_location,
    )
    if source_file is None:
        return steps

    enriched = LineageStep(
        depth=deepest.depth,
        table=deepest.table,
        row_id=deepest.row_id,
        op_id=deepest.op_id,
        run_id=deepest.run_id,
        source_file=source_file,
        predecessors=deepest.predecessors,
    )
    return [*steps[:-1], enriched]


def _collect_op_ids(steps: list[LineageStep]) -> set[int]:
    """Collect every ``op_id`` referenced by *steps* or their predecessors.

    Args:
        steps: Walkback result from
            :func:`pointlessql.services.lineage_edges.walk_back`.

    Returns:
        Set of op IDs to look up in ``agent_run_operations`` so the
        JSON / HTML response can label every edge with its op_name.
    """
    ids: set[int] = set()
    for step in steps:
        if step.op_id is not None:
            ids.add(step.op_id)
        for pred in step.predecessors:
            if pred.op_id is not None:
                ids.add(pred.op_id)
    return ids


def _load_op_metadata(op_ids: set[int]) -> dict[int, dict[str, Any]]:
    """Fetch ``op_name`` / ``principal`` for every referenced op.

    Args:
        op_ids: Operation IDs collected from the walkback steps.

    Returns:
        ``{op_id: {"op_name": str, "principal": str | None}}``.
        Missing ops (deleted runs, FK orphans) are absent from the
        result; the caller renders a "—" in their place.
    """
    if not op_ids:
        return {}
    factory = _get_session_factory()
    with factory() as session:
        stmt = select(
            AgentRunOperation.id,
            AgentRunOperation.op_name,
            AgentRunOperation.agent_run_id,
        ).where(AgentRunOperation.id.in_(op_ids))
        result: dict[int, dict[str, Any]] = {}
        for row in session.execute(stmt).all():
            result[int(row[0])] = {"op_name": row[1], "agent_run_id": row[2]}
        return result
