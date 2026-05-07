"""Branch-promote workflow.

Owns :func:`promote_branch_schema` (the pointer-swap atomic rename),
:func:`preview_promote_conflicts` (the dry-run UI helper), and
:func:`_check_promotion_conflicts` (the strict version-equality gate).

Refuses to promote when the parent moved between branch creation and
now — recovery path is discard + re-branch, since Diff+Replay
promotion is intentionally out of scope for v1.
"""

from __future__ import annotations

from typing import Any

import httpx
from deltalake import DeltaTable
from soyuz_catalog_client import Client
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.identifiers import RunId
from pointlessql.pql._branch_errors import (
    BranchInUseError,
    BranchNotFoundError,
    BranchPromotionConflictError,
)
from pointlessql.pql.branch._common import (
    _get_table,
    branch_tags,
    emit_branch_event,
    logger,
    record_branch_audit_log,
    rename_schema,
    split_two_part,
)
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.branch_tags import STATUS_ACTIVE, STATUS_PROMOTED
from pointlessql.settings import Settings


def _check_promotion_conflicts(
    *,
    client: Client,
    parent_schema_fqn: str,
    parent_versions_at_create: dict[str, int],
) -> None:
    """Raise :class:`BranchPromotionConflictError` if the parent moved.

    Walks every entry in *parent_versions_at_create* (one per table
    that existed at branch-creation time), reads the parent table's
    current ``DeltaTable.version()``, and aborts on the first
    mismatch.  The matching is intentionally strict: any divergence
    means symlinked branch parquets reference an obsolete view of
    the parent, so a pointer-swap promotion would silently re-anchor
    main at a stale state.

    A table that disappeared from the parent schema between create
    and promote is also a conflict — promotion would resurrect a
    deleted table.

    Args:
        client: soyuz client.
        parent_schema_fqn: ``catalog.schema``.
        parent_versions_at_create: ``{table_name: version}`` snapshot
            from the branch's ``parent_version_at_create`` tag.

    Raises:
        BranchPromotionConflictError: First detected divergence.
    """
    from soyuz_catalog_client.models.table_info import TableInfo

    catalog, schema = split_two_part(parent_schema_fqn, "parent_schema")
    for table_name, expected_version in parent_versions_at_create.items():
        full_name = f"{catalog}.{schema}.{table_name}"
        try:
            response = _get_table.sync(client=client, full_name=full_name)
        except UnexpectedStatus:
            response = None
        if not isinstance(response, TableInfo):
            raise BranchPromotionConflictError(
                table_name=table_name,
                expected_version=expected_version,
                actual_version=-1,
            )
        location = response.storage_location
        if isinstance(location, Unset) or not location:
            raise BranchPromotionConflictError(
                table_name=table_name,
                expected_version=expected_version,
                actual_version=-1,
            )

        try:
            dt = DeltaTable(location)
            actual_version = int(dt.version())
        except Exception as exc:  # noqa: BLE001 — surface unreadable tables as conflicts
            logger.warning(
                "_check_promotion_conflicts: cannot read %s @ %s: %s",
                table_name,
                location,
                exc,
            )
            raise BranchPromotionConflictError(
                table_name=table_name,
                expected_version=expected_version,
                actual_version=-1,
            ) from exc

        if actual_version != expected_version:
            raise BranchPromotionConflictError(
                table_name=table_name,
                expected_version=expected_version,
                actual_version=actual_version,
            )


def promote_branch_schema(
    *,
    client: Client,
    branch_schema_fqn: str,
    settings: Settings,
    agent_run_id: str | None = None,
) -> dict[str, str]:
    """Promote a branch to be the new parent via UC pointer-swap.

    Atomic two-step rename:

    1. Parent (``catalog.schema``) → ``catalog.schema_pre_promote_<ts>``
       (backup, tagged ``pointlessql.branch.is_pre_promote_backup=true``).
    2. Branch (``catalog.branch_name``) → ``catalog.schema``
       (the new parent).

    Both renames are pure UC metadata mutations — no parquet bytes
    move.  Tables under each schema keep their original
    ``storage_location`` because UC's per-table location is
    independent of the schema name.  Symlinks inside the (now-promoted)
    branch tree continue to resolve because their absolute targets
    haven't moved either.

    Refuses to promote when the parent has moved between branch
    creation and now (:class:`BranchPromotionConflictError`).  The
    caller's recovery is to discard and re-branch — Diff+Replay
    promotion is explicitly out of scope for v1.

    Args:
        client: Configured soyuz client.
        branch_schema_fqn: ``catalog.branch_name`` of the branch.
        settings: Resolved :class:`Settings`.
        agent_run_id: Active run id; ``None`` when admin-driven.

    Returns:
        ``{"new_parent": "catalog.schema",
        "backup": "catalog.schema_pre_promote_<ts>"}``.

    Raises:
        BranchNotFoundError: ``branch_schema_fqn`` not found or has
            no ``pointlessql.branch.*`` tags.
        BranchInUseError: Branch status is not ``active``.
        BranchPromotionConflictError: Parent table moved since
            branch was created.
        CatalogUnavailableError: soyuz unreachable.
    """  # noqa: DOC502,DOC503 — Catalog* / Branch* propagate from helpers
    import datetime

    catalog, branch_name = split_two_part(branch_schema_fqn, "branch_schema")

    tags = branch_tags.read_branch_tags_sync(client, branch_schema_fqn)
    if tags is None:
        msg = f"branch {branch_schema_fqn!r} not found or carries no branch tags"
        raise BranchNotFoundError(msg)
    if tags.status != STATUS_ACTIVE:
        msg = (
            f"cannot promote branch {branch_schema_fqn!r}: "
            f"status={tags.status!r} (only 'active' branches can promote)"
        )
        raise BranchInUseError(msg)

    parent_fqn = tags.parent_schema
    _, parent_name = split_two_part(parent_fqn, "parent_schema")
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"{parent_name}_pre_promote_{timestamp}"
    backup_fqn = f"{catalog}.{backup_name}"

    _check_promotion_conflicts(
        client=client,
        parent_schema_fqn=parent_fqn,
        parent_versions_at_create=tags.parent_version_at_create,
    )

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    with operation_context(
        factory,
        agent_run_id=RunId(agent_run_id) if agent_run_id else None,
        op_name="branch_promote",
        params={
            "branch_schema": branch_schema_fqn,
            "parent_schema": parent_fqn,
        },
        target_table=parent_fqn,
    ) as recorder:
        try:
            # Order-load-bearing: parent → backup first, otherwise
            # the branch → parent rename collides on the existing name.
            rename_schema(client, parent_fqn, backup_name)
            try:
                rename_schema(client, branch_schema_fqn, parent_name)
            except Exception:
                # Best-effort revert of the parent rename so the operator
                # is left with the original layout if the second step
                # fails.  The parent's storage stays put either way.
                logger.exception(
                    "promote_branch_schema: branch rename failed after parent "
                    "rename; reverting %s -> %s",
                    backup_fqn,
                    parent_name,
                )
                try:
                    rename_schema(client, backup_fqn, parent_name)
                except Exception:  # noqa: BLE001 — promotion-revert must surface every failure
                    logger.exception(
                        "promote_branch_schema: revert ALSO failed; manual "
                        "intervention needed (backup=%s, branch=%s)",
                        backup_fqn,
                        branch_schema_fqn,
                    )
                raise

            # The branch is now at parent_fqn — update its tags in place.
            branch_tags.set_branch_status_sync(client, parent_fqn, STATUS_PROMOTED)
            # The old parent (now backup) gets the marker tag.
            branch_tags.mark_pre_promote_backup_sync(client, backup_fqn)

            recorder.extra_params.update(
                {
                    "backup": backup_fqn,
                    "parent_versions_at_create": tags.parent_version_at_create,
                }
            )
        except httpx.ConnectError as exc:
            raise CatalogUnavailableError(
                f"Cannot reach soyuz-catalog while promoting branch {branch_schema_fqn!r}."
            ) from exc

    record_branch_audit_log(
        branch_schema_fqn=branch_schema_fqn,
        parent_schema_fqn=parent_fqn,
        action="promote",
        run_id=agent_run_id,
        payload={
            "backup": backup_fqn,
            "parent_versions_at_create": tags.parent_version_at_create,
            "strategy": tags.strategy,
        },
    )

    emit_branch_event(
        settings=settings,
        event_type="pointlessql.branch.promoted.v1",
        data={
            "branch_schema": branch_schema_fqn,
            "promoted_to": parent_fqn,
            "backup": backup_fqn,
            "run_id": agent_run_id,
            "strategy": tags.strategy,
        },
    )

    # Reference branch_name to silence linters; future iterations may
    # use it for per-branch metric narrowing.
    del branch_name

    return {"new_parent": parent_fqn, "backup": backup_fqn}


def preview_promote_conflicts(
    *,
    client: Client,
    branch_schema_fqn: str,
) -> dict[str, Any]:
    """Dry-run conflict-detection for the Control-Room "Preview promote".

    No side effects.  Returns a dict the UI can render directly:

    * ``ok``: ``True`` when zero conflicts are detected.
    * ``conflicts``: list of ``{table, expected_version, actual_version}``
      entries, empty on the happy path.

    Args:
        client: soyuz client.
        branch_schema_fqn: ``catalog.branch_name``.

    Returns:
        Conflict report dict.

    Raises:
        BranchNotFoundError: No branch tags at *branch_schema_fqn*.
    """
    tags = branch_tags.read_branch_tags_sync(client, branch_schema_fqn)
    if tags is None:
        msg = f"branch {branch_schema_fqn!r} not found or carries no branch tags"
        raise BranchNotFoundError(msg)

    from soyuz_catalog_client.models.table_info import TableInfo

    conflicts: list[dict[str, Any]] = []
    catalog, schema = split_two_part(tags.parent_schema, "parent_schema")
    for table_name, expected_version in tags.parent_version_at_create.items():
        full_name = f"{catalog}.{schema}.{table_name}"
        actual_version = -1
        try:
            response = _get_table.sync(client=client, full_name=full_name)
        except UnexpectedStatus:
            response = None
        if not isinstance(response, TableInfo):
            conflicts.append(
                {
                    "table": table_name,
                    "expected_version": expected_version,
                    "actual_version": actual_version,
                    "reason": "missing",
                }
            )
            continue
        location = response.storage_location
        if isinstance(location, Unset) or not location:
            conflicts.append(
                {
                    "table": table_name,
                    "expected_version": expected_version,
                    "actual_version": actual_version,
                    "reason": "no_storage_location",
                }
            )
            continue
        try:
            dt = DeltaTable(location)
            actual_version = int(dt.version())
        except Exception as exc:  # noqa: BLE001 — diagnostic-only path
            # bare-broad-ok: failure detail surfaces in conflicts payload
            conflicts.append(
                {
                    "table": table_name,
                    "expected_version": expected_version,
                    "actual_version": -1,
                    "reason": f"unreadable: {exc}",
                }
            )
            continue
        if actual_version != expected_version:
            conflicts.append(
                {
                    "table": table_name,
                    "expected_version": expected_version,
                    "actual_version": actual_version,
                    "reason": "version_drift",
                }
            )

    return {"ok": not conflicts, "conflicts": conflicts}
