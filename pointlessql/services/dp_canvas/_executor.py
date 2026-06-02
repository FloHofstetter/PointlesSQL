"""Compile a canvas, materialise its output ports, and stamp lineage.

End-to-end orchestrator the route layer hands a freshly-loaded
:class:`CanvasDoc`:

#. Compile the doc to a :class:`SQLFragment` carrying one sink per
   ``OutputPort`` block.
#. For *every* sink resolve its target FQN + mode and look up each
   referenced base table's Delta storage location via soyuz — all up
   front, so a misconfigured sink fails the whole run before any write.
#. Per sink, wrap the write in :func:`operation_context` with
   ``op_name=canvas_materialize`` (one audit row + lineage event per
   target table — clean per-table lineage for a fan-out canvas).
#. Register DuckDB views once, then per sink run the ``WITH … SELECT …``
   rendering, write the resulting Arrow table to that sink's target
   Delta location, create the UC table metadata if it didn't exist, and
   upsert the ``DataProductOutputPort`` row.
#. Stamp one next graph version into ``data_product_canvas_graph`` —
   all sinks of a run share it.

Materialisation is best-effort per sink: a runtime write failure on one
sink is recorded as that sink's ``status == "failed"`` and the remaining
sinks still run.  Compile / config / catalog-reachability errors instead
short-circuit the whole run before any write.

The executor talks to soyuz through the standard ``Client`` so callers
hand it the same instance used everywhere else (the FastAPI app stores
one on ``request.app.state.soyuz_client``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.schemas import (
    get_schema_api_2_1_unity_catalog_schemas_full_name_get as _get_schema,
)
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.models import DataProductOutputPort
from pointlessql.pql.engine import register_delta_view
from pointlessql.pql.sql_parser._prepare import prepare_sql
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.dp_canvas._compiler import compile_canvas, render_sql
from pointlessql.services.dp_canvas._storage import save_graph
from pointlessql.services.dp_canvas._types import (
    CanvasDoc,
    MultiExecuteResult,
    PinSchema,
    SinkResult,
    SinkSpec,
)
from pointlessql.services.dp_canvas._uc_lookup import (
    fetch_table_info,
    resolve_storage_location,
)
from pointlessql.types import OpName, RunId

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


logger = logging.getLogger(__name__)


_CATALOG_UNREACHABLE_MSG = (
    "soyuz-catalog could not be reached while materialising a canvas "
    "data product.  Check that the catalog service is running and try "
    "again."
)


def _derive_target_location(client: Client, catalog: str, schema: str, table: str) -> str:
    """Compute the new Delta path for a target table that does not yet exist."""
    schema_full = f"{catalog}.{schema}"
    try:
        response = _get_schema.sync(client=client, full_name=schema_full)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(_CATALOG_UNREACHABLE_MSG) from exc
    if not isinstance(response, SchemaInfo):
        msg = f"OutputPort target schema {schema_full!r} not found in UC."
        raise CatalogNotFoundError(msg)
    for field in (response.storage_location, response.storage_root):
        if not isinstance(field, Unset) and field:
            return f"{field.rstrip('/')}/{table}"
    msg = f"Schema {schema_full!r} has no storage_root; cannot derive target Delta path."
    raise CatalogNotFoundError(msg)


def _register_target_if_new(
    *,
    client: Client,
    target_fqn: str,
) -> tuple[str, bool]:
    """Resolve the target storage location and create the UC row if needed.

    Returns ``(location, was_created)``.  ``was_created`` lets the caller
    distinguish first-time materialise (where the UC ``_create_table``
    call needs to fire after the Delta write) from re-runs against an
    existing table.
    """
    existing = fetch_table_info(client, target_fqn)
    if existing is not None:
        loc = existing.storage_location
        if not isinstance(loc, Unset) and loc:
            return loc, False
    from pointlessql.pql._parsing import parse_full_name

    catalog, schema, table = parse_full_name(target_fqn)
    location = _derive_target_location(client, catalog, schema, table)
    return location, True


def _create_uc_table(
    *,
    client: Client,
    target_fqn: str,
    target_location: str,
    sample_arrow_columns: list[tuple[str, str, str, bool]],
) -> None:
    from pointlessql.pql._columns import columns_from_tuples
    from pointlessql.pql._parsing import parse_full_name

    catalog, schema, table = parse_full_name(target_fqn)
    body = CreateTable(
        catalog_name=catalog,
        schema_name=schema,
        name=table,
        table_type="MANAGED",
        data_source_format="DELTA",
        columns=columns_from_tuples(sample_arrow_columns),
        storage_location=target_location,
    )
    try:
        _create_table.sync(client=client, body=body)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(_CATALOG_UNREACHABLE_MSG) from exc


def _arrow_columns_info(arrow_table: Any) -> list[tuple[str, str, str, bool]]:
    """Translate an Arrow schema into the ``columns_from_tuples`` shape."""
    columns: list[tuple[str, str, str, bool]] = []
    for field in arrow_table.schema:
        type_text = str(field.type)
        # The type_name half of the soyuz column descriptor wants a short
        # token (``INT``, ``STRING``, ``DOUBLE``).  The full text already
        # carries dialect detail, so we coarse-bucket here and keep
        # ``type_text`` precise.
        type_name = _coarse_type(type_text)
        columns.append((field.name, type_name, type_text, field.nullable))
    return columns


def _coarse_type(text: str) -> str:
    text_lower = text.lower()
    if "int" in text_lower:
        return "INT"
    if "float" in text_lower or "double" in text_lower or "decimal" in text_lower:
        return "DOUBLE"
    if "bool" in text_lower:
        return "BOOLEAN"
    if "timestamp" in text_lower or "date" in text_lower:
        return "TIMESTAMP"
    if "binary" in text_lower:
        return "BINARY"
    return "STRING"


def _ensure_output_port(
    factory: sessionmaker[Session],
    *,
    data_product_id: int,
    port_name: str,
    target_fqn: str,
    created_by_user_id: int | None,
) -> int | None:
    """Upsert a ``DataProductOutputPort`` row idempotently.

    Returns the row id if a new port was created, ``None`` if an
    existing port with the same name was reused.  The 148.1 frontend
    blocks renaming the port through this surface — operators rename
    via the existing port-edit route.
    """
    from sqlalchemy import select

    from pointlessql.services.data_product_ports import create_output_port

    with factory() as session:
        existing = session.execute(
            select(DataProductOutputPort).where(
                DataProductOutputPort.data_product_id == data_product_id,
                DataProductOutputPort.name == port_name,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return None

    port = create_output_port(
        factory,
        data_product_id=data_product_id,
        name=port_name,
        kind="sql",
        location=target_fqn,
        created_by_user_id=created_by_user_id,
    )
    return port.id


def execute_canvas(
    factory: sessionmaker[Session],
    *,
    doc: CanvasDoc,
    data_product_id: int,
    soyuz_client: Client,
    actor_user_id: int | None = None,
    upstream_schemas: dict[str, PinSchema] | None = None,
    agent_run_id: str | None = None,
) -> MultiExecuteResult:
    """Compile, execute, materialise, register, and persist a canvas.

    Args:
        factory: SQLAlchemy session factory for PointlesSQL's own
            metadata DB.
        doc: The canvas document to execute.
        data_product_id: The product the canvas authors.
        soyuz_client: Configured ``soyuz_catalog_client.Client``.
        actor_user_id: The acting user (saved on the
            ``data_product_canvas_graph`` row + ``data_product_output_ports``
            rows).
        upstream_schemas: Optional ``{input_port_node_id: PinSchema}``
            seeding for the compiler's schema flow.  The route layer
            populates this from soyuz; tests pass it verbatim.
        agent_run_id: Optional run id to attach the audit rows to.
            When ``None`` the executor falls back to
            :func:`current_agent_run_id` which reads the
            ``POINTLESSQL_AGENT_RUN_ID`` env var.  When neither is
            set the materialise still runs but no audit row /
            lineage event is emitted.

    Returns:
        A :class:`MultiExecuteResult` envelope with one
        :class:`SinkResult` per ``OutputPort`` block.

    Raises:
        ValidationError: On compile failure or sink misconfig
            (the error details carry the per-node
            :class:`CompileError` list).
        CatalogUnavailableError / CatalogNotFoundError: When soyuz
            refuses an UC lookup while validating sinks up front.
    """
    fragment, errors = compile_canvas(doc, upstream_schemas=upstream_schemas)
    if errors or fragment is None:
        summary = "; ".join(
            f"[{e.kind}] {e.node_id or '-'}.{e.pin or '-'}: {e.message}" for e in errors
        )
        raise ValidationError(f"Canvas failed to compile ({len(errors)} error(s)): {summary}")

    # Resolve every base-table location and every sink's target up front.
    # Any failure here short-circuits the whole run *before* any write, so
    # a misconfigured sink can never leave a partially materialised canvas
    # behind.
    approved_tables: dict[str, str] = {}
    for fqn in fragment.referenced_tables:
        approved_tables[fqn] = resolve_storage_location(soyuz_client, fqn, required=True)

    prepared_sinks: list[_PreparedSink] = []
    for sink in fragment.sinks:
        if not sink.port_name or not sink.target_fqn:
            msg = "OutputPort.port_name and OutputPort.materialized_table are required."
            raise ValidationError(msg)
        target_location, target_was_new = _register_target_if_new(
            client=soyuz_client,
            target_fqn=sink.target_fqn,
        )
        prepared = prepare_sql(render_sql(fragment, sink))
        prepared_sinks.append(
            _PreparedSink(
                sink=sink,
                rewritten_sql=prepared.rewritten_sql,
                refs=list(prepared.refs),
                target_location=target_location,
                target_was_new=target_was_new,
            )
        )

    from pointlessql.pql.context import current_agent_run_id

    effective_run_id = agent_run_id or current_agent_run_id()

    # Register every referenced view once on a shared DuckDB connection,
    # then materialise each sink best-effort.
    import duckdb

    all_refs: list[str] = []
    seen_refs: set[str] = set()
    for ps in prepared_sinks:
        for ref in ps.refs:
            if ref not in seen_refs:
                seen_refs.add(ref)
                all_refs.append(ref)

    sink_results: list[SinkResult] = []
    conn = duckdb.connect()
    try:
        for ref in all_refs:
            try:
                register_delta_view(conn, ref, approved_tables[ref])
            except Exception as exc:
                # Every sink reads from the shared base tables, so a
                # source that resolves in the catalog but cannot be read
                # from storage (missing/removed Delta files, bad
                # location) is fatal to the whole run.  Surface it as a
                # clear error naming the table instead of an opaque 500.
                msg = (
                    f"source table {ref!r} could not be read from its storage "
                    f"location {approved_tables[ref]!r}: {exc}"
                )
                raise ValidationError(msg) from exc
        for ps in prepared_sinks:
            sink_results.append(
                _materialise_sink(
                    ps,
                    conn=conn,
                    factory=factory,
                    data_product_id=data_product_id,
                    soyuz_client=soyuz_client,
                    actor_user_id=actor_user_id,
                    effective_run_id=effective_run_id,
                    referenced_tables=list(fragment.referenced_tables),
                )
            )
    finally:
        conn.close()

    graph_version = save_graph(
        factory,
        data_product_id=data_product_id,
        doc=doc,
        author_user_id=actor_user_id,
    )

    return MultiExecuteResult(
        sinks=sink_results,
        graph_version=graph_version,
        compile_errors=[],
    )


class _PreparedSink:
    """A sink whose SQL is prepared and target location resolved up front."""

    __slots__ = ("sink", "rewritten_sql", "refs", "target_location", "target_was_new")

    def __init__(
        self,
        *,
        sink: SinkSpec,
        rewritten_sql: str,
        refs: list[str],
        target_location: str,
        target_was_new: bool,
    ) -> None:
        self.sink = sink
        self.rewritten_sql = rewritten_sql
        self.refs = refs
        self.target_location = target_location
        self.target_was_new = target_was_new


def _write_arrow_to_target(
    deltalake: Any,
    *,
    location: str,
    arrow_table: Any,
    mode: str,
    merge_on: list[str],
    target_is_new: bool,
) -> int:
    """Write *arrow_table* to the Delta *location* honouring *mode*.

    ``overwrite`` / ``append`` map straight to ``write_deltalake``.
    ``merge`` performs a Delta ``MERGE INTO`` on the ``merge_on`` keys
    (matched rows updated, unmatched inserted) — except on the very first
    materialise of a sink, when the target table does not exist yet: there
    merge degenerates to an insert-all, so we seed it with an
    ``overwrite`` create instead and upsert on subsequent runs.

    Returns the number of rows written / affected.
    """
    if mode == "merge" and not target_is_new:
        predicate = " AND ".join(f"t.{key} = s.{key}" for key in merge_on)
        table = deltalake.DeltaTable(location)
        metrics = (
            table.merge(
                source=arrow_table,
                predicate=predicate,
                source_alias="s",
                target_alias="t",
            )
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute()
        )
        inserted = int(metrics.get("num_target_rows_inserted", 0))
        updated = int(metrics.get("num_target_rows_updated", 0))
        return inserted + updated

    deltalake_mode = "append" if mode == "append" else "overwrite"
    deltalake.write_deltalake(location, arrow_table, mode=deltalake_mode)
    return int(arrow_table.num_rows)


def _materialise_sink(
    ps: _PreparedSink,
    *,
    conn: Any,
    factory: sessionmaker[Session],
    data_product_id: int,
    soyuz_client: Client,
    actor_user_id: int | None,
    effective_run_id: str | None,
    referenced_tables: list[str],
) -> SinkResult:
    """Write one sink to its target Delta table; never raises.

    A runtime failure (DuckDB exec, Delta write, UC registration) is
    captured into a ``status="failed"`` :class:`SinkResult` so the
    remaining sinks of the run still execute.
    """
    sink = ps.sink
    op_params: dict[str, Any] = {
        "data_product_id": data_product_id,
        "port_name": sink.port_name,
        "mode": sink.mode,
        "referenced_tables": referenced_tables,
    }
    try:
        import deltalake

        with operation_context(
            factory if effective_run_id else None,
            agent_run_id=cast(RunId | None, effective_run_id),
            op_name=OpName.CANVAS_MATERIALIZE,
            params=op_params,
            target_table=sink.target_fqn,
        ) as recorder:
            arrow_table = conn.execute(ps.rewritten_sql).to_arrow_table()
            rows_written = _write_arrow_to_target(
                deltalake,
                location=ps.target_location,
                arrow_table=arrow_table,
                mode=sink.mode,
                merge_on=sink.merge_on,
                target_is_new=ps.target_was_new,
            )
            recorder.rows_affected = rows_written
        arrow_columns = _arrow_columns_info(arrow_table)
        if ps.target_was_new:
            _create_uc_table(
                client=soyuz_client,
                target_fqn=sink.target_fqn,
                target_location=ps.target_location,
                sample_arrow_columns=arrow_columns,
            )
        output_port_id = _ensure_output_port(
            factory,
            data_product_id=data_product_id,
            port_name=sink.port_name,
            target_fqn=sink.target_fqn,
            created_by_user_id=actor_user_id,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort per sink
        logger.exception(
            "canvas sink %r → %r failed to materialise", sink.port_name, sink.target_fqn
        )
        return SinkResult(
            port_name=sink.port_name,
            target_fqn=sink.target_fqn,
            status="failed",
            error=str(exc),
        )
    return SinkResult(
        port_name=sink.port_name,
        target_fqn=sink.target_fqn,
        rows_written=rows_written,
        output_port_id=output_port_id,
        status="ok",
    )


__all__ = ["execute_canvas"]
