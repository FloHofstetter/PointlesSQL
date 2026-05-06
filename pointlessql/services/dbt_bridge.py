"""Bridge dbt artefacts → PointlesSQL audit / lineage rows.

After a ``dbt run`` / ``dbt test`` finishes, dbt writes two files
under ``target/``:

- ``manifest.json`` — the full graph: models, sources, tests, refs,
  macros, with stable ``unique_id`` keys.
- ``run_results.json`` — per-node execution outcome: status,
  ``execution_time``, ``message``, threading info.

This module reads both files and emits one
:class:`pointlessql.models.AgentRunOperation` row per executed model
or test.  No engine state mutates here — the bridge is a pure
manifest → audit-row mapping.

Sprint 36.2 covers model + test execution rows.  Sprint 36.3 layers
``lineage_row_rejects`` for failing tests on top.  Sprint 36.5 layers
severity enforcement (``error`` → AgentRun ``failed``) and rollback
hooks on top.

All schema reads use ``.get(...)`` with explicit defaults so a future
dbt-version manifest-schema bump that adds new fields does not crash
the bridge — the only fields we *require* on a node are
``unique_id`` and ``resource_type``.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pointlessql.exceptions import AuditUnavailableError
from pointlessql.services.agent_runs.operations import record_operation
from pointlessql.services.lineage.rows import record_rejects

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

_logger = logging.getLogger(__name__)


@dataclass
class DBTNodeResult:
    """A single per-node entry from ``run_results.json``.

    Attributes:
        unique_id: dbt's stable identifier (``model.proj.bronze`` or
            ``test.proj.not_null_bronze_id``).
        resource_type: ``model`` / ``test`` / ``snapshot`` / ``seed``.
        relation_name: For materialised nodes, the qualified DB
            relation (``main.bronze.bronze``).  ``None`` for tests.
        status: dbt status string (``success`` / ``error`` / ``fail`` /
            ``warn`` / ``skipped`` / ``pass``).
        execution_time: Wall-clock seconds the node spent running.
        message: dbt's user-facing summary line (``"OK created table..."``)
            or the failure message.
        rows_affected: ``num_rows_affected`` from the result, or
            ``None`` when not applicable (tests, views).
        depends_on: List of ``unique_id`` strings the node refs / sources.
        materialization: Materialisation strategy from manifest config.
        severity: For tests, ``error`` (default) or ``warn`` — drives
            severity-mapping in 36.5.
    """

    unique_id: str
    resource_type: str
    relation_name: str | None
    status: str
    execution_time: float
    message: str | None
    rows_affected: int | None
    depends_on: list[str]
    materialization: str | None
    severity: str | None


@dataclass
class DBTRunSummary:
    """Aggregate outcome of a dbt invocation, suitable for HTTP responses.

    Attributes:
        agent_run_id: The PointlesSQL run id the operations land under.
        nodes: Per-node results.
        ok_count: Count of nodes with ``status='success'`` / ``'pass'``.
        fail_count: Count of nodes with ``status='error'`` / ``'fail'``.
        warn_count: Count of nodes with ``status='warn'``.
        skipped_count: Count of nodes that did not run.
    """

    agent_run_id: str
    nodes: list[DBTNodeResult]
    ok_count: int
    fail_count: int
    warn_count: int
    skipped_count: int


def parse_manifest(path: Path) -> dict[str, Any]:
    """Read ``target/manifest.json`` into a dict.

    The manifest is large (often megabytes) but we only ever look at
    ``nodes[unique_id]`` plus ``parent_map`` / ``child_map``, so we
    keep the parse cost minimal by not eagerly traversing.

    Args:
        path: Filesystem path to ``manifest.json``.

    Returns:
        Parsed JSON object.

    Raises:
        ValueError: If the file is not valid JSON.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json is not valid JSON: {exc}") from exc


def parse_run_results(path: Path) -> list[dict[str, Any]]:
    """Read ``target/run_results.json`` and return the ``results`` list.

    The file is only written when dbt reaches the post-execute phase,
    so a compile failure leaves the previous run's results intact.
    Callers should check the executor exit code before trusting an
    "old run_results.json" — Sprint 36.2 routes always pair
    executor results with a fresh exit code.

    Args:
        path: Filesystem path to ``run_results.json``.

    Returns:
        The list under the top-level ``results`` key.  Empty list
        when the key is absent (defensive against schema bumps).

    Raises:
        ValueError: If the file is not valid JSON.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"run_results.json is not valid JSON: {exc}") from exc
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        return []
    out: list[dict[str, Any]] = []
    for r in raw_results:
        if isinstance(r, dict):
            out.append(r)  # pyright: ignore[reportUnknownArgumentType]
    return out


def as_dict(value: Any) -> dict[str, Any]:
    """Narrow an ``Any``-typed manifest field to a typed dict.

    The dbt manifest is parsed as raw JSON so every nested lookup
    starts as ``Any``.  Channelling all ``isinstance``-based
    narrowing through this single helper keeps callers free of
    ``reportUnknownVariableType`` cascades.

    Args:
        value: Result of a ``manifest.get(...)`` call.

    Returns:
        The same dict when ``value`` is a dict, else an empty dict.
    """
    if isinstance(value, dict):
        return value  # type: ignore[reportUnknownVariableType]
    return {}


def as_list(value: Any) -> list[Any]:
    """Narrow an ``Any``-typed manifest field to a typed list.

    Args:
        value: Result of a ``manifest.get(...)`` call.

    Returns:
        The same list when ``value`` is a list, else an empty list.
    """
    if isinstance(value, list):
        return value  # type: ignore[reportUnknownVariableType]
    return []


def project_models(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Project the manifest's nodes table down to a model-only summary.

    Filters on ``resource_type='model'``, joins each model with the
    tests that reference it via the test node's ``depends_on``, and
    returns a stable JSON-shaped list.  Used by ``/api/dbt/manifest``
    + ``/api/dbt/coverage`` and reused by the plugin's
    ``pql_dbt_show_lineage`` tool, so we keep one canonical
    projection rather than two slightly different ones.

    Args:
        manifest: Parsed manifest dict.

    Returns:
        list[dict[str, Any]]: One entry per model, ordered by
            ``unique_id`` for deterministic output.
    """
    nodes = as_dict(manifest.get("nodes"))

    # Index tests by the model unique_ids they reference.  We walk
    # the test's own ``depends_on.nodes`` rather than ``parent_map``
    # because the latter is sometimes truncated in hand-written
    # fixtures while ``depends_on`` is part of every node's stable
    # schema.
    tests_by_model: dict[str, list[dict[str, Any]]] = {}
    for test_id, raw_node in nodes.items():
        node = as_dict(raw_node)
        if node.get("resource_type") != "test":
            continue
        config = as_dict(node.get("config"))
        severity = str(config.get("severity") or "error")
        test_meta = as_dict(node.get("test_metadata"))
        test_name = str(test_meta.get("name") or node.get("name") or "")
        column = str(node.get("column_name") or "") or None
        # Tests that ref multiple models get attached to every parent.
        for parent_id in as_list(as_dict(node.get("depends_on")).get("nodes")):
            if not isinstance(parent_id, str):
                continue
            tests_by_model.setdefault(parent_id, []).append(
                {
                    "unique_id": test_id,
                    "name": test_name,
                    "column": column,
                    "severity": severity,
                },
            )

    out: list[dict[str, Any]] = []
    for unique_id, raw_node in nodes.items():
        node = as_dict(raw_node)
        if node.get("resource_type") != "model":
            continue
        config = as_dict(node.get("config"))
        columns_dict = as_dict(node.get("columns"))
        column_names = sorted(str(c) for c in columns_dict.keys())
        depends_on = [str(d) for d in as_list(as_dict(node.get("depends_on")).get("nodes")) if d]
        out.append(
            {
                "unique_id": unique_id,
                "name": str(node.get("name") or ""),
                "schema": str(node.get("schema") or "") or None,
                "database": str(node.get("database") or "") or None,
                "relation_name": node.get("relation_name") or None,
                "materialization": str(config.get("materialized") or "") or None,
                "depends_on": depends_on,
                "columns": column_names,
                "tests": tests_by_model.get(unique_id, []),
            },
        )
    out.sort(key=lambda m: str(m["unique_id"]))
    return out


def _node_relation_name(node: dict[str, Any]) -> str | None:
    """Pull the qualified ``database.schema.alias`` from a node entry.

    dbt 1.7+ exposes ``relation_name`` directly; older versions
    require composing from ``database`` / ``schema`` / ``alias``.
    Both forms are handled — we fall through when neither is present
    (true for ephemeral tests).
    """
    rel = node.get("relation_name")
    if rel:
        return str(rel)
    db = node.get("database")
    schema = node.get("schema")
    alias = node.get("alias") or node.get("name")
    if db and schema and alias:
        return f"{db}.{schema}.{alias}"
    return None


def merge_manifest_and_results(
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
) -> list[DBTNodeResult]:
    """Combine manifest metadata with per-node run results.

    For each ``results`` entry we look up the matching ``unique_id`` in
    the manifest's ``nodes`` table and pull the relation name,
    materialisation strategy, dependency list, and severity (for
    tests) onto the result row.

    Args:
        manifest: Parsed manifest dict.
        results: List of result dicts (from ``parse_run_results``).

    Returns:
        One :class:`DBTNodeResult` per result entry.  Results whose
            ``unique_id`` is unknown to the manifest still produce a
            ``DBTNodeResult`` (with empty depends_on / no relation
            name) — defensive against partial-manifest scenarios.
    """
    empty: dict[str, Any] = {}
    nodes_raw = manifest.get("nodes") if isinstance(manifest.get("nodes"), dict) else empty
    nodes_by_id: dict[str, dict[str, Any]] = nodes_raw or empty  # pyright: ignore[reportAssignmentType]
    empty_list: list[Any] = []
    out: list[DBTNodeResult] = []
    for r in results:
        unique_id = str(r.get("unique_id") or "")
        if not unique_id:
            continue
        raw_node = nodes_by_id.get(unique_id) or empty
        node: dict[str, Any] = raw_node if isinstance(raw_node, dict) else empty
        raw_depends = node.get("depends_on")
        depends_obj: dict[str, Any] = raw_depends if isinstance(raw_depends, dict) else empty
        depends_raw = depends_obj.get("nodes")
        depends_on: list[Any] = depends_raw if isinstance(depends_raw, list) else empty_list
        raw_config = node.get("config")
        config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else empty
        raw_adapter = r.get("adapter_response")
        adapter: dict[str, Any] = raw_adapter if isinstance(raw_adapter, dict) else empty
        rows_aff = adapter.get("rows_affected")
        message_raw = r.get("message")
        materialized = config.get("materialized")
        severity_raw = config.get("severity")
        out.append(
            DBTNodeResult(
                unique_id=unique_id,
                resource_type=str(node.get("resource_type") or r.get("resource_type") or "model"),
                relation_name=_node_relation_name(node),
                status=str(r.get("status") or "unknown"),
                execution_time=float(r.get("execution_time") or 0.0),
                message=(str(message_raw) if message_raw is not None else None),
                rows_affected=int(rows_aff) if isinstance(rows_aff, int | float) else None,
                depends_on=[str(d) for d in depends_on if d],
                materialization=str(materialized) if materialized else None,
                severity=str(severity_raw) if severity_raw else None,
            ),
        )
    return out


def _op_name_for_node(resource_type: str) -> str:
    """Map dbt resource_type → PointlesSQL op_name.

    Snapshots and seeds map to ``dbt_model`` because they materialise
    a relation just like a model does; tests map to ``dbt_test``
    because they read but never write data.
    """
    if resource_type == "test":
        return "dbt_test"
    return "dbt_model"


def emit_test_failure_rejects(
    session_factory: sessionmaker[Session],
    *,
    agent_run_id: str,
    nodes: list[DBTNodeResult],
    op_ids: list[int],
) -> int:
    """Insert one ``lineage_row_rejects`` row per failing dbt test.

    Walks the (node, op_id) pairs in lockstep and emits a reject row
    for every node whose ``resource_type=='test'`` and ``status=='fail'``.
    The reject row's ``source_row_id`` is the test's ``unique_id`` so
    the row-trace UI can link from failure to test definition; its
    ``detail`` carries dbt's failure message verbatim.

    Per-row extraction (one reject per failing data row, with the
    real ``_lineage_row_id``) is deferred — it would require ``dbt
    test --store-failures`` and a follow-up SELECT against
    ``dbt_test__audit.<test_name>``.  This sprint emits a single
    aggregate reject per test instead.

    Args:
        session_factory: Bound SQLAlchemy session factory.
        agent_run_id: The owning :class:`AgentRun` id.
        nodes: Per-node results in the same order as ``op_ids``.
        op_ids: ``agent_run_operations.id`` values returned by
            :func:`emit_operations_for_dbt_run`, paired with
            ``nodes``.

    Returns:
        Count of reject rows inserted.  Zero when no test failed.

    Raises:
        ValueError: If ``nodes`` and ``op_ids`` differ in length —
            the bridge requires a 1:1 pairing for correct attribution.
    """
    if len(nodes) != len(op_ids):
        raise ValueError("nodes and op_ids must be the same length")
    inserted = 0
    for node, op_id in zip(nodes, op_ids, strict=True):
        if node.resource_type != "test" or node.status != "fail":
            continue
        # The reject's ``source_table`` is the dbt_test__audit relation
        # where ``--store-failures`` would persist the failing rows;
        # for plain ``dbt test`` runs this is the relation the cockpit
        # links to even though no rows exist there yet.
        source_table = node.relation_name or node.unique_id
        record_rejects(
            session_factory,
            run_id=agent_run_id,
            op_id=op_id,
            source_table=source_table,
            rejects=[
                (
                    node.unique_id,
                    "expectation_failed",
                    node.message,
                ),
            ],
        )
        inserted += 1
    return inserted


def emit_operations_for_dbt_run(
    session_factory: sessionmaker[Session],
    *,
    agent_run_id: str,
    nodes: list[DBTNodeResult],
    started_at: datetime.datetime,
) -> list[int]:
    """Insert one ``agent_run_operations`` row per node.

    Each row carries:

    - ``op_name`` ``dbt_model`` or ``dbt_test``
    - ``target_table`` from ``relation_name`` (``None`` for tests)
    - ``rows_affected`` from the adapter response when present
    - ``error_message`` set to the dbt ``message`` when status indicates
      failure (``error`` for models, ``fail`` for tests)
    - ``params_json`` with every dbt-specific field (``unique_id``,
      ``materialization``, ``execution_time``, ``severity``,
      ``depends_on``) so a reviewer can see *why* the row exists
      without joining back to the manifest.

    Args:
        session_factory: Bound SQLAlchemy session factory.
        agent_run_id: The owning :class:`AgentRun` id; must already
            exist in the registry.
        nodes: Per-node results from :func:`merge_manifest_and_results`.
        started_at: Wall-clock instant the dbt invocation started.
            We do not have per-node start times in run_results.json
            (only ``execution_time``), so every row uses the same
            start anchor and ``finished_at = started_at +
            execution_time`` for shape consistency.

    Returns:
        list[int]: The auto-assigned ``agent_run_operations.id`` values
            in the same order as ``nodes``.

    Raises:
        AuditUnavailableError: If the parent run is missing or any
            insert fails.  Strict-mode contract from
            :func:`pointlessql.services.agent_runs.operations.record_operation`.
    """
    op_ids: list[int] = []
    cumulative = started_at
    for node in nodes:
        # Attribute each op a synthetic finished_at = previous_finish +
        # execution_time so the per-op timeline in the run-detail view
        # at least preserves relative ordering.  Real wall-clock per
        # op would need dbt --log-format json + parsing -- deferred.
        finished = cumulative + datetime.timedelta(seconds=max(0.0, node.execution_time))
        cumulative = finished
        is_failure = node.status in {"error", "fail"}
        params = {
            "unique_id": node.unique_id,
            "resource_type": node.resource_type,
            "status": node.status,
            "execution_time": node.execution_time,
            "materialization": node.materialization,
            "depends_on": node.depends_on,
            "severity": node.severity,
        }
        try:
            op_id = record_operation(
                session_factory,
                agent_run_id=agent_run_id,
                op_name=_op_name_for_node(node.resource_type),
                params=params,
                target_table=node.relation_name,
                input_sha=None,
                rows_affected=node.rows_affected,
                delta_version_before=None,
                delta_version_after=None,
                started_at=started_at,
                finished_at=finished,
                error_message=node.message if is_failure else None,
            )
        except AuditUnavailableError:
            # Re-raise so the route returns a 500-shaped error rather
            # than silently dropping audit rows.
            raise
        op_ids.append(op_id)
    return op_ids


def summarise(
    agent_run_id: str,
    nodes: list[DBTNodeResult],
) -> DBTRunSummary:
    """Aggregate per-node outcomes into a response-shaped summary.

    Args:
        agent_run_id: Owning run id.
        nodes: Per-node results.

    Returns:
        DBTRunSummary: Summary with ok / fail / warn / skipped counts.
    """
    ok = sum(1 for n in nodes if n.status in {"success", "pass"})
    fail = sum(1 for n in nodes if n.status in {"error", "fail"})
    warn = sum(1 for n in nodes if n.status == "warn")
    skipped = sum(1 for n in nodes if n.status in {"skipped", "skip"})
    return DBTRunSummary(
        agent_run_id=agent_run_id,
        nodes=nodes,
        ok_count=ok,
        fail_count=fail,
        warn_count=warn,
        skipped_count=skipped,
    )
