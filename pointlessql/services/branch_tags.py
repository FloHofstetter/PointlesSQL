"""Branch metadata tag schema (Sprint 16.5.1).

Reserves the ``pointlessql.branch.*`` tag namespace on UC schemas to
mark them as Delta branches, and provides helpers to apply / read /
mutate that metadata through the existing soyuz tags API.

No soyuz-side schema change is needed: the generic ``tags`` table
already accepts arbitrary ``(securable_type, securable_id, key,
value)`` tuples.  This module is the typed, intent-named layer on
top of that generic shape — callers ask for :class:`BranchTags`,
not a list of dicts.

Both async and sync variants are provided.  The async path drives
the existing :class:`UnityCatalogClient` facade and is consumed by
web routes / Control-Room UI (Sprint 16.5.5).  The sync path drives
the soyuz client directly and is consumed by ``pql/_branch.py``
(Sprint 16.5.2 onwards) so the ``pql.branch`` family stays sync,
matching every other PQL primitive.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from soyuz_catalog_client.api.tags import (
    get_tags_tags_securable_type_full_name_get as _get_tags_api,
)
from soyuz_catalog_client.api.tags import (
    update_tags_tags_securable_type_full_name_patch as _update_tags_api,
)
from soyuz_catalog_client.models.get_tags_tags_securable_type_full_name_get_securable_type import (
    GetTagsTagsSecurableTypeFullNameGetSecurableType,
)
from soyuz_catalog_client.models.tag_list import TagList
from soyuz_catalog_client.models.update_tags import UpdateTags
from soyuz_catalog_client.models.update_tags_tags_securable_type_full_name_patch_securable_type import (  # noqa: E501
    UpdateTagsTagsSecurableTypeFullNamePatchSecurableType,
)

if TYPE_CHECKING:
    from soyuz_catalog_client import Client

    from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)


TAG_PARENT_SCHEMA = "pointlessql.branch.parent_schema"
TAG_PARENT_VERSION_AT_CREATE = "pointlessql.branch.parent_version_at_create"
TAG_CREATED_AT = "pointlessql.branch.created_at"
TAG_CREATED_BY_RUN_ID = "pointlessql.branch.created_by_run_id"
TAG_STRATEGY = "pointlessql.branch.strategy"
TAG_STATUS = "pointlessql.branch.status"
TAG_PROMOTED_AT = "pointlessql.branch.promoted_at"
TAG_DISCARDED_AT = "pointlessql.branch.discarded_at"
TAG_IS_PRE_PROMOTE_BACKUP = "pointlessql.branch.is_pre_promote_backup"

STATUS_ACTIVE = "active"
STATUS_PROMOTED = "promoted"
STATUS_DISCARDED = "discarded"

STRATEGY_SYMLINK = "symlink"
STRATEGY_DEEP_COPY = "deep_copy"

VALID_STATUSES = frozenset({STATUS_ACTIVE, STATUS_PROMOTED, STATUS_DISCARDED})
VALID_STRATEGIES = frozenset({STRATEGY_SYMLINK, STRATEGY_DEEP_COPY})

SECURABLE_TYPE = "schema"


@dataclass(frozen=True)
class BranchTags:
    """Typed view of the ``pointlessql.branch.*`` tag set on one schema.

    Returned by :func:`read_branch_tags` (and its sync sibling) when
    the schema carries the full required tag set.  A schema that
    carries *none* of the required tags yields ``None``; a schema
    that carries *some* but not all required tags raises
    :class:`BranchTagsCorruptError` because that is a corrupted
    state — either the partial-write was interrupted or someone
    tampered with the tag table directly.
    """

    parent_schema: str
    parent_version_at_create: dict[str, int]
    created_at: str
    created_by_run_id: str | None
    strategy: str
    status: str
    promoted_at: str | None = None
    discarded_at: str | None = None
    is_pre_promote_backup: bool = False


class BranchTagsCorruptError(Exception):
    """One or more required branch tags are missing or malformed.

    Raised by :func:`read_branch_tags` (and its sync sibling) when a
    schema carries some branch tags but not the full required set,
    or when a tag value cannot be decoded back into its declared
    type.  Callers should treat this as a hard failure — not as
    "branch not found" — because silent recovery would mask a
    partial-write or external tampering.
    """


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Matches the convention used in :mod:`agent_runs.events` and
    :mod:`agent_runs.operations` so tag timestamps sort
    lexicographically alongside ``CloudEvents.time`` fields.
    """
    return datetime.datetime.now(datetime.UTC).isoformat()


def _set_change(key: str, value: str) -> dict[str, Any]:
    """Build a soyuz ``TagChange`` dict in ``op=set`` shape."""
    return {"key": key, "op": "set", "value": value}


def _remove_change(key: str) -> dict[str, Any]:
    """Build a soyuz ``TagChange`` dict in ``op=remove`` shape."""
    return {"key": key, "op": "remove"}


def _build_initial_changes(
    *,
    parent_schema: str,
    parent_version_at_create: dict[str, int],
    created_by_run_id: str | None,
    strategy: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    """Build the change-list that creates a fresh ``status=active`` branch.

    Args:
        parent_schema: ``catalog.schema`` FQN of the branch's source.
        parent_version_at_create: ``{table_name: delta_version}``
            snapshot used by promotion-conflict detection.
        created_by_run_id: ``agent_runs.id`` if invoked inside a run,
            otherwise ``None``.
        strategy: One of :data:`STRATEGY_SYMLINK` or
            :data:`STRATEGY_DEEP_COPY` — determined by the caller after
            inspecting the parent schema's storage URI scheme.
        created_at: ISO-8601 UTC timestamp; defaults to
            :func:`_now_iso`.  Override only in deterministic tests.

    Returns:
        A list of soyuz ``TagChange`` dicts ready to send to the
        ``PATCH /tags/...`` route.

    Raises:
        ValueError: If ``strategy`` is not a known strategy string.
    """
    if strategy not in VALID_STRATEGIES:
        msg = f"invalid strategy {strategy!r}; expected one of {sorted(VALID_STRATEGIES)}"
        raise ValueError(msg)

    timestamp = created_at or _now_iso()
    changes: list[dict[str, Any]] = [
        _set_change(TAG_PARENT_SCHEMA, parent_schema),
        _set_change(
            TAG_PARENT_VERSION_AT_CREATE,
            json.dumps(parent_version_at_create, sort_keys=True),
        ),
        _set_change(TAG_CREATED_AT, timestamp),
        _set_change(TAG_STRATEGY, strategy),
        _set_change(TAG_STATUS, STATUS_ACTIVE),
    ]
    if created_by_run_id is not None:
        changes.append(_set_change(TAG_CREATED_BY_RUN_ID, created_by_run_id))
    return changes


def _build_status_change(
    status: str,
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Build the change-list that transitions a branch to *status*.

    Args:
        status: Target status (one of :data:`VALID_STATUSES`).
        timestamp: ISO-8601 UTC override; defaults to ``now()``.

    Returns:
        A list of soyuz ``TagChange`` dicts.

    Raises:
        ValueError: If ``status`` is unknown.
    """
    if status not in VALID_STATUSES:
        msg = f"invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}"
        raise ValueError(msg)

    when = timestamp or _now_iso()
    changes: list[dict[str, Any]] = [_set_change(TAG_STATUS, status)]
    if status == STATUS_PROMOTED:
        changes.append(_set_change(TAG_PROMOTED_AT, when))
    elif status == STATUS_DISCARDED:
        changes.append(_set_change(TAG_DISCARDED_AT, when))
    else:
        changes.append(_remove_change(TAG_PROMOTED_AT))
        changes.append(_remove_change(TAG_DISCARDED_AT))
    return changes


def _parse_tag_list(
    tag_dicts: list[dict[str, Any]],
    schema_fqn: str,
) -> BranchTags | None:
    """Pure parser: tag-list dicts → :class:`BranchTags` (or ``None``).

    Shared between the async and sync read paths so both surface
    identical error semantics.

    Args:
        tag_dicts: List of soyuz ``TagEntry`` dicts (as returned by
            ``get_tags`` — each carries at least ``"key"`` and
            ``"value"``).
        schema_fqn: For error messages only.

    Returns:
        :class:`BranchTags` when the schema carries the full required
        set, ``None`` when it carries no branch tags at all.

    Raises:
        BranchTagsCorruptError: Partial / malformed branch tag set.
    """
    by_key = {t.get("key"): t.get("value") for t in tag_dicts}
    branch_keys = {
        k: v
        for k, v in by_key.items()
        if isinstance(k, str) and k.startswith("pointlessql.branch.")
    }
    if not branch_keys:
        return None

    required = (
        TAG_PARENT_SCHEMA,
        TAG_PARENT_VERSION_AT_CREATE,
        TAG_CREATED_AT,
        TAG_STRATEGY,
        TAG_STATUS,
    )
    missing = [k for k in required if k not in branch_keys]
    if missing:
        msg = (
            f"schema {schema_fqn!r} has partial branch metadata; "
            f"missing keys: {missing}.  Refusing to silently treat as non-branch."
        )
        raise BranchTagsCorruptError(msg)

    parent_schema = branch_keys[TAG_PARENT_SCHEMA]
    if not isinstance(parent_schema, str) or not parent_schema:
        msg = f"schema {schema_fqn!r}: {TAG_PARENT_SCHEMA} is empty or non-string"
        raise BranchTagsCorruptError(msg)

    raw_versions = branch_keys[TAG_PARENT_VERSION_AT_CREATE]
    try:
        decoded: Any = json.loads(raw_versions) if isinstance(raw_versions, str) else None
    except json.JSONDecodeError as exc:
        msg = (
            f"schema {schema_fqn!r}: {TAG_PARENT_VERSION_AT_CREATE} is not valid JSON: {exc}"
        )
        raise BranchTagsCorruptError(msg) from exc
    if not isinstance(decoded, dict):
        msg = (
            f"schema {schema_fqn!r}: {TAG_PARENT_VERSION_AT_CREATE} did not decode to a dict"
        )
        raise BranchTagsCorruptError(msg)
    typed_versions: dict[str, int] = {}
    decoded_dict = cast(dict[Any, Any], decoded)
    for table_name_raw, version_raw in decoded_dict.items():
        if not isinstance(table_name_raw, str) or not isinstance(version_raw, int):
            msg = (
                f"schema {schema_fqn!r}: {TAG_PARENT_VERSION_AT_CREATE} entry "
                f"{table_name_raw!r} -> {version_raw!r} is not (str -> int)"
            )
            raise BranchTagsCorruptError(msg)
        typed_versions[table_name_raw] = version_raw

    status = branch_keys[TAG_STATUS]
    if status not in VALID_STATUSES:
        msg = f"schema {schema_fqn!r}: {TAG_STATUS}={status!r} is not in {sorted(VALID_STATUSES)}"
        raise BranchTagsCorruptError(msg)

    strategy = branch_keys[TAG_STRATEGY]
    if strategy not in VALID_STRATEGIES:
        msg = (
            f"schema {schema_fqn!r}: {TAG_STRATEGY}={strategy!r} "
            f"is not in {sorted(VALID_STRATEGIES)}"
        )
        raise BranchTagsCorruptError(msg)

    backup_raw = branch_keys.get(TAG_IS_PRE_PROMOTE_BACKUP)
    is_backup = backup_raw == "true"

    return BranchTags(
        parent_schema=parent_schema,
        parent_version_at_create=typed_versions,
        created_at=str(branch_keys[TAG_CREATED_AT]),
        created_by_run_id=(
            str(branch_keys[TAG_CREATED_BY_RUN_ID])
            if branch_keys.get(TAG_CREATED_BY_RUN_ID) is not None
            else None
        ),
        strategy=str(strategy),
        status=str(status),
        promoted_at=(
            str(branch_keys[TAG_PROMOTED_AT])
            if branch_keys.get(TAG_PROMOTED_AT) is not None
            else None
        ),
        discarded_at=(
            str(branch_keys[TAG_DISCARDED_AT])
            if branch_keys.get(TAG_DISCARDED_AT) is not None
            else None
        ),
        is_pre_promote_backup=is_backup,
    )


# ---------------------------------------------------------------------------
# async API (UnityCatalogClient — for web routes)
# ---------------------------------------------------------------------------


async def apply_branch_tags(
    uc: UnityCatalogClient,
    branch_schema_fqn: str,
    *,
    parent_schema: str,
    parent_version_at_create: dict[str, int],
    created_by_run_id: str | None,
    strategy: str,
    created_at: str | None = None,
) -> None:
    """Stamp the full initial tag set on a freshly-created branch schema.

    The schema must already exist in UC — this function only writes
    metadata.  After this call the schema is ``status=active`` and
    fully discoverable to the rest of Phase 16.5.

    Args:
        uc: UC client (forwards principal + handles soyuz errors).
        branch_schema_fqn: Two-part name of the branch
            (``catalog.branch_name``).
        parent_schema: ``catalog.schema`` FQN of the source.
        parent_version_at_create: ``{table_name: delta_version}``
            snapshot at branch-creation time.
        created_by_run_id: Active ``agent_runs.id`` or ``None`` when
            invoked outside a run.
        strategy: :data:`STRATEGY_SYMLINK` or :data:`STRATEGY_DEEP_COPY`.
        created_at: ISO-8601 UTC override; defaults to ``now()``.
    """
    changes = _build_initial_changes(
        parent_schema=parent_schema,
        parent_version_at_create=parent_version_at_create,
        created_by_run_id=created_by_run_id,
        strategy=strategy,
        created_at=created_at,
    )
    await uc.update_tags(SECURABLE_TYPE, branch_schema_fqn, changes)


async def read_branch_tags(
    uc: UnityCatalogClient,
    schema_fqn: str,
) -> BranchTags | None:
    """Read the branch tag set off one schema, or ``None`` when absent.

    Returns ``None`` when the schema carries *no* ``pointlessql.branch.*``
    tags — that's a normal non-branch schema.  Raises
    :class:`BranchTagsCorruptError` when the schema carries *some* but
    not the full required set, or when a value cannot be decoded.

    Args:
        uc: UC client.
        schema_fqn: ``catalog.schema`` FQN.

    Returns:
        Parsed :class:`BranchTags` or ``None``.
    """
    raw = await uc.get_tags(SECURABLE_TYPE, schema_fqn)
    return _parse_tag_list(raw, schema_fqn)


async def set_branch_status(
    uc: UnityCatalogClient,
    schema_fqn: str,
    status: str,
    *,
    timestamp: str | None = None,
) -> None:
    """Transition the branch status and stamp the matching timestamp tag.

    Side-effects per status:

    * :data:`STATUS_PROMOTED` writes :data:`TAG_PROMOTED_AT`.
    * :data:`STATUS_DISCARDED` writes :data:`TAG_DISCARDED_AT`.
    * :data:`STATUS_ACTIVE` removes both timestamp tags so a future
      reader does not see stale promote/discard markers (defensive
      — Phase 16.5.4 does not currently de-promote branches).

    Args:
        uc: UC client.
        schema_fqn: ``catalog.schema`` FQN of the branch.
        status: Target status.
        timestamp: ISO-8601 UTC override; defaults to ``now()``.
    """
    changes = _build_status_change(status, timestamp=timestamp)
    await uc.update_tags(SECURABLE_TYPE, schema_fqn, changes)


async def mark_pre_promote_backup(uc: UnityCatalogClient, schema_fqn: str) -> None:
    """Tag a (renamed) pre-promote backup schema for later recognition.

    Sprint 16.5.4 promotes a branch by renaming the parent schema to
    ``{parent}_pre_promote_{timestamp}`` and stamping it with this
    tag.  The Control-Room UI (Sprint 16.5.5) lists those backups in
    a separate panel so reviewers can find the original parent state
    after a promotion.

    Args:
        uc: UC client.
        schema_fqn: ``catalog.schema`` FQN of the backup.
    """
    await uc.update_tags(
        SECURABLE_TYPE,
        schema_fqn,
        [_set_change(TAG_IS_PRE_PROMOTE_BACKUP, "true")],
    )


# ---------------------------------------------------------------------------
# sync API (raw soyuz Client — for pql primitives)
# ---------------------------------------------------------------------------


def _update_tags_sync(client: Client, schema_fqn: str, changes: list[dict[str, Any]]) -> None:
    """Sync wrapper over the generated ``PATCH /tags/...`` route."""
    body = UpdateTags.from_dict({"changes": changes})
    securable = UpdateTagsTagsSecurableTypeFullNamePatchSecurableType(SECURABLE_TYPE)
    _update_tags_api.sync(
        securable_type=securable,
        full_name=schema_fqn,
        client=client,
        body=body,
    )


def _get_tags_sync(client: Client, schema_fqn: str) -> list[dict[str, Any]]:
    """Sync wrapper over the generated ``GET /tags/...`` route.

    Returns the tag entries as plain dicts ready for
    :func:`_parse_tag_list`.  An empty list is the "schema has no
    tags" outcome and is also the right shape for "schema unknown
    to soyuz" (the route returns ``200 {"tags": []}`` for both).
    """
    securable = GetTagsTagsSecurableTypeFullNameGetSecurableType(SECURABLE_TYPE)
    response = _get_tags_api.sync(
        securable_type=securable,
        full_name=schema_fqn,
        client=client,
    )
    if not isinstance(response, TagList):
        return []
    tags = response.tags
    if not isinstance(tags, list):
        return []
    return [t.to_dict() for t in tags]


def apply_branch_tags_sync(
    client: Client,
    branch_schema_fqn: str,
    *,
    parent_schema: str,
    parent_version_at_create: dict[str, int],
    created_by_run_id: str | None,
    strategy: str,
    created_at: str | None = None,
) -> None:
    """Sync sibling of :func:`apply_branch_tags`."""
    changes = _build_initial_changes(
        parent_schema=parent_schema,
        parent_version_at_create=parent_version_at_create,
        created_by_run_id=created_by_run_id,
        strategy=strategy,
        created_at=created_at,
    )
    _update_tags_sync(client, branch_schema_fqn, changes)


def read_branch_tags_sync(client: Client, schema_fqn: str) -> BranchTags | None:
    """Sync sibling of :func:`read_branch_tags`."""
    raw = _get_tags_sync(client, schema_fqn)
    return _parse_tag_list(raw, schema_fqn)


def set_branch_status_sync(
    client: Client,
    schema_fqn: str,
    status: str,
    *,
    timestamp: str | None = None,
) -> None:
    """Sync sibling of :func:`set_branch_status`."""
    changes = _build_status_change(status, timestamp=timestamp)
    _update_tags_sync(client, schema_fqn, changes)


def mark_pre_promote_backup_sync(client: Client, schema_fqn: str) -> None:
    """Sync sibling of :func:`mark_pre_promote_backup`."""
    _update_tags_sync(
        client,
        schema_fqn,
        [_set_change(TAG_IS_PRE_PROMOTE_BACKUP, "true")],
    )
