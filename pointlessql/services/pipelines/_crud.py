"""Pipeline persistence, dataset validation, and DAG derivation."""

from __future__ import annotations

import datetime
import json
import re
import uuid
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, select

from pointlessql.models.pipelines import (
    PIPELINE_DATASET_KINDS,
    PIPELINE_EXPECTATION_ACTIONS,
    Pipeline,
    PipelineCursor,
    PipelineRun,
)
from pointlessql.pql import prepare_sql

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

_FQN_RE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PipelineValidationError(ValueError):
    """Raised when a pipeline definition cannot be compiled into a DAG."""


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _slugify(title: str) -> str:
    """Derive a collision-proof slug from *title*."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "pipeline"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def validate_datasets(datasets: Any) -> list[dict[str, Any]]:
    """Validate and normalise a dataset-definition list.

    Args:
        datasets: Candidate list of dataset dicts (``name`` 3-part
            target FQN, ``kind``, ``sql`` single SELECT,
            ``expectations`` list).

    Returns:
        The normalised list (refs pre-extracted under ``"refs"``).

    Raises:
        PipelineValidationError: On structural problems — duplicate
            targets, unknown kinds, non-SELECT SQL, a streaming
            table reading more than one source, or malformed
            expectations.
    """
    if not isinstance(datasets, list) or not datasets:
        raise PipelineValidationError("a pipeline needs at least one dataset")
    seen: set[str] = set()
    normalised: list[dict[str, Any]] = []
    for raw in cast("list[object]", datasets):
        if not isinstance(raw, dict):
            raise PipelineValidationError("each dataset must be an object")
        entry = cast("dict[str, Any]", raw)
        name = str(entry.get("name", "")).strip()
        if not _FQN_RE.match(name):
            raise PipelineValidationError(
                f"dataset target must be catalog.schema.table, got {name!r}"
            )
        if name in seen:
            raise PipelineValidationError(f"duplicate dataset target {name!r}")
        seen.add(name)
        kind = str(entry.get("kind", ""))
        if kind not in PIPELINE_DATASET_KINDS:
            raise PipelineValidationError(
                f"kind must be one of {', '.join(PIPELINE_DATASET_KINDS)}, got {kind!r}"
            )
        sql = str(entry.get("sql", "")).strip().rstrip(";")
        if not sql:
            raise PipelineValidationError(f"dataset {name!r} needs a SELECT")
        try:
            prepared = prepare_sql(sql)
        except Exception as exc:  # noqa: BLE001 — surface parser detail verbatim
            raise PipelineValidationError(f"dataset {name!r} SQL: {exc}") from exc
        refs = list(prepared.refs)
        if name in refs:
            raise PipelineValidationError(f"dataset {name!r} reads itself")
        if kind == "streaming_table" and len(refs) != 1:
            raise PipelineValidationError(
                f"streaming table {name!r} must read exactly one source table"
            )
        expectations = _validate_expectations(entry.get("expectations"), dataset=name)
        normalised.append(
            {
                "name": name,
                "kind": kind,
                "sql": sql,
                "refs": refs,
                "expectations": expectations,
            }
        )
    topological_order(normalised)  # raises on cycles
    return normalised


def _validate_expectations(raw: Any, *, dataset: str) -> list[dict[str, str]]:
    """Validate one dataset's expectation list."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise PipelineValidationError(f"dataset {dataset!r}: expectations must be a list")
    result: list[dict[str, str]] = []
    names: set[str] = set()
    for item in cast("list[object]", raw):
        if not isinstance(item, dict):
            raise PipelineValidationError(f"dataset {dataset!r}: each expectation is an object")
        entry = cast("dict[str, Any]", item)
        name = str(entry.get("name", "")).strip()
        if not _NAME_RE.match(name) or name in names:
            raise PipelineValidationError(
                f"dataset {dataset!r}: expectation names must be unique identifiers"
            )
        names.add(name)
        constraint = str(entry.get("constraint", "")).strip()
        if not constraint or ";" in constraint:
            raise PipelineValidationError(
                f"dataset {dataset!r}: expectation {name!r} needs a single SQL predicate"
            )
        action = str(entry.get("action", "warn"))
        if action not in PIPELINE_EXPECTATION_ACTIONS:
            raise PipelineValidationError(
                f"dataset {dataset!r}: expectation action must be one of "
                f"{', '.join(PIPELINE_EXPECTATION_ACTIONS)}"
            )
        result.append({"name": name, "constraint": constraint, "action": action})
    return result


def topological_order(datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return *datasets* in dependency order (Kahn's algorithm).

    Args:
        datasets: Normalised dataset definitions (with ``refs``).

    Returns:
        The datasets reordered so every internal dependency runs
        before its consumers.

    Raises:
        PipelineValidationError: When the internal references form a
            cycle.
    """
    by_name = {d["name"]: d for d in datasets}
    indegree: dict[str, int] = {name: 0 for name in by_name}
    consumers: dict[str, list[str]] = {name: [] for name in by_name}
    for dataset in datasets:
        for ref in dataset["refs"]:
            if ref in by_name:
                indegree[dataset["name"]] += 1
                consumers[ref].append(dataset["name"])
    queue = sorted(name for name, degree in indegree.items() if degree == 0)
    ordered: list[dict[str, Any]] = []
    while queue:
        name = queue.pop(0)
        ordered.append(by_name[name])
        for consumer in consumers[name]:
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                queue.append(consumer)
        queue.sort()
    if len(ordered) != len(datasets):
        cyclic = sorted(name for name, degree in indegree.items() if degree > 0)
        raise PipelineValidationError(f"dataset dependencies form a cycle: {', '.join(cyclic)}")
    return ordered


def parse_datasets(pipeline: Pipeline) -> list[dict[str, Any]]:
    """Parse + re-validate a stored pipeline's dataset JSON.

    Args:
        pipeline: The pipeline row.

    Returns:
        Normalised dataset definitions.

    Raises:
        PipelineValidationError: When the stored document no longer
            validates (e.g. hand-edited rows).
    """
    try:
        raw = json.loads(pipeline.datasets or "[]")
    except ValueError as exc:
        raise PipelineValidationError(f"stored datasets are not JSON: {exc}") from exc
    return validate_datasets(raw)


def create_pipeline(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    title: str,
    description: str | None,
    owner_id: int,
    datasets: Any,
) -> Pipeline:
    """Create a pipeline from a validated dataset document.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        title: Human-readable name.
        description: Optional description.
        owner_id: Creating user's id (runs execute as the owner).
        datasets: Dataset-definition list (validated).

    Returns:
        The persisted row (detached).

    Raises:
        PipelineValidationError: On an empty title or invalid
            datasets.
    """
    cleaned = title.strip()
    if not cleaned:
        raise PipelineValidationError("title must be a non-empty string")
    normalised = validate_datasets(datasets)
    now = _utcnow()
    row = Pipeline(
        workspace_id=workspace_id,
        slug=_slugify(cleaned),
        title=cleaned,
        description=description,
        owner_id=owner_id,
        datasets=json.dumps(normalised),
        created_at=now,
        updated_at=now,
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_pipelines(factory: sessionmaker[Session], *, workspace_id: int) -> list[Pipeline]:
    """List the workspace's pipelines, newest-updated first.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.

    Returns:
        Detached pipeline rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(Pipeline)
                .where(Pipeline.workspace_id == workspace_id)
                .order_by(Pipeline.updated_at.desc())
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def get_pipeline(
    factory: sessionmaker[Session], *, workspace_id: int, slug: str
) -> Pipeline | None:
    """Return the workspace's pipeline by slug, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        slug: Pipeline slug.

    Returns:
        The detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.scalar(
            select(Pipeline).where(
                Pipeline.workspace_id == workspace_id,
                Pipeline.slug == slug,
            )
        )
        if row is not None:
            session.expunge(row)
    return row


def update_pipeline(
    factory: sessionmaker[Session],
    *,
    pipeline_id: int,
    title: str | None = None,
    description: str | None = None,
    datasets: Any = None,
) -> Pipeline | None:
    """Patch title / description / datasets.

    Args:
        factory: SQLAlchemy session factory.
        pipeline_id: Primary key.
        title: New title, or ``None`` to keep.
        description: New description, or ``None`` to keep.
        datasets: New dataset document, or ``None`` to keep
            (validated when provided).

    Returns:
        The refreshed detached row, or ``None`` when absent.

    Raises:
        PipelineValidationError: On invalid input.
    """
    with factory() as session:
        row = session.get(Pipeline, pipeline_id)
        if row is None:
            return None
        if title is not None:
            cleaned = title.strip()
            if not cleaned:
                raise PipelineValidationError("title must be a non-empty string")
            row.title = cleaned
        if description is not None:
            row.description = description
        if datasets is not None:
            row.datasets = json.dumps(validate_datasets(datasets))
        row.updated_at = _utcnow()
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def delete_pipeline(factory: sessionmaker[Session], *, pipeline_id: int) -> bool:
    """Delete a pipeline with its runs and cursors.

    Args:
        factory: SQLAlchemy session factory.
        pipeline_id: Primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(Pipeline, pipeline_id)
        if row is None:
            return False
        session.execute(delete(PipelineRun).where(PipelineRun.pipeline_id == pipeline_id))
        session.execute(delete(PipelineCursor).where(PipelineCursor.pipeline_id == pipeline_id))
        session.delete(row)
        session.commit()
    return True


def list_runs(
    factory: sessionmaker[Session], *, pipeline_id: int, limit: int = 20
) -> list[PipelineRun]:
    """List a pipeline's most recent runs.

    Args:
        factory: SQLAlchemy session factory.
        pipeline_id: Primary key.
        limit: Maximum rows returned.

    Returns:
        Detached run rows, newest first.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(PipelineRun)
                .where(PipelineRun.pipeline_id == pipeline_id)
                .order_by(PipelineRun.id.desc())
                .limit(limit)
            )
        )
        for row in rows:
            session.expunge(row)
    return rows
