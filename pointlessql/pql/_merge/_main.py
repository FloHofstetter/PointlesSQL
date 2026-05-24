# pyright: reportPrivateUsage=false
"""``merge_table`` — the top-level orchestration of one Delta MERGE."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, cast

from soyuz_catalog_client import Client

from pointlessql.exceptions import ValidationError
from pointlessql.pql._hashing import arrow_ipc_sha256
from pointlessql.pql._merge._constants import MergeStrategy
from pointlessql.pql._merge._lineage import (
    _capture_value_changes,
    _detect_rejects,
    _prepare_lineage,
)
from pointlessql.pql._merge._resolve import (
    _frame_to_arrow,
    _resolve_source_frame,
    _resolve_target_location,
)
from pointlessql.pql._merge._stats import _merge_rows_affected, _stats_for_audit
from pointlessql.pql._merge._strategies import _do_scd2, _do_upsert
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql.engine import Engine
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.lineage_edges import ColumnEdgeSpec
from pointlessql.types import OpName, RunId

logger = logging.getLogger(__name__)


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
            columns to their *true* source-column names.  Populates ``derived`` rows in
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

        # data-product contract enforcement.  Same shape
        # as in ``pql/_write.py``: resolve the cached contract for the
        # target's schema, diff the arrow source's schema against the
        # table contract, and either stamp the recorder for the post-
        # commit event or raise a ``DataProductContractViolation``
        # *before* the merge runs so the bad write never lands.
        if agent_run_id is not None and factory is not None:
            from pointlessql.data_products import check_contract_for_write

            target_catalog, target_schema, target_table = parse_full_name(target)
            arrow_columns: list[tuple[str, str, str, bool]] = []
            for field in arrow_source.schema:
                ftype = str(field.type)
                arrow_columns.append((field.name, ftype.upper(), ftype, field.nullable))
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
                from pointlessql.services.lineage.column_diff import infer_column_edges

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
