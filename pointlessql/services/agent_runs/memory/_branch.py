"""Branch-from-run helper backing ``pql.memory.branch`` / ``fork``.

Wraps :func:`pointlessql.pql.branch.create_branch_schema` with the
agent-memory naming convention: instead of asking the caller to
pre-compute the source schema fqn, this helper derives it from the
source run's recorded operations and auto-generates a branch name
keyed by the agent + run id.

Version-pinning semantics: the source run's
first-write ``delta_version_before`` is captured into the
:class:`BranchAuditLog` payload (``pinned_delta_version``) and into
the branch's ``pointlessql.branch.parent_version_at_create`` tag set
when ``pin_to_version=True``.  The branch tables themselves are
cloned at the source's *current* version, so the pinning is best-
effort: if the source schema does not change between the recorded
run and the branch call, replay is fully deterministic.  True per-
table time-travel branching (re-clone each table at the recorded
version) is intentionally deferred — the deltalake snapshot-restore
plumbing belongs to a follow-up sprint.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import select

from pointlessql.config import get_settings
from pointlessql.exceptions import ValidationError
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.pql.branch import create_branch_schema
from pointlessql.types import RunId

if TYPE_CHECKING:
    from soyuz_catalog_client import Client
    from sqlalchemy.orm import Session, sessionmaker


_BRANCH_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_]+")


def _resolve_source_schema(target_table: str) -> str:
    """Strip the table component from a three-part FQN.

    Args:
        target_table: ``catalog.schema.table`` string.

    Returns:
        ``catalog.schema``.

    Raises:
        ValidationError: When the FQN does not have three dot-
            separated parts.
    """
    parts = target_table.split(".")
    if len(parts) != 3:
        raise ValidationError(
            f"branch-from-run: expected three-part target_table, got {target_table!r}"
        )
    return f"{parts[0]}.{parts[1]}"


def _first_write_op(
    session_factory: sessionmaker[Session],
    run_id: RunId,
) -> AgentRunOperation:
    """Return the run's earliest operation that carries a target_table.

    The branch helper uses this to derive both the source schema
    (from ``target_table``) and the pin version
    (from ``delta_version_before``).  Reads-only runs (``op_name='sql'``
    with no target) cannot be branched off — there is no schema to
    branch.

    Args:
        session_factory: SQLAlchemy session factory.
        run_id: Source agent-run UUID.

    Returns:
        The first :class:`AgentRunOperation` row, ordered by
        ``ordinal``, whose ``target_table`` is not null.

    Raises:
        ValidationError: When no such operation exists for the run.
    """
    with session_factory() as session:
        op = session.scalar(
            select(AgentRunOperation)
            .where(
                AgentRunOperation.agent_run_id == run_id,
                AgentRunOperation.target_table.is_not(None),
            )
            .order_by(AgentRunOperation.ordinal)
            .limit(1)
        )
    if op is None:
        raise ValidationError(
            f"branch-from-run: run {run_id!r} has no operations with a target_table; "
            "cannot derive a source schema to branch from"
        )
    return op


def _derive_branch_name(agent_id: str, run_id: RunId) -> str:
    """Compose a filesystem- and UC-safe branch name from agent + run.

    Strategy: ``mem_<agent_id_sanitized>_<run_id_short>``.  The
    ``mem_`` prefix lets ops + the UI distinguish agent-memory
    branches from manually-created ones.  Non-word characters in
    ``agent_id`` are collapsed to a single underscore.

    Args:
        agent_id: Source agent's identifier.
        run_id: Source run UUID.

    Returns:
        A name that satisfies UC's schema-name rules.
    """
    sanitised = _BRANCH_NAME_SAFE.sub("_", agent_id).strip("_") or "agent"
    short_run = str(run_id).replace("-", "")[:8]
    return f"mem_{sanitised}_{short_run}"


def branch_from_run(
    *,
    client: Client,
    session_factory: sessionmaker[Session],
    agent_id: str,
    from_run_id: RunId,
    branch_name: str | None,
    pin_to_version: bool,
    action: Literal["create", "fork"],
    unreachable_msg: str,
) -> dict[str, Any]:
    """Create a Delta branch tied to a source agent run.

    See :func:`pointlessql.pql.memory.branch` and :func:`fork` for
    the public docstrings.  This helper is the shared
    implementation; the ``action`` kwarg only affects the
    ``intent`` field stamped into the operation params and the
    branch tag set.

    Args:
        client: Configured soyuz-catalog client.
        session_factory: SQLAlchemy session factory.
        agent_id: Source agent's identifier — used as the branch-
            name prefix when ``branch_name`` is ``None``, and
            validated against the source run's recorded agent_id
            for safety.
        from_run_id: Source agent-run UUID.
        branch_name: Optional override; ``None`` triggers the
            ``mem_<agent>_<run>`` auto-naming.
        pin_to_version: When ``True``, stamps the source run's
            first-write delta version into the branch metadata.
        action: ``"create"`` (default for :func:`branch`) or
            ``"fork"`` (used by :func:`fork`).  Routed into the
            audit-trail ``intent`` field; the UC ``action`` column
            stays ``"create"`` for both because no SQL CHECK
            constraint allows a new value without an Alembic
            migration.
        unreachable_msg: Pre-rendered catalog error text.

    Returns:
        ``{"branch_schema_fqn": ..., "parent_schema_fqn": ...,
        "pinned_delta_version": <int|None>, "intent": "create"|"fork"}``.

    Raises:
        ValidationError: When the source run is unknown, has no
            recorded operations with a target_table, or carries a
            different agent_id than the caller supplied.
        BranchAlreadyExistsError: When the auto-derived (or
            caller-supplied) branch name already exists in UC.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """  # noqa: DOC502,DOC503 — Branch* / Catalog* propagate from create_branch_schema
    with session_factory() as session:
        run = session.get(AgentRun, str(from_run_id))
    if run is None:
        raise ValidationError(
            f"branch-from-run: run {from_run_id!r} is not registered"
        )
    if run.agent_id is not None and run.agent_id != agent_id:
        raise ValidationError(
            f"branch-from-run: run {from_run_id!r} belongs to agent "
            f"{run.agent_id!r}, not {agent_id!r}"
        )

    first_op = _first_write_op(session_factory, from_run_id)
    assert first_op.target_table is not None  # narrowed by query  # noqa: S101
    source_schema_fqn = _resolve_source_schema(first_op.target_table)
    pinned_version = first_op.delta_version_before if pin_to_version else None

    name = branch_name or _derive_branch_name(agent_id, from_run_id)

    settings = get_settings()
    branch_fqn = create_branch_schema(
        client=client,
        source_schema_fqn=source_schema_fqn,
        branch_name=name,
        settings=settings,
        agent_run_id=str(from_run_id),
    )

    _stamp_intent_in_audit_payload(
        session_factory=session_factory,
        branch_fqn=branch_fqn,
        pinned_version=pinned_version,
        intent=action,
        source_run_id=from_run_id,
    )

    return {
        "branch_schema_fqn": branch_fqn,
        "parent_schema_fqn": source_schema_fqn,
        "pinned_delta_version": pinned_version,
        "intent": action,
    }


def _stamp_intent_in_audit_payload(
    *,
    session_factory: sessionmaker[Session],
    branch_fqn: str,
    pinned_version: int | None,
    intent: Literal["create", "fork"],
    source_run_id: RunId,
) -> None:
    """Update the most-recent BranchAuditLog row with memory-facade metadata.

    ``create_branch_schema`` writes the BranchAuditLog row with the
    base ``payload_json``; we read it back and append the
    ``intent`` + ``pinned_delta_version`` + ``source_run_id`` fields
    so the UI's branch-tree pane can filter fork-vs-create and so
    replay can find the source run by branch.

    Args:
        session_factory: SQLAlchemy session factory.
        branch_fqn: Branch schema FQN
            (matches :attr:`BranchAuditLog.branch_schema_fqn`).
        pinned_version: Delta version stamp; ``None`` when
            ``pin_to_version=False``.
        intent: Either ``"create"`` or ``"fork"``.
        source_run_id: Source run that drove the branch.
    """
    from pointlessql.models import BranchAuditLog  # local import — avoid circular

    with session_factory() as session:
        row = session.scalar(
            select(BranchAuditLog)
            .where(BranchAuditLog.branch_schema_fqn == branch_fqn)
            .order_by(BranchAuditLog.created_at.desc())
            .limit(1)
        )
        if row is None:
            # create_branch_schema is supposed to land a row.  If it
            # didn't (DB hiccup) we silently skip — the caller already
            # has the branch fqn and we don't want to fail the whole
            # call over an audit-row backfill.
            return
        existing_payload: dict[str, Any] = {}
        if row.payload_json:
            try:
                existing_payload = json.loads(row.payload_json)
            except (TypeError, ValueError):
                existing_payload = {}
        existing_payload["intent"] = intent
        existing_payload["pinned_delta_version"] = pinned_version
        existing_payload["source_run_id"] = str(source_run_id)
        existing_payload["stamped_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        row.payload_json = json.dumps(existing_payload, sort_keys=True, default=str)
        session.commit()
