"""OpenLineage 1.x inbound-event parser for the federation track.

Phase 40 Sprint 40.1: external producers POST OpenLineage RunEvents
to ``POST /api/lineage/openlineage`` and the route normalises them
into rows on the existing ``lineage_row_edges`` and
``lineage_column_map`` tables.  This module owns the mapping between
the OL envelope and the dialect-portable shadow-table dicts, in
isolation from the route handler so the parser can be unit-tested
without an HTTP fixture.

The parser is **forward-compatible**: unknown facets are silently
ignored, so an OL 2.x envelope with extra facets still feeds its
``columnLineage`` body through.  We only structurally parse:

* the ``run.runId`` (used as ``external_event_id`` for de-dupe),
* the ``job.namespace`` (used as ``producer``),
* every ``outputs[*].facets.columnLineage.fields[*].inputFields[*]``
  (turned into one row of ``lineage_column_map``),
* an optional custom ``pointlessql.lineage.row`` facet on outputs
  carrying ``inputFields`` with row IDs (turned into rows of
  ``lineage_row_edges``).

Workspace scoping is the **caller**'s responsibility — the route
hands the API-key's workspace_id into :func:`build_edge_dicts`
because external producers must not be able to cross-post lineage
into a workspace they don't own.
"""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Allowed transform_kind values on lineage_column_map rows.  Mirrors
# the CHECK constraint defined in
# :mod:`pointlessql.models.lineage`.
_VALID_TRANSFORM_KINDS = frozenset(
    {
        "identity",
        "rename",
        "derived",
        "aggregate",
        "unknown_origin",
        "sql_select",
        "sql_function",
        "sql_unknown",
    }
)


class _OpenLineageRun(BaseModel):
    """Minimal OL ``run`` shape — only ``runId`` is load-bearing."""

    model_config = ConfigDict(extra="allow")

    runId: str  # noqa: N815 — OL spec uses camelCase


class _OpenLineageJob(BaseModel):
    """Minimal OL ``job`` shape — namespace becomes the ``producer``."""

    model_config = ConfigDict(extra="allow")

    namespace: str
    name: str = ""


class _OpenLineageDataset(BaseModel):
    """OL input/output dataset reference + its facets."""

    model_config = ConfigDict(extra="allow")

    namespace: str = ""
    name: str
    facets: dict[str, Any] = Field(default_factory=dict)


class OpenLineageInboundEvent(BaseModel):
    """One OpenLineage 1.x ``RunEvent`` accepted on the inbound route.

    Tolerant of unknown fields (``extra="allow"``) so OL 2.x events
    with extra facets still parse.  Required fields are limited to
    what the parser needs to land an audit-relevant edge:
    ``eventTime`` (timestamp), ``run.runId`` (de-dupe key),
    ``job.namespace`` (producer label).
    """

    model_config = ConfigDict(extra="allow")

    eventTime: datetime.datetime  # noqa: N815 — OL spec uses camelCase
    run: _OpenLineageRun
    job: _OpenLineageJob
    inputs: list[_OpenLineageDataset] = Field(default_factory=list)
    outputs: list[_OpenLineageDataset] = Field(default_factory=list)


def _full_name(dataset: _OpenLineageDataset) -> str:
    """Render a dataset reference as a single-string identifier.

    The OL spec splits names into ``namespace`` + ``name``; downstream
    storage uses a flat ``VARCHAR(255)``.  When the namespace is
    ``unity`` (matching our outbound emitter convention) we drop it
    so federation-internal tables retain their three-part UC name;
    every other namespace prefixes for safety.
    """
    if not dataset.namespace or dataset.namespace == "unity":
        return dataset.name
    return f"{dataset.namespace}.{dataset.name}"


def _coerce_transform_kind(raw: Any) -> str:
    """Map an OL ``transformations[0].type`` string into our enum.

    Args:
        raw: The first transformation type pulled off an OL
            ``inputField``, or ``None`` when the producer omits the
            ``transformations`` array.

    Returns:
        A value from :data:`_VALID_TRANSFORM_KINDS`.  Unknown / missing
        values fall back to ``"unknown_origin"`` so the CHECK
        constraint never bounces a well-formed event.
    """
    if isinstance(raw, str) and raw in _VALID_TRANSFORM_KINDS:
        return raw
    return "unknown_origin"


def parse_to_column_maps(
    event: OpenLineageInboundEvent,
    *,
    workspace_id: int,
    created_at: datetime.datetime,
) -> list[dict[str, Any]]:
    """Extract ``lineage_column_map`` row dicts from one inbound event.

    Each entry under
    ``outputs[*].facets.columnLineage.fields.<col>.inputFields[*]``
    becomes one row.  Pure function so callers can unit-test
    deterministically.

    Args:
        event: Validated inbound event.
        workspace_id: Workspace the producer's API key pins to.  This
            value is stamped on every emitted row; the event body
            cannot override it.
        created_at: Wall-clock to record on every row.  The route
            uses ``datetime.now(UTC)`` so all rows from one POST
            share an insertion timestamp.

    Returns:
        Per-edge dicts ready to pass to a SQLAlchemy bulk insert.
        Empty when the event has no parseable column lineage.
    """
    rows: list[dict[str, Any]] = []
    producer = event.job.namespace
    external_event_id = event.run.runId
    for output in event.outputs:
        facet = output.facets.get("columnLineage")
        if not isinstance(facet, dict):
            continue
        fields = facet.get("fields")
        if not isinstance(fields, dict):
            continue
        target_table = _full_name(output)
        for target_column, body in fields.items():
            if not isinstance(target_column, str) or not target_column:
                continue
            if not isinstance(body, dict):
                continue
            input_fields = body.get("inputFields")
            if not isinstance(input_fields, list):
                continue
            for inp in input_fields:
                if not isinstance(inp, dict):
                    continue
                source_table_raw = inp.get("name")
                source_column_raw = inp.get("field")
                if not isinstance(source_table_raw, str) or not source_table_raw:
                    continue
                if not isinstance(source_column_raw, str) or not source_column_raw:
                    continue
                source_namespace = inp.get("namespace")
                if isinstance(source_namespace, str) and source_namespace and source_namespace != "unity":
                    source_table = f"{source_namespace}.{source_table_raw}"
                else:
                    source_table = source_table_raw
                transformations = inp.get("transformations")
                first_kind: Any = None
                if isinstance(transformations, list) and transformations:
                    head = transformations[0]
                    if isinstance(head, dict):
                        first_kind = head.get("type")
                rows.append(
                    {
                        "workspace_id": workspace_id,
                        "run_id": None,
                        "op_id": None,
                        "source_table": source_table,
                        "source_column": source_column_raw,
                        "target_table": target_table,
                        "target_column": target_column,
                        "transform_kind": _coerce_transform_kind(first_kind),
                        "transform_detail": None,
                        "producer": producer,
                        "external_event_id": external_event_id,
                        "created_at": created_at,
                    }
                )
    return rows


def parse_to_row_edges(
    event: OpenLineageInboundEvent,
    *,
    workspace_id: int,
    created_at: datetime.datetime,
) -> list[dict[str, Any]]:
    """Extract ``lineage_row_edges`` row dicts from one inbound event.

    Row-level lineage is **opt-in** for external producers: only
    events carrying a custom ``pointlessql.lineage.row`` facet on an
    output dataset (with ``inputFields[*]`` of shape
    ``{namespace, name, sourceRowId, targetRowId}``) emit row edges.
    Producers that only ship column-level lineage (the common case)
    return an empty list here.

    Args:
        event: Validated inbound event.
        workspace_id: Workspace the producer's API key pins to.
        created_at: Wall-clock for the inserted rows.

    Returns:
        Per-edge dicts.  Empty when no row-level facet is present.
    """
    rows: list[dict[str, Any]] = []
    producer = event.job.namespace
    external_event_id = event.run.runId
    for output in event.outputs:
        facet = output.facets.get("pointlessql.lineage.row")
        if not isinstance(facet, dict):
            continue
        input_fields = facet.get("inputFields")
        if not isinstance(input_fields, list):
            continue
        target_table = _full_name(output)
        for inp in input_fields:
            if not isinstance(inp, dict):
                continue
            source_table_raw = inp.get("name")
            source_row_id = inp.get("sourceRowId")
            target_row_id = inp.get("targetRowId")
            if not isinstance(source_table_raw, str) or not source_table_raw:
                continue
            if not isinstance(source_row_id, str) or not source_row_id:
                continue
            if not isinstance(target_row_id, str) or not target_row_id:
                continue
            source_namespace = inp.get("namespace")
            if isinstance(source_namespace, str) and source_namespace and source_namespace != "unity":
                source_table = f"{source_namespace}.{source_table_raw}"
            else:
                source_table = source_table_raw
            rows.append(
                {
                    "workspace_id": workspace_id,
                    "run_id": None,
                    "op_id": None,
                    "source_table": source_table,
                    "source_row_id": source_row_id,
                    "target_table": target_table,
                    "target_row_id": target_row_id,
                    "source_model_uri": None,
                    "producer": producer,
                    "external_event_id": external_event_id,
                    "created_at": created_at,
                }
            )
    return rows


__all__ = [
    "OpenLineageInboundEvent",
    "parse_to_column_maps",
    "parse_to_row_edges",
]
