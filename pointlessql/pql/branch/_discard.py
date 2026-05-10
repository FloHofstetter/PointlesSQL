"""Branch-discard workflow.

Owns :func:`discard_branch_schema` and the local-FS storage cleanup
helper.  Idempotent against an already-discarded branch; refuses to
discard a promoted branch (post-promote backup is not "the branch"
any more).
"""

from __future__ import annotations

import shutil
from typing import cast

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.schema_info import SchemaInfo

from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.pql._branch_errors import (
    BranchInUseError,
    BranchNotFoundError,
)
from pointlessql.pql.branch._common import (
    _get_schema,
    branch_tags,
    classify_storage_scheme,
    emit_branch_event,
    logger,
    record_branch_audit_log,
    resolve_storage_root,
    split_two_part,
    uri_to_local_path,
)
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.branch_tags import (
    STATUS_DISCARDED,
    STATUS_PROMOTED,
)
from pointlessql.settings import Settings
from pointlessql.types import BranchAction, OpName, RunId


def discard_branch_schema(
    *,
    client: Client,
    branch_schema_fqn: str,
    settings: Settings,
    agent_run_id: str | None = None,
) -> None:
    """Permanently remove a Delta branch and its UC namespace.

    Idempotent: a branch already in ``status='discarded'`` is a no-op
    plus a warning log.  Branches in ``status='promoted'`` are
    refused with :class:`BranchInUseError` because the post-promote
    backup is not a "branch" any more — it's the previous parent
    state preserved for time-travel.

    Storage cleanup is safe-by-design for both clone modes:

    * Symlink branches: ``shutil.rmtree`` on the branch directory
      removes the symlinks themselves, not the source parquets they
      point at.
    * Deep-copy branches: ``rmtree`` removes the branch's owned
      copies.

    Cloud-storage discard is a follow-up — the v1 path requires the
    branch to be local FS, which is the only configuration that
    16.5.2 actually creates today.

    Args:
        client: Configured soyuz client.
        branch_schema_fqn: ``catalog.schema`` of the branch.
        settings: Resolved :class:`Settings`.
        agent_run_id: Active run id; ``None`` when invoked from a
            scheduler / admin path.

    Raises:
        BranchNotFoundError: ``branch_schema_fqn`` does not exist
            in UC, or exists but carries no ``pointlessql.branch.*``
            tags (refusing to delete a non-branch schema).
        BranchInUseError: Branch is in ``status='promoted'``.
        CatalogUnavailableError: soyuz unreachable.
    """  # noqa: DOC502,DOC503 — Catalog* / Branch* propagate from helpers
    catalog, branch_name = split_two_part(branch_schema_fqn, "branch_schema")

    try:
        existing = _get_schema.sync(client=client, full_name=branch_schema_fqn)
    except UnexpectedStatus:
        existing = None
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(
            f"Cannot reach soyuz-catalog while resolving {branch_schema_fqn!r}."
        ) from exc

    tags = branch_tags.read_branch_tags_sync(client, branch_schema_fqn)
    if not isinstance(existing, SchemaInfo) and tags is None:
        msg = f"branch {branch_schema_fqn!r} not found in soyuz-catalog"
        raise BranchNotFoundError(msg)
    if tags is None:
        msg = (
            f"schema {branch_schema_fqn!r} exists in soyuz-catalog but carries no "
            f"pointlessql.branch.* tags — refusing to discard a non-branch schema"
        )
        raise BranchNotFoundError(msg)
    if tags.status == STATUS_PROMOTED:
        msg = f"cannot discard branch {branch_schema_fqn!r}: status='promoted' (promotion is final)"
        raise BranchInUseError(msg)
    if tags.status == STATUS_DISCARDED:
        logger.warning(
            "discard_branch_schema: %s already status='discarded' — no-op",
            branch_schema_fqn,
        )
        return

    storage_root = (
        resolve_storage_root(existing, branch_schema_fqn)
        if isinstance(existing, SchemaInfo)
        else None
    )

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    with operation_context(
        factory,
        agent_run_id=cast(RunId | None, agent_run_id),
        op_name=OpName.BRANCH_DISCARD,
        params={
            "branch_schema": branch_schema_fqn,
            "parent_schema": tags.parent_schema,
        },
        target_table=branch_schema_fqn,
    ) as recorder:
        try:
            _delete_branch_storage(storage_root)

            from pointlessql.services.unitycatalog._api import (
                _delete_schema as delete_schema_api,
            )

            delete_schema_api.sync(
                full_name=branch_schema_fqn,
                client=client,
                force=True,
            )

            recorder.extra_params.update(
                {
                    "strategy": tags.strategy,
                    "deleted_storage_root": storage_root,
                }
            )
        except httpx.ConnectError as exc:
            raise CatalogUnavailableError(
                f"Cannot reach soyuz-catalog while discarding branch {branch_schema_fqn!r}."
            ) from exc

    record_branch_audit_log(
        branch_schema_fqn=branch_schema_fqn,
        parent_schema_fqn=tags.parent_schema,
        action=BranchAction.DISCARD,
        run_id=agent_run_id,
        payload={
            "strategy": tags.strategy,
            "parent_versions": tags.parent_version_at_create,
            "deleted_storage_root": storage_root,
        },
    )

    emit_branch_event(
        settings=settings,
        event_type="pointlessql.branch.discarded.v1",
        data={
            "branch_schema": branch_schema_fqn,
            "parent_schema": tags.parent_schema,
            "run_id": agent_run_id,
            "strategy": tags.strategy,
        },
    )

    # Reference catalog/branch_name for log narrowing only — keeping
    # them named in the discard path makes future per-catalog cleanup
    # filters trivial.
    del catalog, branch_name


def _delete_branch_storage(storage_root: str | None) -> None:
    """Remove a branch's local-FS storage tree.

    Safe for both clone modes: ``shutil.rmtree`` unlinks symlinks
    rather than recursing into them, so a symlink-strategy branch's
    cleanup does not touch the source parquets.

    A no-op when *storage_root* is ``None`` (UC schema vanished
    independently — only the audit row + tag cleanup remain) or when
    the directory does not exist (idempotent re-discard).

    Args:
        storage_root: URI returned by UC for the branch schema, or
            ``None``.

    Raises:
        ValueError: When *storage_root* is on cloud storage —
            the v1 discard path is local-FS only, mirroring the
            v1 create path.
    """
    if not storage_root:
        return
    scheme = classify_storage_scheme(storage_root)
    if scheme == "cloud":
        msg = (
            f"cloud-storage discard not implemented in v1 (storage_root={storage_root!r}); "
            f"this is a follow-up"
        )
        raise ValueError(msg)
    branch_path = uri_to_local_path(storage_root)
    if branch_path.exists():
        shutil.rmtree(branch_path)
