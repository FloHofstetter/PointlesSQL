"""Helpers for :meth:`PQL.write_table`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.schemas import (
    get_schema_api_2_1_unity_catalog_schemas_full_name_get as _get_schema,
)
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.pql._columns import columns_from_tuples
from pointlessql.pql._hashing import arrow_ipc_sha256
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql.engine import Engine
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.lineage_edges import synth_target_row_id

LINEAGE_ROW_ID_COLUMN = "_lineage_row_id"


def write_table(
    *,
    client: Client,
    engine: Engine,
    df: Any,
    full_name: str,
    mode: Literal["error", "append", "overwrite", "ignore"],
    unreachable_msg: str,
    agent_run_id: str | None = None,
    source_table_fqn: str | None = None,
    source_model_uri: str | None = None,
    derivations: Mapping[str, Sequence[str]] | None = None,
) -> None:
    """Write a frame to a Delta table and register it in the catalog.

    Args:
        client: Configured ``soyuz_catalog_client.Client``.
        engine: Engine to write *df* with.
        df: The data to write, in the engine's native frame type.
        full_name: Three-part name ``"catalog.schema.table"``.
        mode: Write mode passed to the engine.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.
        agent_run_id: When set, the call emits one
            ``agent_run_operations`` row.  ``None`` keeps the
            interactive path silent.
        source_table_fqn: When set, declared as the upstream UC
            input on the OpenLineage event emitted to soyuz so the
            cross-table edge ``source_table_fqn → full_name`` appears
            in the lineage graph.  ``None`` keeps
            ``write_table`` generic for in-memory frames with no UC
            origin.
        source_model_uri: when set, declares the
            originating registered-model URI
            (``models:/cat.sch.model/<version>``) so every
            ``lineage_row_edges`` row produced by this write
            carries the model provenance, and the model-detail DAG
            can paint ``target_table`` as a downstream prediction
            node.  Requires ``source_table_fqn`` for the row-edge
            grain to be meaningful AND ``_lineage_row_id`` on *df*
            ( caveat) — without the column the row-edge
            hook short-circuits with no source IDs to correlate on,
            and the URI has nowhere to land.
        derivations: Optional declarative mapping of derived target
            columns to their *true* source-column names (Sprint
            15.6.2).  Effective only when ``source_table_fqn`` is
            also set (a derivation needs a source to point at).

    Raises:
        ValidationError: If *full_name* does not have exactly three parts.
        CatalogNotFoundError: If the parent schema has no storage root
            and the table does not already exist.
        CatalogUnavailableError: If soyuz-catalog is unreachable.
        AuditUnavailableError: If *agent_run_id* is set and the
            ``agent_run_operations`` row cannot be persisted.
    """  # noqa: DOC503
    catalog, schema, table = parse_full_name(full_name)

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    with operation_context(
        factory,
        agent_run_id=agent_run_id,
        op_name="write_table",
        params={"full_name": full_name, "mode": mode},
        target_table=full_name,
    ) as recorder:
        table_exists = False
        location: str | None = None

        try:
            response = _get_table.sync(client=client, full_name=full_name)
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

        if agent_run_id is not None and table_exists and location is not None:
            recorder.delta_version_before = safe_delta_version(location)
        if agent_run_id is not None:
            try:
                recorder.input_sha = arrow_ipc_sha256(df)
            except TypeError:
                recorder.input_sha = None
            recorder.rows_affected = _frame_row_count(df)
            if source_table_fqn:
                recorder.extra_params = {
                    **recorder.extra_params,
                    "source_table_fqn": source_table_fqn,
                }
                if source_model_uri:
                    recorder.extra_params = {
                        **recorder.extra_params,
                        "source_model_uri": source_model_uri,
                    }
                source_ids, target_ids, df = _stamp_lineage_for_write(df, full_name)
                if source_ids:
                    recorder.pending_lineage_edges = {
                        "source_table": source_table_fqn,
                        "source_row_ids": source_ids,
                        "target_row_ids": target_ids,
                        "source_model_uri": source_model_uri,
                    }

                column_names = _frame_column_names(df)
                if column_names:
                    from pointlessql.services.column_lineage_diff import infer_column_edges
                    from pointlessql.services.lineage_edges import ColumnEdgeSpec

                    edges = infer_column_edges(
                        source_columns=column_names,
                        target_columns=column_names,
                        source_table=source_table_fqn,
                        target_table=full_name,
                        derivations=derivations,
                    )
                    if LINEAGE_ROW_ID_COLUMN in column_names:
                        edges = [
                            e
                            for e in edges
                            if not (
                                e.target_column == LINEAGE_ROW_ID_COLUMN
                                and e.transform_kind == "identity"
                            )
                        ]
                        edges.append(
                            ColumnEdgeSpec(
                                source_table=source_table_fqn,
                                source_column=LINEAGE_ROW_ID_COLUMN,
                                target_table=full_name,
                                target_column=LINEAGE_ROW_ID_COLUMN,
                                transform_kind="derived",
                                transform_detail="synth_target_row_id",
                            )
                        )
                    if edges:
                        recorder.pending_column_edges = edges

        try:
            if not table_exists:
                location = derive_storage_location(client, catalog, schema, table)

            assert location is not None  # noqa: S101 — guarded above

            engine.write(df, location, mode)

            if not table_exists:
                from pointlessql.pql._cdf import ensure_cdf_enabled

                ensure_cdf_enabled(location)

            if agent_run_id is not None:
                recorder.delta_version_after = safe_delta_version(location)

            if not table_exists:
                columns = columns_from_tuples(engine.columns_info(df))
                body = CreateTable(
                    catalog_name=catalog,
                    schema_name=schema,
                    name=table,
                    table_type="MANAGED",
                    data_source_format="DELTA",
                    columns=columns,
                    storage_location=location,
                )
                _create_table.sync(client=client, body=body)
        except httpx.ConnectError as exc:
            raise CatalogUnavailableError(unreachable_msg) from exc


def _stamp_lineage_for_write(df: Any, target_full_name: str) -> tuple[list[str], list[str], Any]:
    """Replace ``_lineage_row_id`` on *df* with synthesised target IDs.

    Mirrors :func:`pointlessql.pql._merge._prepare_lineage` but works
    on whatever frame shape the engine accepts (pandas /
    PyArrow / Polars).  When the column is absent or the frame can't
    be inspected the helper returns empty lists so the audit-row hook
    skips edge emission cleanly.

    Args:
        df: Frame the caller passed to :func:`write_table`.
        target_full_name: Fully-qualified UC name being written to.

    Returns:
        ``(source_row_ids, target_row_ids, df_with_target_ids)``.
        Empty ID lists when the lineage column wasn't present or
        couldn't be rewritten — caller skips edge persistence.
    """
    column = LINEAGE_ROW_ID_COLUMN
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover — pandas is a hard dep
        return [], [], df

    if isinstance(df, pd.DataFrame):
        if column not in df.columns:
            return [], [], df
        source_ids = [str(v) for v in df[column].tolist()]
        target_ids = [synth_target_row_id(s, target_full_name) for s in source_ids]
        df = df.copy()
        df[column] = target_ids
        return source_ids, target_ids, df

    try:
        import pyarrow as pa
    except ImportError:  # pragma: no cover — pyarrow is a hard dep
        return [], [], df

    if isinstance(df, pa.Table):
        if column not in df.schema.names:
            return [], [], df
        source_ids = [str(v) if v is not None else "" for v in df.column(column).to_pylist()]
        target_ids = [synth_target_row_id(s, target_full_name) for s in source_ids]
        rebuilt = df.set_column(
            df.schema.get_field_index(column),
            column,
            pa.array(target_ids, type=pa.string()),
        )
        return source_ids, target_ids, rebuilt

    return [], [], df


def safe_delta_version(location: str) -> int | None:
    """Read ``DeltaTable.version()`` without raising into the audit path.

    Used by operation rows to capture pre/post versions.  A read
    failure (table missing, corrupt log) is logged-and-skipped so
    a cosmetic Delta-side hiccup cannot block the underlying
    write — the write is the audit-relevant action.

    Args:
        location: Delta-table storage URI.

    Returns:
        The version integer, or ``None`` when reading failed.
    """
    try:
        import deltalake

        return int(deltalake.DeltaTable(location).version())
    except Exception:  # noqa: BLE001 — version reads are best-effort
        # bare-broad-ok: version probe returns None on Delta absent / corrupt
        return None


def _frame_column_names(frame: Any) -> list[str]:
    """Best-effort column-name extraction for the engine's native frame types.

    Args:
        frame: Source frame.

    Returns:
        List of column names, or an empty list when the frame shape
        is unrecognised.
    """
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover — pandas is a hard dep
        pd = None  # type: ignore[assignment]
    if pd is not None and isinstance(frame, pd.DataFrame):
        return [str(c) for c in frame.columns]
    try:
        import pyarrow as pa
    except ImportError:  # pragma: no cover — pyarrow is a hard dep
        pa = None  # type: ignore[assignment]
    if pa is not None and isinstance(frame, pa.Table):
        return list(frame.schema.names)
    if hasattr(frame, "columns"):
        try:
            return [str(c) for c in frame.columns]
        except TypeError, ValueError:
            return []
    return []


def _frame_row_count(frame: Any) -> int | None:
    """Best-effort row count for the engine's native frame types.

    Args:
        frame: Source frame.

    Returns:
        Number of rows or ``None`` when unavailable.
    """
    try:
        if hasattr(frame, "num_rows"):
            return int(frame.num_rows)  # type: ignore[arg-type]
        if hasattr(frame, "shape"):
            return int(frame.shape[0])  # type: ignore[arg-type]
        if hasattr(frame, "count") and callable(frame.count):
            return int(frame.count())  # type: ignore[arg-type]
        return len(frame)
    except TypeError, ValueError, AttributeError:
        return None


def derive_storage_location(client: Client, catalog: str, schema: str, table: str) -> str:
    """Compute a storage location for a new table from its parent schema.

    Args:
        client: Configured catalog client.
        catalog: Catalog name.
        schema: Schema name.
        table: Table name.

    Returns:
        The derived storage location path.

    Raises:
        CatalogNotFoundError: If the parent schema has no
            ``storage_location`` or ``storage_root``.
    """
    schema_full = f"{catalog}.{schema}"
    response = _get_schema.sync(client=client, full_name=schema_full)
    if not isinstance(response, SchemaInfo):
        msg = f"Schema not found: {schema_full!r}"
        raise CatalogNotFoundError(msg)

    for field in (response.storage_location, response.storage_root):
        if not isinstance(field, Unset) and field:
            return f"{field.rstrip('/')}/{table}"

    msg = (
        f"Schema {schema_full!r} has no storage_location or storage_root. "
        f"Set a storage_root on the schema before writing new tables."
    )
    raise CatalogNotFoundError(msg)
