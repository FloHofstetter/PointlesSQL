"""The declarative-pipeline refresh engine (synchronous).

One run walks the datasets in dependency order:

* **materialized_view** — recompute the SELECT in full and
  overwrite the target through the governed PQL write (lineage +
  audit ride along like every other write).
* **streaming_table** — read the single source's change feed from
  the per-dataset cursor, apply the SELECT to the change batch (the
  batch is materialised as a temporary Delta table and bound to the
  source's name, so the stored SQL runs verbatim), and append.
  First run = full backfill.

Expectations gate every computed batch before the write: ``warn``
records violations, ``drop`` removes violating rows, ``fail``
aborts the run.  Everything here is synchronous — routes dispatch
through ``run_sync``, the scheduler through a thread.
"""

from __future__ import annotations

import datetime
import json
import logging
import tempfile
from typing import TYPE_CHECKING, Any

import deltalake
import pandas as pd
from sqlalchemy import select

from pointlessql.models.pipelines import Pipeline, PipelineCursor, PipelineRun
from pointlessql.pql import PQL, PandasEngine, prepare_sql, register_delta_view
from pointlessql.services.pipelines._crud import (
    PipelineValidationError,
    parse_datasets,
    topological_order,
)
from pointlessql.services.unitycatalog import _get_table

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_CDF_META_COLUMNS = ("_change_type", "_commit_version", "_commit_timestamp")


class PipelineExpectationError(RuntimeError):
    """Raised when a ``fail``-action expectation finds violations."""


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _get_table_storage(client: Any, fqn: str) -> str:
    """Resolve a table's storage location through the catalog.

    Module-level seam so tests can map FQNs onto temp paths.

    Args:
        client: A sync-capable soyuz client.
        fqn: Three-part table name.

    Returns:
        The storage location.

    Raises:
        PipelineValidationError: When the table is unknown or
            carries no storage location.
    """
    info = _get_table.sync(full_name=fqn, client=client)
    storage = getattr(info, "storage_location", None)
    if not isinstance(storage, str) or not storage:
        raise PipelineValidationError(f"table {fqn!r} has no storage_location on the catalog")
    return storage


def _execute_select_to_pandas(
    sql: str,
    *,
    approved: dict[str, str],
    policies: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Run one SELECT and return the full result as pandas.

    Mirrors the export path (arrow, no JSON flattening, no row cap)
    rather than :func:`run_sql` — a materialized view legitimately
    recomputes millions of rows.

    Args:
        sql: The dataset's stored SELECT.
        approved: ``fqn → storage`` for every ref.
        policies: Optional per-table read policies.

    Returns:
        The result frame.
    """
    import duckdb

    prepared = prepare_sql(sql)
    conn = duckdb.connect()
    try:
        for ref in prepared.refs:
            register_delta_view(conn, ref, approved[ref], policy=(policies or {}).get(ref))
        return conn.execute(prepared.rewritten_sql).to_arrow_table().to_pandas()
    finally:
        conn.close()


def _apply_expectations(
    frame: pd.DataFrame, expectations: list[dict[str, str]], *, dataset: str
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Evaluate a dataset's expectations against a computed batch.

    Args:
        frame: The batch about to be written.
        expectations: ``{"name", "constraint", "action"}`` entries.
        dataset: Target FQN (for error messages).

    Returns:
        ``(surviving frame, metrics)`` where metrics carries one
        entry per expectation with its violation count.

    Raises:
        PipelineExpectationError: When a ``fail`` expectation has
            violations.
    """
    if not expectations:
        return frame, []
    import duckdb

    metrics: list[dict[str, Any]] = []
    current = frame
    conn = duckdb.connect()
    try:
        for expectation in expectations:
            constraint = expectation["constraint"]
            conn.register("__batch", current)
            violations = conn.execute(
                f"SELECT count(*) FROM __batch WHERE NOT coalesce(({constraint}), FALSE)"
            ).fetchone()
            count = int(violations[0]) if violations else 0
            action = expectation["action"]
            metrics.append({"name": expectation["name"], "violations": count, "action": action})
            if count == 0:
                conn.unregister("__batch")
                continue
            if action == "fail":
                raise PipelineExpectationError(
                    f"{dataset}: expectation {expectation['name']!r} failed for {count} rows"
                )
            if action == "drop":
                current = conn.execute(
                    f"SELECT * FROM __batch WHERE coalesce(({constraint}), FALSE)"
                ).fetch_df()
            conn.unregister("__batch")
    finally:
        conn.close()
    return current, metrics


def _cursor_value(
    factory: sessionmaker[Session], *, pipeline_id: int, dataset: str, source: str
) -> int | None:
    """Return the stored CDF cursor, or ``None`` before the backfill."""
    with factory() as session:
        row = session.scalar(
            select(PipelineCursor).where(
                PipelineCursor.pipeline_id == pipeline_id,
                PipelineCursor.dataset_name == dataset,
                PipelineCursor.source_fqn == source,
            )
        )
        return row.last_version if row is not None else None


def _advance_cursor(
    factory: sessionmaker[Session],
    *,
    pipeline_id: int,
    dataset: str,
    source: str,
    version: int,
) -> None:
    """Persist the new CDF cursor for ``(dataset, source)``."""
    with factory() as session:
        row = session.scalar(
            select(PipelineCursor).where(
                PipelineCursor.pipeline_id == pipeline_id,
                PipelineCursor.dataset_name == dataset,
                PipelineCursor.source_fqn == source,
            )
        )
        if row is None:
            row = PipelineCursor(
                pipeline_id=pipeline_id,
                dataset_name=dataset,
                source_fqn=source,
                last_version=version,
                updated_at=_utcnow(),
            )
            session.add(row)
        else:
            row.last_version = version
            row.updated_at = _utcnow()
        session.commit()


def _changes_since(storage: str, *, after_version: int) -> tuple[pd.DataFrame, int]:
    """Read the source's change feed after *after_version*.

    Args:
        storage: The source table's storage location.
        after_version: Last already-applied Delta version.

    Returns:
        ``(rows, current_version)`` — inserted/post-update rows with
        the CDF metadata columns dropped; empty when nothing new.

    Raises:
        PipelineValidationError: When the table has no change feed
            (``delta.enableChangeDataFeed`` unset).
    """
    table = deltalake.DeltaTable(storage)
    current = table.version()
    if current <= after_version:
        return pd.DataFrame(), current
    try:
        import pyarrow as pa

        # load_cdf hands back an arro3 stream; pyarrow adopts it via
        # the Arrow C stream interface.
        batch = pa.table(table.load_cdf(starting_version=after_version + 1)).to_pandas()
    except Exception as exc:  # noqa: BLE001 — deltalake raises plain exceptions here
        raise PipelineValidationError(
            f"change feed unavailable ({exc}) — enable "
            "delta.enableChangeDataFeed on the source or use a materialized view"
        ) from exc
    if batch.empty:
        return pd.DataFrame(), current
    kept = batch[batch["_change_type"].isin(["insert", "update_postimage"])]
    kept = kept.drop(columns=[c for c in _CDF_META_COLUMNS if c in kept.columns])
    return kept.reset_index(drop=True), current


def run_pipeline_sync(
    factory: sessionmaker[Session],
    *,
    pipeline_id: int,
    triggered_by: str | None,
    external: dict[str, str],
    external_policies: dict[str, Any],
    client: Any,
) -> int:
    """Execute one pipeline run and return its ``PipelineRun.id``.

    The caller (route or scheduler wrapper) has already enforced
    SELECT on every external reference and collected the caller's
    read policies; targets are written through PQL with the given
    principal-bound client, so creation, lineage, and audit follow
    the normal write path.

    Args:
        factory: SQLAlchemy session factory.
        pipeline_id: The pipeline to run.
        triggered_by: Principal recorded on the run row.
        external: ``fqn → storage`` for every external reference.
        external_policies: ``fqn → policy`` for governed externals.
        client: Sync-capable principal-bound soyuz client.

    Returns:
        The run row's primary key (status reflects the outcome).

    Raises:
        PipelineValidationError: When the pipeline row itself is
            missing — every error after the run row exists lands on
            that row instead of raising.
    """
    with factory() as session:
        pipeline = session.get(Pipeline, pipeline_id)
        if pipeline is None:
            raise PipelineValidationError(f"pipeline id={pipeline_id} not found")
        session.expunge(pipeline)

    run = PipelineRun(
        pipeline_id=pipeline_id,
        status="running",
        triggered_by=triggered_by,
        started_at=_utcnow(),
    )
    with factory() as session:
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    metrics: list[dict[str, Any]] = []
    try:
        datasets = topological_order(parse_datasets(pipeline))
        dataset_names = {d["name"] for d in datasets}
        internal_storage: dict[str, str] = {}
        pql = PQL(client=client, engine=PandasEngine())

        for dataset in datasets:
            name = dataset["name"]
            entry: dict[str, Any] = {
                "dataset": name,
                "kind": dataset["kind"],
                "rows_written": 0,
                "skipped": False,
                "expectations": [],
            }
            approved: dict[str, str] = {}
            for ref in dataset["refs"]:
                if ref in dataset_names:
                    if ref not in internal_storage:
                        internal_storage[ref] = _get_table_storage(client, ref)
                    approved[ref] = internal_storage[ref]
                elif ref in external:
                    approved[ref] = external[ref]
                else:
                    raise PipelineValidationError(f"{name}: unresolved reference {ref!r}")

            single_source = dataset["refs"][0] if len(dataset["refs"]) == 1 else None

            if dataset["kind"] == "materialized_view":
                frame = _execute_select_to_pandas(
                    dataset["sql"], approved=approved, policies=external_policies
                )
                frame, entry["expectations"] = _apply_expectations(
                    frame, dataset["expectations"], dataset=name
                )
                pql.write_table(frame, name, mode="overwrite", source_table_fqn=single_source)
                entry["rows_written"] = int(len(frame))
            else:  # streaming_table — exactly one source, enforced at validation
                source = dataset["refs"][0]
                cursor = _cursor_value(
                    factory, pipeline_id=pipeline_id, dataset=name, source=source
                )
                if cursor is None:
                    frame = _execute_select_to_pandas(
                        dataset["sql"], approved=approved, policies=external_policies
                    )
                    version = deltalake.DeltaTable(approved[source]).version()
                    write_mode = "overwrite"
                else:
                    changes, version = _changes_since(approved[source], after_version=cursor)
                    if changes.empty:
                        entry["skipped"] = True
                        metrics.append(entry)
                        _advance_cursor(
                            factory,
                            pipeline_id=pipeline_id,
                            dataset=name,
                            source=source,
                            version=version,
                        )
                        continue
                    with tempfile.TemporaryDirectory() as tmp:
                        batch_path = f"{tmp}/batch"
                        deltalake.write_deltalake(batch_path, changes)
                        frame = _execute_select_to_pandas(
                            dataset["sql"],
                            approved={**approved, source: batch_path},
                            policies=external_policies,
                        )
                    write_mode = "append"
                frame, entry["expectations"] = _apply_expectations(
                    frame, dataset["expectations"], dataset=name
                )
                pql.write_table(frame, name, mode=write_mode, source_table_fqn=source)
                entry["rows_written"] = int(len(frame))
                _advance_cursor(
                    factory,
                    pipeline_id=pipeline_id,
                    dataset=name,
                    source=source,
                    version=version,
                )

            if name not in internal_storage:
                internal_storage[name] = _get_table_storage(client, name)
            metrics.append(entry)

        _finish_run(factory, run_id, status="ok", metrics=metrics, error=None)
    except Exception as exc:  # noqa: BLE001 — every failure lands on the run row
        logger.exception("pipeline %s run %s failed", pipeline_id, run_id)
        _finish_run(factory, run_id, status="failed", metrics=metrics, error=str(exc))
    return run_id


def _finish_run(
    factory: sessionmaker[Session],
    run_id: int,
    *,
    status: str,
    metrics: list[dict[str, Any]],
    error: str | None,
) -> None:
    """Persist a run's terminal state."""
    with factory() as session:
        row = session.get(PipelineRun, run_id)
        if row is None:
            return
        row.status = status
        row.metrics = json.dumps(metrics)
        row.error = error
        row.finished_at = _utcnow()
        session.commit()
