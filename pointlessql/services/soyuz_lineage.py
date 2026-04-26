"""Best-effort emission of OpenLineage events to soyuz-catalog.

Phase 15 Sprint 15.1.  Every successful PQL primitive call inside an
agent run emits one ``OpenLineage`` ``RunEvent`` to soyuz so the
table-level lineage graph (``soyuz_catalog.lineage_runs`` +
``lineage_edges``, see soyuz Sprint 22 / ADR-0008) auto-populates.
The cross-reference lives in the ``runId`` field — soyuz strips
hyphens to derive ``LineageRun.id``, so a 36-char PointlesSQL
``agent_run_id`` becomes the 32-char soyuz primary key without any
extra mapping table.

This module is **best-effort**: a soyuz outage, a 5xx response, or a
network blip never blocks the underlying PQL write.  Failures are
returned to the caller (``operation_context`` in
:mod:`pointlessql.services.agent_runs.operations`) which stamps a
``[lineage_emit_failed]`` marker onto the just-inserted
``agent_run_operations`` row so the audit trail still records that
the side-effect was attempted.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Sequence

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


def emit_event_sync(
    *,
    run_id: str,
    op_name: str,
    inputs: Sequence[str],
    outputs: Sequence[str],
    event_type: str = "COMPLETE",
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
    body = OpenLineageEvent(
        event_time=datetime.datetime.now(datetime.UTC).isoformat(),
        event_type=event_type_enum,
        job=job,
        run=run,
        inputs=[OpenLineageDataset(name=fqn, namespace=_DATASET_NAMESPACE) for fqn in inputs],
        outputs=[OpenLineageDataset(name=fqn, namespace=_DATASET_NAMESPACE) for fqn in outputs],
    )

    try:
        client = make_soyuz_client(agent_run_id=run_id)
        _ingest.sync(client=client, body=body)
        return None
    except Exception as exc:  # noqa: BLE001 — best-effort, all failures returned to caller
        logger.info("soyuz lineage emit failed for run=%s op=%s: %s", run_id, op_name, exc)
        return exc
