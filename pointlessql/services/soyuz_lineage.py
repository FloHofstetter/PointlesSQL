"""Best-effort emission of OpenLineage events to soyuz-catalog.

Every successful PQL primitive call inside an agent run emits one
``OpenLineage`` ``RunEvent`` to soyuz so the table-level lineage
graph (``soyuz_catalog.lineage_runs`` + ``lineage_edges``)
auto-populates.  The cross-reference lives in the ``runId`` field
— soyuz strips hyphens to derive ``LineageRun.id``, so a 36-char
PointlesSQL ``agent_run_id`` becomes the 32-char soyuz primary key
without any extra mapping table.

Emission also carries two optional output facets:

* ``columnLineage`` — OpenLineage 1.x standard.  Built from the
   ``LineageColumnMap`` rows for the same op.
* ``valueChange`` — PointlesSQL custom facet (non-spec, namespaced
  by ``_producer``).  Built from the  ``LineageValueChange``
  rows for the same op.  PointlesSQL emits already-redacted values
  (per ``settings.audit.pii_mode``) so cleartext PII never leaves
  the install.

This module is **best-effort**: a soyuz outage, a 5xx response, or a
network blip never blocks the underlying PQL write.  Failures are
returned to the caller (``operation_context`` in
:mod:`pointlessql.services.agent_runs.operations`) which stamps a
``[lineage_emit_failed]`` marker into the just-inserted
``agent_run_operations.warnings_json`` blob so the audit trail
still records that the side-effect was attempted (these markers
are kept out of ``error_message``).
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Sequence
from typing import Any

from soyuz_catalog_client.api.lineage import (
    ingest_lineage_event_lineage_v1_events_post as _ingest,
)
from soyuz_catalog_client.models.open_lineage_dataset import OpenLineageDataset
from soyuz_catalog_client.models.open_lineage_event import OpenLineageEvent
from soyuz_catalog_client.models.open_lineage_event_eventtype import (
    OpenLineageEventEventtype,
)
from soyuz_catalog_client.models.open_lineage_job import OpenLineageJob
from soyuz_catalog_client.models.open_lineage_run import OpenLineageRun

from pointlessql.services.soyuz_client import make_soyuz_client

logger = logging.getLogger(__name__)

_JOB_NAMESPACE = "pointlessql"
_DATASET_NAMESPACE = "unity"
_VALUE_CHANGE_PRODUCER = "https://github.com/FloHofstetter/pointlessql"
_VALUE_CHANGE_SCHEMA = "https://pointlessql.dev/schemas/openlineage/valueChange.json"


def _build_column_lineage_facet(
    column_edges: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build the OpenLineage 1.x ``columnLineage`` facet body.

    Args:
        column_edges: Per-column-edge dicts with keys
            ``source_table``, ``source_column``, ``target_column``,
            ``transform_kind``.

    Returns:
        The facet body as a JSON-serialisable dict, or ``None`` when
        ``column_edges`` is empty.
    """
    if not column_edges:
        return None
    fields: dict[str, dict[str, Any]] = {}
    for edge in column_edges:
        target_column = edge.get("target_column")
        source_table = edge.get("source_table")
        source_column = edge.get("source_column")
        if not isinstance(target_column, str) or not source_column or not source_table:
            continue
        input_field: dict[str, Any] = {
            "namespace": _DATASET_NAMESPACE,
            "name": source_table,
            "field": source_column,
        }
        transform_kind = edge.get("transform_kind")
        if isinstance(transform_kind, str) and transform_kind:
            input_field["transformations"] = [{"type": transform_kind}]
        fields.setdefault(target_column, {"inputFields": []})["inputFields"].append(input_field)
    if not fields:
        return None
    return {"fields": fields}


def _build_value_change_facet(
    value_changes: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build the PointlesSQL custom ``valueChange`` facet body.

    Args:
        value_changes: Per-cell-change dicts with keys ``row_id``,
            ``column``, ``old_value``, ``new_value``.  Values are
            already redacted/hashed per ``settings.audit.pii_mode``
            — this builder does not re-mask.

    Returns:
        The facet body, or ``None`` when ``value_changes`` is empty.
    """
    if not value_changes:
        return None
    changes: list[dict[str, Any]] = []
    for change in value_changes:
        row_id = change.get("row_id")
        column = change.get("column")
        if not isinstance(row_id, str) or not isinstance(column, str):
            continue
        changes.append(
            {
                "rowId": row_id,
                "column": column,
                "oldValue": change.get("old_value"),
                "newValue": change.get("new_value"),
            }
        )
    if not changes:
        return None
    return {
        "_producer": _VALUE_CHANGE_PRODUCER,
        "_schemaURL": _VALUE_CHANGE_SCHEMA,
        "changes": changes,
    }


def emit_event_sync(
    *,
    run_id: str,
    op_name: str,
    inputs: Sequence[str],
    outputs: Sequence[str],
    event_type: str = "COMPLETE",
    column_edges: Sequence[dict[str, Any]] | None = None,
    value_changes: Sequence[dict[str, Any]] | None = None,
) -> Exception | None:
    """Post one ``OpenLineage`` ``RunEvent`` to soyuz, swallowing failures.

    Args:
        run_id: PointlesSQL ``agent_run_id`` (UUID with hyphens).  Used
            verbatim as the OpenLineage ``runId``; soyuz strips the
            hyphens internally so the resulting ``LineageRun.id`` is
            stable across both repos.
        op_name: PQL primitive name (``autoload`` / ``merge`` /
            ``write_table`` / ``sql``).  Becomes the OpenLineage
            ``job.name`` and each emitted edge's ``operation`` label.
        inputs: Fully-qualified UC table names that fed this
            operation.  Empty for ``autoload`` (filesystem source) and
            for ``merge`` / ``write_table`` calls where the caller did
            not declare ``source_table_fqn``.
        outputs: Fully-qualified UC table names this operation wrote.
            Empty for read-only ``sql`` queries.
        event_type: One of ``START`` / ``RUNNING`` / ``COMPLETE`` /
            ``FAIL`` / ``ABORT`` / ``OTHER``.  Defaults to
            ``COMPLETE`` because PointlesSQL emits exactly one event
            per primitive (after the write commits successfully).
        column_edges: Optional sequence of per-column-edge dicts
            (``source_table``, ``source_column``, ``target_column``,
            ``transform_kind``).  Empty / ``None`` skips the
            ``columnLineage`` facet.
        value_changes: Optional sequence of per-cell-change dicts
            (``row_id``, ``column``, ``old_value``, ``new_value``).
            Values must already be redacted/hashed per
            ``settings.audit.pii_mode`` — this function does not
            re-mask.  Empty / ``None`` skips the ``valueChange``
            facet.

    Returns:
        ``None`` when the event was accepted (HTTP 201), a 4xx that
        soyuz silently consumed (e.g. 422 from an evolved facet), or
        the call was a no-op because both ``inputs`` and ``outputs``
        were empty.  An ``Exception`` instance when the underlying
        HTTP call failed — connection refused, 5xx, timeout — so the
        caller can record the marker on the audit row.
    """
    if not inputs and not outputs:
        return None

    try:
        event_type_enum = OpenLineageEventEventtype(event_type)
    except ValueError as exc:
        return exc

    job = OpenLineageJob(namespace=_JOB_NAMESPACE, name=op_name)
    run = OpenLineageRun(run_id=run_id)

    column_facet = _build_column_lineage_facet(column_edges or [])
    value_facet = _build_value_change_facet(value_changes or [])

    output_datasets: list[OpenLineageDataset] = []
    for fqn in outputs:
        ds = OpenLineageDataset(name=fqn, namespace=_DATASET_NAMESPACE)
        if column_facet is not None or value_facet is not None:
            facets: dict[str, Any] = {}
            if column_facet is not None:
                facets["columnLineage"] = column_facet
            if value_facet is not None:
                facets["valueChange"] = value_facet
            ds["facets"] = facets
        output_datasets.append(ds)

    body = OpenLineageEvent(
        event_time=datetime.datetime.now(datetime.UTC).isoformat(),
        event_type=event_type_enum,
        job=job,
        run=run,
        inputs=[OpenLineageDataset(name=fqn, namespace=_DATASET_NAMESPACE) for fqn in inputs],
        outputs=output_datasets,
    )

    try:
        client = make_soyuz_client(agent_run_id=run_id)
        _ingest.sync(client=client, body=body)
        return None
    except Exception as exc:  # noqa: BLE001 — best-effort, all failures returned to caller
        logger.info(
            "soyuz lineage emit failed",
            exc_info=exc,
            extra={"run_id": run_id, "op_name": op_name},
        )
        return exc
