"""``pql.aggregate()`` — fan-in-aware aggregation primitive.

The third Medallion building block — bronze (autoload) → silver
(merge) → gold (aggregate).  Earlier sprints used ``pql.write_table(
..., mode="overwrite")`` after a pandas ``groupby`` to materialise
gold tables, which silently dropped the per-row lineage chain: the
``_lineage_row_id`` audit column on silver is N-to-1-aggregated and
cannot map to a single target row via the
:func:`pointlessql.services.lineage_edges.synth_target_row_id`
formula merge uses.

This primitive closes that gap.  For each output group it:

1. mints a deterministic ``_lineage_row_id`` via
   :func:`synth_aggregate_target_row_id` (hashes the group-key
   values, *not* any single source ID, so the target ID is stable
   across re-runs and independent of group ordering);
2. captures every source ``_lineage_row_id`` in the group;
3. stashes parallel arrays
   ``(source_row_ids, target_row_ids_replicated)`` on the
   recorder so the post-commit hook bulk-inserts N edges per group
   into ``lineage_row_edges``.

``source_table_fqn`` is **required** here, unlike the optional
kwargs on ``merge`` and ``write_table``: an aggregate without a
declared source produces no useful lineage at all, so we fail fast
rather than silently emit zero edges.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.pql._columns import columns_from_tuples
from pointlessql.pql._hashing import arrow_ipc_sha256
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._write import derive_storage_location, safe_delta_version
from pointlessql.pql.engine import Engine
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.lineage_edges import (
    ColumnEdgeSpec,
    synth_aggregate_target_row_id,
)
from pointlessql.types import OpName, RunId

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    import pandas as pd

LINEAGE_ROW_ID_COLUMN = "_lineage_row_id"

AggregateMode = Literal["overwrite", "append"]
AggSpec = tuple[str, "str | Callable[[Any], Any]"]


def aggregate_table(
    *,
    client: Client,
    engine: Engine,
    source_df: pd.DataFrame,
    target: str,
    group_by: list[str],
    aggs: dict[str, AggSpec],
    source_table_fqn: str,
    mode: AggregateMode = "overwrite",
    unreachable_msg: str,
    derivations: Mapping[str, Sequence[str]] | None = None,
    agent_run_id: str | None = None,
) -> dict[str, Any]:
    """Group-aggregate *source_df* into *target* and emit fan-in edges.

    Performs a pandas ``groupby(group_by).agg(...)`` and writes the
    resulting frame to the target Delta table.  When the source
    carries a ``_lineage_row_id`` column the output rows gain
    deterministic IDs and N→1 edges (one per source row per group)
    are stashed on the recorder for the post-commit hook to persist.

    Propagates :class:`AuditUnavailableError` from the operation
    recorder when *agent_run_id* is set and the
    ``agent_run_operations`` row cannot be persisted.

    Args:
        client: Configured ``soyuz_catalog_client.Client``.
        engine: Engine used to write the resulting frame.  The
            engine's ``write`` and ``columns_info`` methods are the
            only entry points the primitive uses.
        source_df: Pandas DataFrame to aggregate.  When the
            ``_lineage_row_id`` column is missing the primitive runs
            but emits zero edges (no fan-in lineage to record).
        target: UC ``"catalog.schema.table"`` string.  Created on
            first call when missing.
        group_by: Column names to group on.  Must be non-empty and
            present on *source_df*.
        aggs: Mapping ``output_col -> (source_col, agg_fn)`` —
            the same shape pandas' named aggregations accept.
            ``agg_fn`` is either a pandas aggregation name string
            (``"sum"``, ``"mean"``, ...) or a callable.
        source_table_fqn: Fully-qualified UC name of the upstream
            table that produced *source_df*.  **Required** —
            aggregate lineage without a declared source is a
            no-op against the row-trace UI, so we fail fast.
        mode: ``"overwrite"`` (default) or ``"append"``.  Mirrors
            :func:`pointlessql.pql._write.write_table` semantics.
        unreachable_msg: Pre-rendered "cannot reach catalog"
            message — same hop other primitives take.
        derivations: Optional declarative mapping of derived target
            columns (those produced by upstream ``.assign(...)`` /
            arithmetic / etc. before the aggregate call) to their
            source-column names.  populates
            ``derived`` rows in ``lineage_column_map`` so the
            column-trace UI can answer "where did ``placed_day``
            come from?" even when the primitive itself only saw the
            already-derived column.
        agent_run_id: Run UUID for forced-audit emission.  ``None``
            keeps the interactive path silent.

    Returns:
        ``{"target": str, "rows_written": int, "groups": int,
        "edges_emitted": int}``.

    Raises:
        ValidationError: When ``group_by`` is empty, columns are
            missing, ``source_table_fqn`` is empty, or the input
            frame is not a pandas DataFrame.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """
    if not group_by:
        raise ValidationError("aggregate requires at least one column in 'group_by'")
    if not source_table_fqn:
        raise ValidationError(
            "aggregate requires source_table_fqn — without a declared source, "
            "fan-in lineage cannot be recorded"
        )
    if not aggs:
        raise ValidationError("aggregate requires at least one entry in 'aggs'")

    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover — pandas is a hard dep
        raise ValidationError("aggregate requires pandas to be installed") from exc

    if not isinstance(source_df, pd.DataFrame):
        raise ValidationError(
            f"aggregate source must be a pandas DataFrame, got {type(source_df).__name__}"
        )

    missing = [col for col in group_by if col not in source_df.columns]
    if missing:
        raise ValidationError(
            f"aggregate group_by columns {missing!r} not present on source frame "
            f"({list(source_df.columns)!r})"
        )

    parse_full_name(target)

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    grouped_df, source_ids_per_group = _build_aggregate_frame(
        source_df=source_df,
        target=target,
        group_by=group_by,
        aggs=aggs,
    )

    flat_source_ids: list[str] = []
    flat_target_ids: list[str] = []
    for target_id, source_ids in source_ids_per_group:
        for sid in source_ids:
            flat_source_ids.append(sid)
            flat_target_ids.append(target_id)

    with operation_context(
        factory,
        agent_run_id=cast(RunId | None, agent_run_id),
        op_name=OpName.AGGREGATE,
        params={
            "target": target,
            "group_by": list(group_by),
            "aggs": {k: [v[0], _agg_repr(v[1])] for k, v in aggs.items()},
            "mode": mode,
        },
        target_table=target,
    ) as recorder:
        location, table_exists = _resolve_or_plan_target(
            client=client,
            target=target,
            unreachable_msg=unreachable_msg,
        )

        if agent_run_id is not None:
            if table_exists:
                recorder.delta_version_before = safe_delta_version(location)
            try:
                recorder.input_sha = arrow_ipc_sha256(grouped_df)
            except TypeError:
                recorder.input_sha = None
            recorder.rows_affected = int(len(grouped_df))
            recorder.extra_params = {
                **recorder.extra_params,
                "source_table_fqn": source_table_fqn,
                "groups": int(len(grouped_df)),
                "edges_emitted": len(flat_source_ids),
            }
            if flat_source_ids:
                recorder.pending_lineage_edges = {
                    "source_table": source_table_fqn,
                    "source_row_ids": flat_source_ids,
                    "target_row_ids": flat_target_ids,
                }

            recorder.pending_column_edges = _build_aggregate_column_edges(
                source_df=source_df,
                source_table_fqn=source_table_fqn,
                target=target,
                group_by=group_by,
                aggs=aggs,
                derivations=derivations,
            )

        try:
            engine.write(grouped_df, location, mode)
            if agent_run_id is not None:
                recorder.delta_version_after = safe_delta_version(location)

            if not table_exists:
                columns = columns_from_tuples(engine.columns_info(grouped_df))
                catalog, schema, table_name = parse_full_name(target)
                body = CreateTable(
                    catalog_name=catalog,
                    schema_name=schema,
                    name=table_name,
                    table_type="MANAGED",
                    data_source_format="DELTA",
                    columns=columns,
                    storage_location=location,
                )
                _create_table.sync(client=client, body=body)
        except httpx.ConnectError as exc:
            raise CatalogUnavailableError(unreachable_msg) from exc

        return {
            "target": target,
            "rows_written": int(len(grouped_df)),
            "groups": int(len(grouped_df)),
            "edges_emitted": len(flat_source_ids),
        }


def _build_aggregate_frame(
    *,
    source_df: pd.DataFrame,
    target: str,
    group_by: list[str],
    aggs: dict[str, AggSpec],
) -> tuple[pd.DataFrame, list[tuple[str, list[str]]]]:
    """Run the groupby-aggregation and stamp ``_lineage_row_id`` on the result.

    Args:
        source_df: Source pandas DataFrame.
        target: Fully-qualified UC name (used to derive deterministic
            target row IDs).
        group_by: Column names to group on.
        aggs: ``output_col -> (source_col, agg_fn)`` mapping.

    Returns:
        ``(grouped_df, source_ids_per_group)``.  ``grouped_df`` has
        the group-by columns, the user's aggregation outputs, and a
        ``_lineage_row_id`` column with deterministic IDs.
        ``source_ids_per_group`` is a list of
        ``(target_row_id, [source_row_id, ...])`` tuples in the same
        order as ``grouped_df`` rows — empty source list when the
        source frame had no ``_lineage_row_id`` column.
    """
    has_lineage = LINEAGE_ROW_ID_COLUMN in source_df.columns

    per_group: pd.DataFrame | None
    if has_lineage:
        per_group = cast(
            "pd.DataFrame",
            source_df[[*group_by, LINEAGE_ROW_ID_COLUMN]]
            .groupby(list(group_by), as_index=False, sort=False)
            .agg(_pql_source_ids=(LINEAGE_ROW_ID_COLUMN, list)),
        )
    else:
        per_group = None

    named_aggs = {out_col: (src_col, agg_fn) for out_col, (src_col, agg_fn) in aggs.items()}
    grouped = cast(
        "pd.DataFrame",
        source_df.groupby(list(group_by), as_index=False, sort=False).agg(**named_aggs),
    )

    target_ids: list[str] = []
    source_ids_per_group: list[tuple[str, list[str]]] = []

    if per_group is not None:
        merged_df = grouped.merge(per_group, on=list(group_by), how="left")
        for _, row in merged_df.iterrows():
            group_values: list[Any] = [row[col] for col in group_by]
            tid = synth_aggregate_target_row_id(target, group_values)
            sids_raw: Any = row["_pql_source_ids"]
            sids = [str(s) for s in sids_raw] if isinstance(sids_raw, list) else []
            target_ids.append(tid)
            source_ids_per_group.append((tid, sids))
    else:
        for _, row in grouped.iterrows():
            group_values = [row[col] for col in group_by]
            tid = synth_aggregate_target_row_id(target, group_values)
            target_ids.append(tid)
            source_ids_per_group.append((tid, []))

    grouped[LINEAGE_ROW_ID_COLUMN] = target_ids
    return grouped, source_ids_per_group


def _resolve_or_plan_target(
    *, client: Client, target: str, unreachable_msg: str
) -> tuple[str, bool]:
    """Return ``(storage_location, table_exists)`` for *target*.

    Looks the table up in soyuz-catalog; if missing, derives a
    storage location from the parent schema's ``storage_root`` so
    the engine can write before the catalog row is created.
    Propagates :class:`CatalogNotFoundError` from
    :func:`derive_storage_location` when the parent schema lacks a
    storage root.

    Args:
        client: Configured catalog client.
        target: UC ``"catalog.schema.table"`` string.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        ``(location, table_exists)``.  When the table already exists
        the location is its registered ``storage_location``;
        otherwise it is the derived path under the schema's storage
        root and the caller must register the new table after the
        write.

    Raises:
        CatalogUnavailableError: When soyuz-catalog is unreachable.
        UnexpectedStatus: For any non-404 soyuz-catalog response to
            the table lookup.
    """
    table_exists = False
    location: str | None = None

    try:
        response = _get_table.sync(client=client, full_name=target)
        if isinstance(response, TableInfo):
            loc = response.storage_location
            if not isinstance(loc, Unset) and loc:
                location = loc
                table_exists = True
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    except UnexpectedStatus as exc:
        if exc.status_code != 404:
            raise

    if not table_exists:
        catalog, schema, table_name = parse_full_name(target)
        location = derive_storage_location(client, catalog, schema, table_name)

    assert location is not None  # noqa: S101 — guarded above
    return location, table_exists


def _build_aggregate_column_edges(
    *,
    source_df: pd.DataFrame,
    source_table_fqn: str,
    target: str,
    group_by: list[str],
    aggs: dict[str, AggSpec],
    derivations: Mapping[str, Sequence[str]] | None,
) -> list[ColumnEdgeSpec]:
    """Translate aggregate signals into ``lineage_column_map`` edges.

    ``pql.aggregate`` is the most expressive of the PQL primitives
    column-wise: ``aggs`` already encodes the source→target mapping
    explicitly, and ``group_by`` columns carry through as identity
    edges.  ``derivations`` covers the Pre-aggregate ``.assign(...)``
    pattern.  Every edge gets ``source_table_fqn`` since aggregate
    requires it (we fail-fast above when missing).

    Args:
        source_df: Source DataFrame the aggregation ran against.
        source_table_fqn: Fully-qualified UC name of the source.
        target: Fully-qualified UC name of the target.
        group_by: Group-by column names.
        aggs: ``{output_col: (source_col, agg_fn)}`` mapping.
        derivations: Optional ``{target_col: [source_col, ...]}``
            mapping for upstream-of-aggregate column derivations.

    Returns:
        Specs describing every (source_column, target_column) edge:
        identity edges for group-by columns, ``aggregate`` edges
        with ``transform_detail=agg_fn_name`` for ``aggs`` outputs,
        ``derived`` edges for declared derivations, plus a single
        ``derived`` edge for the synthesised ``_lineage_row_id``
        column with ``transform_detail="synth_target_row_id"``.
    """
    src_columns: set[str] = set(source_df.columns)
    edges: list[ColumnEdgeSpec] = []

    # Group-by columns: identity edges.  Override with derivations
    # when the caller declared one (e.g. placed_day derived from
    # placed_at, used as a group-by key).
    derivations = derivations or {}
    for col in group_by:
        if col in derivations:
            for src_col in derivations[col]:
                if src_col in src_columns:
                    edges.append(
                        ColumnEdgeSpec(
                            source_table=source_table_fqn,
                            source_column=src_col,
                            target_table=target,
                            target_column=col,
                            transform_kind="derived",
                            transform_detail=None,
                        )
                    )
                else:
                    edges.append(
                        ColumnEdgeSpec(
                            source_table=None,
                            source_column=None,
                            target_table=target,
                            target_column=col,
                            transform_kind="unknown_origin",
                            transform_detail=(
                                f"derivation references {src_col!r} which is not on source"
                            ),
                        )
                    )
            continue
        if col in src_columns:
            edges.append(
                ColumnEdgeSpec(
                    source_table=source_table_fqn,
                    source_column=col,
                    target_table=target,
                    target_column=col,
                    transform_kind="identity",
                    transform_detail=None,
                )
            )
        else:
            edges.append(
                ColumnEdgeSpec(
                    source_table=None,
                    source_column=None,
                    target_table=target,
                    target_column=col,
                    transform_kind="unknown_origin",
                    transform_detail=None,
                )
            )

    # Aggregation outputs: aggregate edges; pre-aggregate derivations
    # extend the chain with derived edges from the *real* source.
    for out_col, (src_col, agg_fn) in aggs.items():
        agg_label = _agg_repr(agg_fn)
        if src_col in derivations:
            for upstream in derivations[src_col]:
                if upstream in src_columns:
                    edges.append(
                        ColumnEdgeSpec(
                            source_table=source_table_fqn,
                            source_column=upstream,
                            target_table=target,
                            target_column=out_col,
                            transform_kind="derived",
                            transform_detail=(f"via {src_col!r} → {agg_label}({src_col!r})"),
                        )
                    )
                else:
                    edges.append(
                        ColumnEdgeSpec(
                            source_table=None,
                            source_column=None,
                            target_table=target,
                            target_column=out_col,
                            transform_kind="unknown_origin",
                            transform_detail=(
                                f"derivation references {upstream!r} which is not on source"
                            ),
                        )
                    )
            continue
        if src_col in src_columns:
            edges.append(
                ColumnEdgeSpec(
                    source_table=source_table_fqn,
                    source_column=src_col,
                    target_table=target,
                    target_column=out_col,
                    transform_kind="aggregate",
                    transform_detail=agg_label,
                )
            )
        else:
            edges.append(
                ColumnEdgeSpec(
                    source_table=None,
                    source_column=None,
                    target_table=target,
                    target_column=out_col,
                    transform_kind="unknown_origin",
                    transform_detail=f"aggregate {agg_label} on missing column {src_col!r}",
                )
            )

    # Synthesised _lineage_row_id is "derived" from the source's
    # row ID column (when present) — let agents trace where a
    # gold row id ultimately comes from.
    if LINEAGE_ROW_ID_COLUMN in src_columns:
        edges.append(
            ColumnEdgeSpec(
                source_table=source_table_fqn,
                source_column=LINEAGE_ROW_ID_COLUMN,
                target_table=target,
                target_column=LINEAGE_ROW_ID_COLUMN,
                transform_kind="derived",
                transform_detail="synth_target_row_id",
            )
        )

    return edges


def _agg_repr(agg_fn: str | Callable[[Any], Any]) -> str:
    """Stringify an aggregation function for the audit ``params_json``.

    Args:
        agg_fn: Either a pandas aggregation name (``"sum"``,
            ``"mean"``, ...) or a callable.

    Returns:
        The string itself for string inputs; ``"<callable>"`` for
        callables (we deliberately do not try to capture lambda
        bodies — agent reproducibility relies on the input SHA, not
        on the textual params).
    """
    return agg_fn if isinstance(agg_fn, str) else "<callable>"
