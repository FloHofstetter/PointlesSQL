"""Compile a canvas, materialise the output port, and stamp lineage.

End-to-end orchestrator the Wave-B route layer hands a freshly-loaded
:class:`CanvasDoc`:

#. Compile the doc to a :class:`SQLFragment`.
#. Resolve the single ``OutputPort`` block to its target FQN + mode.
#. Look up each referenced base table's Delta storage location via
   soyuz.
#. Wrap the rest in :func:`operation_context` with ``op_name=
   canvas_materialize`` so the agent-run audit trail picks up one
   row + ``emit_lineage_after_commit`` fires for the multi-input
   case (the lineage branch the migration extended).
#. Register DuckDB views, run the ``WITH … SELECT …`` rendering,
   write the resulting Arrow table to the target Delta location, and
   create the UC table metadata if it didn't already exist.
#. Register / upsert the ``DataProductOutputPort`` row pointing at the
   freshly-materialised target.
#. Stamp the next graph version into ``data_product_canvas_graph``.

The executor talks to soyuz through the standard ``Client`` so callers
hand it the same instance used everywhere else (the FastAPI app stores
one on ``request.app.state.soyuz_client``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

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
    ExecuteResult,
    PinSchema,
)
from pointlessql.types import OpName, RunId

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


_CATALOG_UNREACHABLE_MSG = (
    "soyuz-catalog could not be reached while materialising a canvas "
    "data product.  Check that the catalog service is running and try "
    "again."
)


def _find_output_node(doc: CanvasDoc) -> dict[str, Any]:
    """Locate the single ``OutputPort`` node and return its config dict."""
    outputs = [n for n in doc.nodes if n.block_type == "OutputPort"]
    if len(outputs) != 1:
        msg = (
            "execute_canvas: canvas must contain exactly one OutputPort "
            f"block; found {len(outputs)}."
        )
        raise ValidationError(msg)
    return dict(outputs[0].config)


def _resolve_storage_location(client: Client, fqn: str) -> str:
    """Read the Delta storage location of *fqn* off soyuz UC.

    Raises:
        ValidationError: When the table is unknown to UC.
        CatalogUnavailableError: When soyuz is unreachable.
    """
    try:
        response = _get_table.sync(client=client, full_name=fqn)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(_CATALOG_UNREACHABLE_MSG) from exc
    except UnexpectedStatus as exc:
        if exc.status_code == 404:
            msg = f"InputPort references table {fqn!r} which is not registered in UC."
            raise ValidationError(msg) from exc
        raise
    if not isinstance(response, TableInfo):
        msg = f"InputPort references table {fqn!r} which is not registered in UC."
        raise ValidationError(msg)
    location = response.storage_location
    if isinstance(location, Unset) or not location:
        msg = f"Table {fqn!r} has no storage_location in UC; cannot register as a view."
        raise ValidationError(msg)
    return location


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
    try:
        existing = _get_table.sync(client=client, full_name=target_fqn)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(_CATALOG_UNREACHABLE_MSG) from exc
    except UnexpectedStatus as exc:
        if exc.status_code != 404:
            raise
        existing = None

    if isinstance(existing, TableInfo):
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
) -> ExecuteResult:
    """Compile, execute, materialise, register, and persist a canvas.

    Args:
        factory: SQLAlchemy session factory for PointlesSQL's own
            metadata DB.
        doc: The canvas document to execute.
        data_product_id: The product the canvas authors.
        soyuz_client: Configured ``soyuz_catalog_client.Client``.
        actor_user_id: The acting user (saved on the
            ``data_product_canvas_graph`` row + ``data_product_output_ports``
            row).
        upstream_schemas: Optional ``{input_port_node_id: PinSchema}``
            seeding for the compiler's schema flow.  The Wave-B
            route layer populates this from soyuz; tests pass it
            verbatim.
        agent_run_id: Optional run id to attach the audit row to.
            When ``None`` the executor falls back to
            :func:`current_agent_run_id` which reads the
            ``POINTLESSQL_AGENT_RUN_ID`` env var.  When neither is
            set the materialise still runs but no audit row /
            lineage event is emitted.

    Returns:
        An :class:`ExecuteResult` envelope.

    Raises:
        ValidationError: On compile failure or OutputPort misconfig
            (the error details carry the per-node
            :class:`CompileError` list).
        CatalogUnavailableError / CatalogNotFoundError: When soyuz
            refuses an UC lookup.
    """
    fragment, errors = compile_canvas(doc, upstream_schemas=upstream_schemas)
    if errors or fragment is None:
        summary = "; ".join(
            f"[{e.kind}] {e.node_id or '-'}.{e.pin or '-'}: {e.message}" for e in errors
        )
        raise ValidationError(f"Canvas failed to compile ({len(errors)} error(s)): {summary}")

    output_cfg = _find_output_node(doc)
    port_name = str(output_cfg.get("port_name") or "").strip()
    target_fqn = str(output_cfg.get("materialized_table") or "").strip()
    mode = str(output_cfg.get("mode") or "overwrite").lower()
    if not port_name or not target_fqn:
        msg = "OutputPort.port_name and OutputPort.materialized_table are required."
        raise ValidationError(msg)

    approved_tables: dict[str, str] = {}
    for fqn in fragment.referenced_tables:
        approved_tables[fqn] = _resolve_storage_location(soyuz_client, fqn)

    full_sql = render_sql(fragment)
    prepared = prepare_sql(full_sql)

    target_location, target_was_new = _register_target_if_new(
        client=soyuz_client,
        target_fqn=target_fqn,
    )

    from pointlessql.pql.context import current_agent_run_id

    effective_run_id = agent_run_id or current_agent_run_id()

    op_params: dict[str, Any] = {
        "data_product_id": data_product_id,
        "port_name": port_name,
        "mode": mode,
        "referenced_tables": list(fragment.referenced_tables),
    }

    rows_written = 0
    arrow_columns: list[tuple[str, str, str, bool]] = []

    with operation_context(
        factory if effective_run_id else None,
        agent_run_id=cast(RunId | None, effective_run_id),
        op_name=OpName.CANVAS_MATERIALIZE,
        params=op_params,
        target_table=target_fqn,
    ) as recorder:
        import deltalake
        import duckdb

        conn = duckdb.connect()
        try:
            for ref in prepared.refs:
                register_delta_view(conn, ref, approved_tables[ref])
            arrow_table = conn.execute(prepared.rewritten_sql).to_arrow_table()
        finally:
            conn.close()

        deltalake_mode: Any = "overwrite" if mode in {"overwrite", "merge"} else "append"
        deltalake.write_deltalake(target_location, arrow_table, mode=deltalake_mode)

        rows_written = arrow_table.num_rows
        arrow_columns = _arrow_columns_info(arrow_table)
        recorder.rows_affected = rows_written

    if target_was_new:
        _create_uc_table(
            client=soyuz_client,
            target_fqn=target_fqn,
            target_location=target_location,
            sample_arrow_columns=arrow_columns,
        )

    output_port_id = _ensure_output_port(
        factory,
        data_product_id=data_product_id,
        port_name=port_name,
        target_fqn=target_fqn,
        created_by_user_id=actor_user_id,
    )

    graph_version = save_graph(
        factory,
        data_product_id=data_product_id,
        doc=doc,
        author_user_id=actor_user_id,
    )

    return ExecuteResult(
        rows_written=rows_written,
        target_fqn=target_fqn,
        output_port_id=output_port_id,
        graph_version=graph_version,
        compile_errors=[],
    )


__all__ = ["execute_canvas"]
