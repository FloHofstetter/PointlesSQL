"""``pql.merge()`` — thin facade over Delta MERGE.

The merge primitive is one of the Medallion building blocks that
turn an agent run into a Medallion lakehouse: ``autoload`` lifts
files into bronze, ``merge`` consolidates bronze → silver, and a SQL
aggregation produces gold.  Silver is where upsert semantics matter
— gold writes are typically full-overwrite or append-truncate.

Two strategies in scope:

* ``upsert`` — match on the supplied keys; update all non-key
  columns from source on match, insert new rows otherwise.
  Standard SCD-1 semantics.
* ``scd2`` — append-only history.  Source rows are augmented with
  ``_valid_from`` / ``_valid_to`` / ``_is_current`` columns; a key
  match closes the currently-open target row (``_valid_to=now``,
  ``_is_current=false``) and appends a new current row.  Note:
  the MVP closes + reopens for *every* source row whose key
  matches a current target row, even when the values are
  unchanged.  Pre-filter the source to only "actually changed"
  rows if churn-free history matters — change detection inside
  the primitive would force schema-aware comparison and is
  deliberately deferred.

The audit column names are hardcoded here rather than read from
:mod:`pointlessql.conventions` because they are silver-layer
specific (audit columns in conventions are bronze-specific).  A
later iteration may promote them to a configurable field on
:class:`pointlessql.conventions.LayerConvention` if a real
override case appears.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal, cast

import deltalake
import httpx
import pyarrow as pa
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.enums import OpName
from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.identifiers import RunId
from pointlessql.pql._hashing import arrow_ipc_sha256
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._read import read_table
from pointlessql.pql.engine import Engine
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.lineage_edges import ColumnEdgeSpec, synth_target_row_id

logger = logging.getLogger(__name__)

LINEAGE_ROW_ID_COLUMN = "_lineage_row_id"

MergeStrategy = Literal["upsert", "scd2"]

SCD2_VALID_FROM = "_valid_from"
SCD2_VALID_TO = "_valid_to"
SCD2_IS_CURRENT = "_is_current"


def merge_table(
    *,
    client: Client,
    engine: Engine,
    source: Any,
    target: str,
    on: list[str],
    strategy: MergeStrategy,
    unreachable_msg: str,
    agent_run_id: str | None = None,
    source_table_fqn: str | None = None,
    source_model_uri: str | None = None,
    track_rejects: bool = False,
    track_value_changes: bool = False,
    derivations: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Merge *source* into the existing Delta table at *target*.

    The target table must already exist in soyuz-catalog with a
    ``storage_location``; the primitive does not bootstrap a
    table — that is the autoload primitive's job.

    Args:
        client: Configured ``soyuz_catalog_client.Client``.
        engine: Engine to read *source* with when it is a UC
            reference.  Ignored when *source* is already a frame.
        source: Either a pandas DataFrame (or any frame the engine
            knows how to read) **or** a UC ``"catalog.schema.table"``
            string that resolves through :func:`read_table`.
        target: UC ``"catalog.schema.table"`` string.  Must exist.
        on: Non-empty list of column names that together form the
            merge key.  Every key column must be present in the
            source frame.
        strategy: ``"upsert"`` or ``"scd2"``.
        unreachable_msg: Pre-rendered "cannot reach catalog"
            message — same hop the read/write helpers take.
        agent_run_id: When set, emits one ``agent_run_operations``
            row capturing input SHA, Delta version pre/post, and
            merge stats.
        source_table_fqn: When set, declared as the upstream UC
            input on the OpenLineage event emitted to soyuz so the
            cross-table edge ``source_table_fqn → target`` appears
            in the lineage graph.  ``None`` when the
            source is an in-memory frame with no UC origin — the
            audit row is still written but no lineage edge appears.
        source_model_uri: when set, declares the
            originating registered-model URI
            (``models:/cat.sch.model/<version>``) so every
            ``lineage_row_edges`` row produced by this merge carries
            the model provenance.  Effective only when
            ``source_table_fqn`` is also set (the row-edge grain
            needs a source table to be meaningful).
            extension mirroring :func:`pointlessql.pql._write.write_table`.
        track_rejects: When ``True``, scan the source frame for
            rows that won't land in the target (NULL ``on`` keys,
            duplicate keys within the source) and bulk-insert one
            ``lineage_row_rejects`` row per rejected source row
           .  ``False`` (default) skips the scan —
            performance-conservative; production callers that need
            reject visibility flip it on explicitly.  Effective
            only when the source carries ``_lineage_row_id`` and
            ``source_table_fqn`` is declared (no source identity =
            no useful reject row).
        track_value_changes: When ``True`` and ``strategy="upsert"``,
            read the Delta Change Data Feed for the merge's commit
            range and record one ``lineage_value_changes`` row per
            actually-different cell on a matched-and-updated target
            row.  Requires ``_lineage_row_id`` on
            both source and target rows so preimage/postimage events
            can be paired.  Silently ignored on ``strategy="scd2"``
            because SCD-2 already encodes value history in the
            ``_valid_from`` / ``_valid_to`` / ``_is_current`` triple.
            ``False`` (default) skips the CDF read — production
            callers that want the audit trail flip it on explicitly.
        derivations: Optional declarative mapping of derived target
            columns to their *true* source-column names (Sprint
            15.6.2).  Populates ``derived`` rows in
            ``lineage_column_map`` so the column-trace UI can
            answer "where did this column come from?" even when the
            primitive only saw the already-derived column.

    Returns:
        A dict carrying ``strategy`` and the deltalake merge stats
        (row counts).  SCD-2 also reports the appended-rows count.

    Raises:
        ValidationError: When ``on`` is empty, ``strategy`` is
            unknown, or a key column is missing from the source.
        CatalogNotFoundError: When *target* is unknown to
            soyuz-catalog or has no ``storage_location``.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
        AuditUnavailableError: If *agent_run_id* is set and the
            ``agent_run_operations`` row cannot be persisted.
    """  # noqa: DOC503 — Catalog* errors propagate from helpers below
    if not on:
        raise ValidationError("merge requires at least one column in 'on'")
    if strategy not in ("upsert", "scd2"):
        raise ValidationError(f"strategy must be 'upsert' or 'scd2', got {strategy!r}")

    parse_full_name(target)
    target_location = _resolve_target_location(client, target, unreachable_msg)
    source_frame = _resolve_source_frame(client, engine, source, unreachable_msg)

    arrow_source = _frame_to_arrow(source_frame)

    missing = [col for col in on if col not in arrow_source.schema.names]
    if missing:
        raise ValidationError(
            f"merge keys {missing!r} are not present in the source schema "
            f"({arrow_source.schema.names!r})"
        )

    from pointlessql.db import get_session_factory
    from pointlessql.pql._write import safe_delta_version

    factory = get_session_factory() if agent_run_id else None

    rejects: list[tuple[str, str, str | None]] = []
    if track_rejects and source_table_fqn:
        arrow_source, rejects = _detect_rejects(arrow_source, on)

    source_row_ids, target_row_ids, arrow_source = _prepare_lineage(arrow_source, target)

    with operation_context(
        factory,
        agent_run_id=cast(RunId | None, agent_run_id),
        op_name=OpName.MERGE,
        params={"target": target, "on": list(on), "strategy": strategy},
        target_table=target,
    ) as recorder:
        # bootstrap CDF on the target BEFORE capturing
        # ``delta_version_before`` so the merge commit lands with CDF
        # on regardless of the target's history.  For tables created
        # via :func:`pql.write_table` this is a no-op (CDF was set
        # post-create); the load-bearing case is non-pql-created
        # targets where ``ensure_cdf_enabled`` running AFTER the merge
        # would mean ``load_cdf`` returns nothing for the just-committed
        # merge.
        if agent_run_id is not None and track_value_changes and strategy == "upsert":
            from pointlessql.pql._cdf import ensure_cdf_enabled

            ensure_cdf_enabled(target_location)

        if agent_run_id is not None:
            recorder.delta_version_before = safe_delta_version(target_location)
            try:
                recorder.input_sha = arrow_ipc_sha256(arrow_source)
            except TypeError:
                recorder.input_sha = None

        # Phase 50.3 — data-product contract enforcement.  Same shape
        # as in ``pql/_write.py``: resolve the cached contract for the
        # target's schema, diff the arrow source's schema against the
        # table contract, and either stamp the recorder for the post-
        # commit event or raise a ``DataProductContractViolation``
        # *before* the merge runs so the bad write never lands.
        if agent_run_id is not None and factory is not None:
            from pointlessql.data_products import check_contract_for_write

            target_catalog, target_schema, target_table = parse_full_name(target)
            arrow_columns: list[tuple[str, str, str, bool]] = []
            for field in arrow_source.schema:  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
                fname = cast(str, field.name)  # pyright: ignore[reportUnknownMemberType]
                ftype = str(field.type)  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType]
                fnullable = cast(bool, field.nullable)  # pyright: ignore[reportUnknownMemberType]
                arrow_columns.append((fname, ftype.upper(), ftype, fnullable))
            enforcement = check_contract_for_write(
                factory=factory,
                agent_run_id=agent_run_id,
                catalog=target_catalog,
                schema=target_schema,
                table=target_table,
                df_columns=arrow_columns,
                mode=strategy,
            )
            if enforcement.outcome != "no_contract":
                recorder.pending_contract_event = (
                    enforcement.outcome,
                    enforcement.details,
                    enforcement.data_product_id,
                )
            if enforcement.violation is not None:
                raise enforcement.violation

        if strategy == "upsert":
            stats = _do_upsert(target_location, arrow_source, on)
        else:
            stats = _do_scd2(target_location, arrow_source, on)

        if agent_run_id is not None:
            recorder.delta_version_after = safe_delta_version(target_location)
            recorder.rows_affected = _merge_rows_affected(stats)
            extras: dict[str, Any] = {"stats": _stats_for_audit(stats)}
            if source_table_fqn:
                extras["source_table_fqn"] = source_table_fqn
            if source_model_uri:
                extras["source_model_uri"] = source_model_uri
            recorder.extra_params = extras
            if source_row_ids and source_table_fqn:
                recorder.pending_lineage_edges = {
                    "source_table": source_table_fqn,
                    "source_row_ids": source_row_ids,
                    "target_row_ids": target_row_ids,
                    "source_model_uri": source_model_uri,
                }
            if rejects and source_table_fqn:
                recorder.pending_rejects = {
                    "source_table": source_table_fqn,
                    "rejects": rejects,
                }

            if source_table_fqn:
                from pointlessql.services.column_lineage_diff import infer_column_edges

                target_columns = list(arrow_source.schema.names)
                edges = infer_column_edges(
                    source_columns=target_columns,
                    target_columns=target_columns,
                    source_table=source_table_fqn,
                    target_table=target,
                    derivations=derivations,
                )
                if "_lineage_row_id" in target_columns:
                    edges = [
                        e
                        for e in edges
                        if not (
                            e.target_column == "_lineage_row_id" and e.transform_kind == "identity"
                        )
                    ]
                    edges.append(
                        ColumnEdgeSpec(
                            source_table=source_table_fqn,
                            source_column="_lineage_row_id",
                            target_table=target,
                            target_column="_lineage_row_id",
                            transform_kind="derived",
                            transform_detail="synth_target_row_id",
                        )
                    )
                if edges:
                    recorder.pending_column_edges = edges

            if track_value_changes:
                if strategy != "upsert":
                    logger.info(
                        "track_value_changes ignored for strategy=%s "
                        "(value history is in the SCD-2 columns)",
                        strategy,
                    )
                else:
                    recorder.pending_value_changes = _capture_value_changes(
                        target_location=target_location,
                        target=target,
                        version_before=recorder.delta_version_before,
                        version_after=recorder.delta_version_after,
                    )

        return stats


def _capture_value_changes(
    *,
    target_location: str,
    target: str,
    version_before: int | None,
    version_after: int | None,
) -> list[Any] | None:
    """Best-effort capture of per-cell value changes from Delta CDF.

    runs after ``_do_upsert`` returns and the audit
    row has its delta_version_before / delta_version_after stamped.
    assumes the caller already enabled CDF on the
    target before ``_do_upsert`` (so the merge commit lands with CDF
    on); this helper just reads the stream and pairs events.  Any
    failure (deltalake error, missing ``_lineage_row_id``) is logged
    at INFO and returns ``None`` so the merge that already committed
    never rolls back.

    Args:
        target_location: Delta table URI.
        target: Fully-qualified UC name to stamp on each spec.
        version_before: Recorder-side Delta version pre-merge, or
            ``None`` when the audit hook didn't fire.
        version_after: Recorder-side Delta version post-merge, or
            ``None``.

    Returns:
        A list of
        :class:`~pointlessql.services.lineage_edges.ValueChangeSpec`
        entries, or ``None`` when capture was impossible / yielded
        nothing.
    """
    if version_before is None or version_after is None:
        return None
    if version_after <= version_before:
        return None

    # CDF is now bootstrapped before ``_do_upsert`` (see
    # ``merge_table``), so the merge commit always lands with CDF on
    # — no post-merge ALTER needed here.

    try:
        from pointlessql.services.value_change_capture import extract_value_changes

        dt = deltalake.DeltaTable(target_location)
        cdf_reader = dt.load_cdf(
            starting_version=version_before + 1,
            ending_version=version_after,
        )
        cdf_arrow = pa.table(cdf_reader.read_all())
    except Exception:  # noqa: BLE001 — best-effort
        logger.info(
            "value-change capture: load_cdf failed for %s",
            target_location,
            exc_info=True,
        )
        return None

    specs = extract_value_changes(cdf_table=cdf_arrow, target_table=target)
    return specs or None


def _detect_rejects(
    arrow_source: pa.Table, on: list[str]
) -> tuple[pa.Table, list[tuple[str, str, str | None]]]:
    """Identify pre-merge reject rows and return the cleaned source.

    opt-in via ``track_rejects=True``.  Only two
    reject reasons are detectable pre-merge without inspecting the
    target Delta state:

    * ``on_key_null`` — any row whose ``on`` columns contain NULL.
      The Delta-merge predicate evaluates NULL = NULL as false, so
      these rows always insert; usually this is unintended.
    * ``duplicate_in_source`` — rows that share the same ``on``
      values within the source.  A merge with such a source is
      undefined behaviour in deltalake — last-write-wins semantics
      depend on partitioning order.  We keep the first occurrence
      and reject the rest.

    Schema-mismatch and merge-predicate-excluded reasons need
    target-side context that the helper deliberately does not
    pull in here; callers that need them surface the rejects via
    ``pending_rejects`` with reason ``"other"`` from their own
    error-handling paths.

    Args:
        arrow_source: Source PyArrow Table.  When it has no
            ``_lineage_row_id`` column, no rejects can be tied to a
            source row, so the function returns the table unchanged
            with an empty rejects list.
        on: Merge-key column names.

    Returns:
        ``(cleaned_source, rejects)``.  ``cleaned_source`` has the
        rejected rows removed; the merge proceeds with this
        narrower table.  ``rejects`` is a list of
        ``(source_row_id, reason, detail)`` tuples in source order.
        Empty list when the source had no rejects.
    """
    if LINEAGE_ROW_ID_COLUMN not in arrow_source.schema.names:
        return arrow_source, []

    try:
        import pandas as pd
    except ImportError:  # pragma: no cover — pandas is a hard dep
        return arrow_source, []

    df: pd.DataFrame = arrow_source.to_pandas()
    rejects: list[tuple[str, str, str | None]] = []
    keep_mask = pd.Series([True] * len(df), index=df.index)

    null_key_mask = pd.Series([False] * len(df), index=df.index)
    for col in on:
        if col in df.columns:
            null_key_mask = null_key_mask | df[col].isna()

    for idx in df.index[null_key_mask]:
        row_id = df.at[idx, LINEAGE_ROW_ID_COLUMN]
        first_null = next(
            (col for col in on if col in df.columns and pd.isna(df.at[idx, col])),
            None,
        )
        rejects.append(
            (
                str(row_id) if row_id is not None else "",
                "on_key_null",
                f"NULL in on-key column {first_null!r}" if first_null else None,
            )
        )
    keep_mask = keep_mask & ~null_key_mask

    surviving = cast("pd.DataFrame", df[keep_mask])
    dup_mask = surviving.duplicated(subset=on, keep="first")
    for idx in surviving.index[dup_mask]:
        row_id = surviving.at[idx, LINEAGE_ROW_ID_COLUMN]
        key_repr = ", ".join(f"{c}={surviving.at[idx, c]!r}" for c in on if c in surviving.columns)
        rejects.append(
            (
                str(row_id) if row_id is not None else "",
                "duplicate_in_source",
                f"second occurrence of merge key ({key_repr})",
            )
        )

    final_mask = keep_mask.copy()
    final_mask.loc[surviving.index[dup_mask]] = False
    cleaned_df = df[final_mask].reset_index(drop=True)

    return pa.Table.from_pandas(cleaned_df, preserve_index=False), rejects


def _prepare_lineage(arrow_source: pa.Table, target: str) -> tuple[list[str], list[str], pa.Table]:
    """Extract source ``_lineage_row_id`` values and synthesise target IDs.

    When the source has a ``_lineage_row_id`` column the target gets
    a deterministic per-row ID written into the same column so the
    chain stays connected.  When the source has no such column the
    helper is a no-op — the target table simply doesn't gain a
    lineage column for the rows from this merge, and 's
    walk-back stops there with a "lineage break" marker.

    Args:
        arrow_source: PyArrow Table fed into the merge.
        target: Fully-qualified UC name of the merge target.

    Returns:
        ``(source_row_ids, target_row_ids, arrow_source_with_target_ids)``.
        Both lists are empty when the source doesn't carry a lineage
        column — caller skips edge emission.
    """
    if LINEAGE_ROW_ID_COLUMN not in arrow_source.schema.names:
        return [], [], arrow_source

    column = arrow_source.column(LINEAGE_ROW_ID_COLUMN)
    source_row_ids: list[str] = [
        v if isinstance(v, str) else ""
        for v in column.to_pylist()  # pyright: ignore[reportUnknownVariableType]
    ]
    target_row_ids = [synth_target_row_id(src, target) if src else "" for src in source_row_ids]
    target_array = pa.array(target_row_ids, type=pa.string())
    rebuilt = arrow_source.set_column(
        arrow_source.schema.get_field_index(LINEAGE_ROW_ID_COLUMN),
        LINEAGE_ROW_ID_COLUMN,
        target_array,
    )
    return source_row_ids, target_row_ids, rebuilt


def _merge_rows_affected(stats: dict[str, Any]) -> int | None:
    """Best-effort total row count from the deltalake merge stats.

    Args:
        stats: Return value from :func:`_do_upsert` or :func:`_do_scd2`.

    Returns:
        Sum of inserted + updated for upsert; appended + closed for
        SCD-2; ``None`` when the keys cannot be located.
    """
    try:
        if stats.get("strategy") == "upsert":
            inserted = int(stats.get("num_target_rows_inserted", 0) or 0)
            updated = int(stats.get("num_target_rows_updated", 0) or 0)
            return inserted + updated
        if stats.get("strategy") == "scd2":
            appended = int(stats.get("rows_appended", 0) or 0)
            closed = 0
            close_stats = stats.get("close_stats") or {}
            if isinstance(close_stats, dict):
                closed = int(close_stats.get("num_target_rows_updated", 0) or 0)
            return appended + closed
    except TypeError, ValueError:
        return None
    return None


def _stats_for_audit(stats: dict[str, Any]) -> dict[str, Any]:
    """Strip non-JSON-serialisable bits from the merge stats payload.

    Args:
        stats: Return value from :func:`_do_upsert` or :func:`_do_scd2`.

    Returns:
        A dict whose values are JSON-encodable (numbers, strings,
        nested dicts, lists).  Anything else gets stringified.
    """
    out: dict[str, Any] = {}
    for key, value in stats.items():
        if isinstance(value, (int, float, str, bool, type(None))):
            out[key] = value
        elif isinstance(value, dict):
            out[key] = _stats_for_audit(value)  # type: ignore[arg-type]
        elif isinstance(value, list):
            out[key] = [
                v if isinstance(v, (int, float, str, bool, type(None))) else str(v)
                for v in value  # pyright: ignore[reportUnknownVariableType]
            ]
        else:
            out[key] = str(value)
    return out


def _resolve_target_location(client: Client, full_name: str, unreachable_msg: str) -> str:
    """Look up *full_name* in soyuz-catalog and return its storage_location.

    Args:
        client: Configured catalog client.
        full_name: UC ``"catalog.schema.table"`` string.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        The Delta table's storage location URI.

    Raises:
        CatalogNotFoundError: Target is unknown or has no location.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    if not isinstance(response, TableInfo):
        raise CatalogNotFoundError(
            f"merge target {full_name!r} not found in soyuz-catalog "
            "(merge does not bootstrap tables — write or autoload first)"
        )
    location = response.storage_location
    if isinstance(location, Unset) or not location:
        raise CatalogNotFoundError(f"merge target {full_name!r} has no storage_location")
    return location


def _resolve_source_frame(client: Client, engine: Engine, source: Any, unreachable_msg: str) -> Any:
    """Return *source* as a frame, resolving UC references through the engine.

    Args:
        client: Configured catalog client (only used when *source* is a string).
        engine: Engine used to materialise UC references.
        source: Either a frame or a UC ``"catalog.schema.table"`` string.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        The source frame in the engine's native type.

    Raises:
        CatalogNotFoundError: When *source* is a UC reference that
            cannot be resolved.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """  # noqa: DOC502 — both errors propagate from read_table
    if isinstance(source, str):
        return read_table(
            client=client,
            engine=engine,
            full_name=source,
            unreachable_msg=unreachable_msg,
        )
    return source


def _frame_to_arrow(frame: Any) -> pa.Table:
    """Coerce a frame into a PyArrow Table for ``DeltaTable.merge``.

    Accepts pandas DataFrames (the default engine output) and any
    object that already exposes an Arrow conversion via
    ``to_arrow`` (Polars / DuckDB relations).  PyArrow Tables pass
    through unchanged.

    Args:
        frame: Source frame in the engine's native type.

    Returns:
        A PyArrow Table backing the merge source side.

    Raises:
        ValidationError: When the frame cannot be converted.
    """
    if isinstance(frame, pa.Table):
        return frame
    if hasattr(frame, "to_arrow"):
        return pa.Table.from_pandas(frame.to_arrow())  # type: ignore[no-any-return]
    try:
        return pa.Table.from_pandas(frame)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"merge source must be a pandas DataFrame, PyArrow Table, or "
            f"frame with .to_arrow(); got {type(frame).__name__}"
        ) from exc


def _do_upsert(target_location: str, arrow_source: pa.Table, on: list[str]) -> dict[str, Any]:
    """Run an upsert MERGE against the Delta table at *target_location*.

    Args:
        target_location: Delta table URI.
        arrow_source: Source rows as a PyArrow Table.
        on: Merge-key column names.

    Returns:
        ``{"strategy": "upsert", **deltalake_merge_stats}``.
    """
    dt = deltalake.DeltaTable(target_location)
    predicate = " AND ".join(f"target.{col} = source.{col}" for col in on)
    stats = (
        dt.merge(
            source=arrow_source,
            predicate=predicate,
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute()
    )
    return {"strategy": "upsert", **stats}


def _do_scd2(target_location: str, arrow_source: pa.Table, on: list[str]) -> dict[str, Any]:
    """Run an SCD-2 close-and-append against the Delta table.

    Two-phase: the merge step closes any currently-open target row
    that matches the source key (``_valid_to = now``,
    ``_is_current = false``).  An append step then writes every
    source row as a new current version with ``_valid_from = now``,
    ``_valid_to = null``, ``_is_current = true``.  See the module
    docstring for the no-change-detection caveat.

    Args:
        target_location: Delta table URI.
        arrow_source: Source rows as a PyArrow Table.
        on: Merge-key column names.

    Returns:
        ``{"strategy": "scd2", "rows_appended": int, "close_stats": {...}}``.
    """
    now = datetime.now(UTC)
    augmented = _augment_for_scd2(arrow_source, now)

    dt = deltalake.DeltaTable(target_location)
    predicate_close = (
        " AND ".join(f"target.{col} = source.{col}" for col in on)
        + f" AND target.{SCD2_IS_CURRENT} = TRUE"
    )
    close_iso = now.isoformat()
    close_stats = (
        dt.merge(
            source=augmented,
            predicate=predicate_close,
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update(
            updates={
                SCD2_VALID_TO: f"TIMESTAMP '{close_iso}'",
                SCD2_IS_CURRENT: "FALSE",
            }
        )
        .execute()
    )

    deltalake.write_deltalake(target_location, augmented, mode="append")
    return {
        "strategy": "scd2",
        "rows_appended": augmented.num_rows,
        "close_stats": close_stats,
    }


def _augment_for_scd2(arrow_source: pa.Table, now: datetime) -> pa.Table:
    """Add ``_valid_from`` / ``_valid_to`` / ``_is_current`` to *arrow_source*.

    Args:
        arrow_source: Source rows as a PyArrow Table.
        now: Wall-clock instant to stamp into ``_valid_from``.

    Returns:
        A new Arrow Table with the three SCD-2 columns appended at
        the end (key columns and existing fields are unchanged).
    """
    n = arrow_source.num_rows
    valid_from_col = pa.array([now] * n, type=pa.timestamp("us", tz="UTC"))
    valid_to_col = pa.array([None] * n, type=pa.timestamp("us", tz="UTC"))
    is_current_col = pa.array([True] * n, type=pa.bool_())
    augmented = arrow_source
    augmented = augmented.append_column(SCD2_VALID_FROM, valid_from_col)
    augmented = augmented.append_column(SCD2_VALID_TO, valid_to_col)
    augmented = augmented.append_column(SCD2_IS_CURRENT, is_current_col)
    return augmented
