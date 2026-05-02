"""Helpers for the  Delta-branching primitives.

Implements ``pql.branch``, ``pql.branch_discard``
(), and ``pql.branch_promote`` on top
of the soyuz UC client and the local Delta storage layout.

The branch-creation path (this sprint) is the central piece — once
a branch exists in UC with the right ``pointlessql.branch.*`` tags
and per-table symlinked / deep-copied parquet files plus a fresh
``_delta_log/``, agents write into it via the normal ``pql.write_table``
/ ``pql.merge`` primitives.

Hybrid storage strategy from ADR-0003:

* Local filesystem (``file://`` or absolute path): build symlinks
  inside the branch's storage prefix that point at the source's
  parquet files, then synth a Delta log referencing the symlinks
  by relative path.  Zero parquet bytes copied.
* Object storage (``s3://``, ``gs://``, ``abfss://``, ``wasbs://``):
  no symlink primitive — operator must opt into ``deep_copy``
  via the ``branch.cloud_strategy`` setting, otherwise the
  primitive raises :class:`BranchCloudUnsupportedError`.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import unquote, urlparse

import httpx
import pyarrow as pa
from deltalake import DeltaTable
from deltalake.transaction import AddAction
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.schemas import (
    create_schema_api_2_1_unity_catalog_schemas_post as _create_schema,
)
from soyuz_catalog_client.api.schemas import (
    get_schema_api_2_1_unity_catalog_schemas_full_name_get as _get_schema,
)
from soyuz_catalog_client.api.schemas import (
    update_schema_api_2_1_unity_catalog_schemas_full_name_patch as _update_schema,
)
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_schema import CreateSchema
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.update_schema import UpdateSchema
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.pql._branch_errors import (
    BranchAlreadyExistsError,
    BranchCloudUnsupportedError,
    BranchInUseError,
    BranchNotFoundError,
    BranchOfBranchError,
    BranchPromotionConflictError,
)
from pointlessql.services import branch_tags
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.branch_tags import (
    STATUS_ACTIVE,
    STATUS_DISCARDED,
    STATUS_PROMOTED,
    STRATEGY_DEEP_COPY,
    STRATEGY_SYMLINK,
)
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)


CLOUD_SCHEMES = frozenset({"s3", "gs", "gcs", "abfss", "abfs", "wasbs", "wasb", "az"})
LOCAL_SCHEMES = frozenset({"file", ""})


def _classify_storage_scheme(storage_uri: str) -> Literal["local", "cloud"]:
    """Classify a storage URI as ``local`` or ``cloud``.

    A bare absolute path (no scheme) is local.  ``file://`` URIs are
    local.  Object-store schemes are cloud.  Anything else raises
    ``ValueError`` so we never silently fall through to the wrong
    branch strategy.

    Args:
        storage_uri: The schema's ``storage_root`` or ``storage_location``.

    Returns:
        ``"local"`` or ``"cloud"``.

    Raises:
        ValueError: Unknown scheme.
    """
    parsed = urlparse(storage_uri)
    scheme = parsed.scheme.lower()
    if scheme in LOCAL_SCHEMES:
        return "local"
    if scheme in CLOUD_SCHEMES:
        return "cloud"
    msg = f"unsupported storage scheme {scheme!r} on URI {storage_uri!r}"
    raise ValueError(msg)


def _uri_to_local_path(storage_uri: str) -> Path:
    """Resolve a local storage URI down to an absolute :class:`Path`.

    Accepts both ``file://`` URIs and bare absolute paths.  Path-encoded
    URIs are URL-decoded.  Raises ``ValueError`` for non-local URIs.

    Args:
        storage_uri: URI returned by UC's ``storage_root`` /
            ``storage_location``.

    Returns:
        Resolved :class:`Path`.

    Raises:
        ValueError: When the URI is not on a local filesystem.
    """
    parsed = urlparse(storage_uri)
    scheme = parsed.scheme.lower()
    if scheme not in LOCAL_SCHEMES:
        msg = f"_uri_to_local_path called on non-local URI {storage_uri!r}"
        raise ValueError(msg)
    if scheme == "file":
        return Path(unquote(parsed.path))
    return Path(storage_uri)


def _derive_branch_storage_root(parent_storage_root: str, branch_name: str) -> str:
    """Compute the storage root URI for a new branch schema.

    Stays under the parent's prefix (``{parent}/_branches/{name}/``) so
    cloud-storage scanners walking the parent prefix don't have to
    learn a new "branches live elsewhere" rule.  The leading
    ``_`` plus ``branches`` are conventionally hidden by file
    browsers and by our own catalog tree.

    Args:
        parent_storage_root: As reported by UC for the source schema.
        branch_name: Plain schema name (no catalog prefix).

    Returns:
        Storage root URI for the branch.
    """
    return f"{parent_storage_root.rstrip('/')}/_branches/{branch_name}"


def _split_two_part(name: str, kind: str) -> tuple[str, str]:
    """Split a ``catalog.schema`` two-part name; raise on malformed input."""
    parts = name.split(".")
    if len(parts) != 2 or not all(parts):
        msg = f"{kind} {name!r} must be a two-part 'catalog.schema' name"
        raise ValueError(msg)
    return parts[0], parts[1]


def _ensure_source_schema(client: Client, source_schema_fqn: str) -> SchemaInfo:
    """Fetch the source schema's :class:`SchemaInfo` or raise.

    Args:
        client: Configured soyuz client.
        source_schema_fqn: ``catalog.schema``.

    Returns:
        The :class:`SchemaInfo` for the source schema.

    Raises:
        CatalogNotFoundError: Source schema unknown to soyuz.
    """
    response = _get_schema.sync(client=client, full_name=source_schema_fqn)
    if not isinstance(response, SchemaInfo):
        msg = f"source schema {source_schema_fqn!r} not found in soyuz-catalog"
        raise CatalogNotFoundError(msg)
    return response


def _resolve_storage_root(schema_info: SchemaInfo, schema_fqn: str) -> str:
    """Return the schema's ``storage_root`` (preferring ``storage_location``)."""
    for field in (schema_info.storage_location, schema_info.storage_root):
        if not isinstance(field, Unset) and field:
            return field
    msg = (
        f"schema {schema_fqn!r} has no storage_location or storage_root.  "
        f" branching requires a known storage root on the parent schema."
    )
    raise CatalogNotFoundError(msg)


def _list_source_tables(client: Client, catalog: str, schema: str) -> list[dict[str, Any]]:
    """Bypass the generated client and fetch full ``TableInfo`` payloads.

    The generated ``list_tables`` route returns lightweight
    ``identifiers`` per the spec, but soyuz returns full ``tables``
    bodies with ``columns`` and ``storage_location`` already
    populated — exactly what the branch primitive needs to
    reconstruct each table on the branch side without a follow-up
    ``get_table`` per row.

    Args:
        client: Configured soyuz client.
        catalog: Parent catalog.
        schema: Source schema.

    Returns:
        List of table-info dicts.
    """
    url = "/api/2.1/unity-catalog/tables"
    params = {"catalog_name": catalog, "schema_name": schema}
    http = client.get_httpx_client()
    resp = http.get(url, params=params)
    if resp.status_code != 200:
        return []
    data = resp.json()
    tables = data.get("tables", data.get("identifiers", []))
    if not isinstance(tables, list):
        return []
    return cast(list[dict[str, Any]], tables)


def _stats_from_action_row(row: dict[str, Any], column_names: list[str]) -> str:
    """Convert a flattened ``get_add_actions`` row into a Delta ``stats`` JSON.

    The Delta protocol's ``stats`` field is a JSON string with
    ``numRecords`` / ``minValues`` / ``maxValues`` / ``nullCount`` keys.
    The flattened representation prefixes each column with
    ``min.`` / ``max.`` / ``null_count.`` so we re-fold them here.

    Args:
        row: One pylist entry from
            ``DeltaTable.get_add_actions(flatten=True)``.
        column_names: Schema column order; preserved in the JSON for
            human-readable diffs.

    Returns:
        JSON string ready to pass into :class:`AddAction.stats`.
    """
    stats: dict[str, Any] = {"numRecords": int(row.get("num_records", 0))}
    min_values: dict[str, Any] = {}
    max_values: dict[str, Any] = {}
    null_count: dict[str, Any] = {}
    for col in column_names:
        if f"min.{col}" in row:
            min_values[col] = row[f"min.{col}"]
        if f"max.{col}" in row:
            max_values[col] = row[f"max.{col}"]
        if f"null_count.{col}" in row:
            null_count[col] = row[f"null_count.{col}"]
    if min_values:
        stats["minValues"] = min_values
    if max_values:
        stats["maxValues"] = max_values
    if null_count:
        stats["nullCount"] = null_count
    return json.dumps(stats, sort_keys=True, default=str)


def _clone_table_local_symlink(
    source_uri: str,
    branch_uri: str,
) -> int:
    """Build a symlinked Delta clone of *source_uri* at *branch_uri*.

    Returns the source's Delta version that the snapshot was taken
    from — recorded into ``parent_version_at_create`` for promotion-
    conflict detection.
    """
    return _clone_table_local(source_uri, branch_uri, mode="symlink")


def _clone_table_local_deep_copy(
    source_uri: str,
    branch_uri: str,
) -> int:
    """Deep-copy variant of :func:`_clone_table_local_symlink`.

    Behaves identically except parquet bytes are duplicated rather
    than symlinked.  Used for cloud-strategy testing on local FS.
    """
    return _clone_table_local(source_uri, branch_uri, mode="deep_copy")


def _clone_table_local(
    source_uri: str,
    branch_uri: str,
    *,
    mode: Literal["symlink", "deep_copy"],
) -> int:
    """Shared body of the two local-FS clone modes.

    Args:
        source_uri: Source-table URI (``file://`` or absolute path).
        branch_uri: Branch-table URI (``file://`` or absolute path).
        mode: ``"symlink"`` (zero-copy) or ``"deep_copy"`` (byte copy).

    Returns:
        Source's Delta version at the moment the snapshot was taken.
    """
    src_path = _uri_to_local_path(source_uri)
    branch_path = _uri_to_local_path(branch_uri)
    branch_path.mkdir(parents=True, exist_ok=True)

    src_dt = DeltaTable(str(src_path))
    source_version = int(src_dt.version())
    schema = src_dt.schema()
    column_names = [f.name for f in schema.fields]

    actions_table: Any = src_dt.get_add_actions(flatten=True)
    arrow_table: Any = pa.table(actions_table)  # pyright: ignore[reportUnknownMemberType]
    rows = cast(
        list[dict[str, Any]],
        arrow_table.to_pylist(),  # pyright: ignore[reportUnknownMemberType]
    )

    add_actions: list[AddAction] = []
    for row in rows:
        rel_path = str(row["path"])
        target_file: Path = branch_path / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        source_file: Path = src_path / rel_path
        if mode == "symlink":
            if target_file.exists() or target_file.is_symlink():
                target_file.unlink()
            target_file.symlink_to(source_file.resolve())
        else:
            shutil.copy2(str(source_file), str(target_file))
        add_actions.append(
            AddAction(
                path=rel_path,
                size=int(row["size_bytes"]),
                partition_values={},
                modification_time=int(row["modification_time"]),
                data_change=True,
                stats=_stats_from_action_row(row, column_names),
            )
        )

    DeltaTable.create(str(branch_path), schema=schema)
    branch_dt = DeltaTable(str(branch_path))
    if add_actions:
        branch_dt.create_write_transaction(
            actions=add_actions,
            mode="append",
            schema=schema,
        )
    return source_version


def create_branch_schema(
    *,
    client: Client,
    source_schema_fqn: str,
    branch_name: str,
    settings: Settings,
    strategy: Literal["auto", "symlink", "deep_copy"] = "auto",
    agent_run_id: str | None = None,
) -> str:
    """Create a Delta-branch of *source_schema_fqn* under *branch_name*.

    Two-part flow:

    1. Resolve the source schema, classify storage scheme, pick the
       cloning strategy, validate that *branch_name* doesn't already
       exist.
    2. Inside an :func:`operation_context` audit envelope, create the
       branch UC schema, clone every source table (symlink or deep
       copy depending on strategy), register the branch tables in
       UC, stamp the ``pointlessql.branch.*`` tag set on the branch
       schema, and emit the ``pointlessql.branch.created.v1`` CloudEvent.

    Args:
        client: Configured soyuz client.
        source_schema_fqn: ``catalog.schema`` of the parent.
        branch_name: Plain branch schema name (no dots).
        settings: Resolved :class:`Settings`; used for
            ``cloud_strategy`` and the CloudEvent factory.
        strategy: ``"auto"`` (pick from URI scheme + setting),
            ``"symlink"`` (force local-FS symlinks), or
            ``"deep_copy"`` (force byte-copy).  Per-call override of
            the global ``branch.cloud_strategy`` setting.
        agent_run_id: Active ``agent_runs.id``; ``None`` keeps the
            primitive silent on the audit trail.

    Returns:
        The created branch's two-part FQN ``catalog.branch_name``.

    Raises:
        BranchAlreadyExistsError: ``branch_name`` already exists.
        BranchOfBranchError: *source_schema_fqn* itself carries
            ``pointlessql.branch.*`` tags.
        BranchCloudUnsupportedError: Cloud parent + ``cloud_strategy='error'``
            (the default) and no per-call override.
        CatalogNotFoundError: Parent schema unknown / has no storage_root.
        CatalogUnavailableError: soyuz unreachable.
        ValueError: Unknown URI scheme on the parent's storage_root.
    """  # noqa: DOC502,DOC503 — Catalog* / Branch* propagate from helpers
    catalog, source_schema = _split_two_part(source_schema_fqn, "source_schema")
    if "." in branch_name or not branch_name:
        msg = f"branch_name {branch_name!r} must be a single name (no dots, non-empty)"
        raise ValueError(msg)
    branch_fqn = f"{catalog}.{branch_name}"

    try:
        existing = _get_schema.sync(client=client, full_name=branch_fqn)
    except UnexpectedStatus:
        existing = None
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(
            f"Cannot reach soyuz-catalog while resolving {branch_fqn!r}."
        ) from exc
    if isinstance(existing, SchemaInfo):
        msg = f"branch target {branch_fqn!r} already exists in soyuz-catalog"
        raise BranchAlreadyExistsError(msg)

    if branch_tags.read_branch_tags_sync(client, source_schema_fqn) is not None:
        msg = (
            f"source schema {source_schema_fqn!r} is itself a branch — "
            f"branch-of-branch is intentionally out of scope for v1.  "
            f"Promote or discard the inner branch first."
        )
        raise BranchOfBranchError(msg)

    source_info = _ensure_source_schema(client, source_schema_fqn)
    parent_storage_root = _resolve_storage_root(source_info, source_schema_fqn)
    scheme = _classify_storage_scheme(parent_storage_root)

    chosen_strategy = _pick_strategy(strategy, scheme, settings)

    branch_storage_root = _derive_branch_storage_root(parent_storage_root, branch_name)

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    parent_versions: dict[str, int] = {}
    table_count = 0

    with operation_context(
        factory,
        agent_run_id=agent_run_id,
        op_name="branch_create",
        params={
            "source_schema": source_schema_fqn,
            "branch_schema": branch_fqn,
            "strategy": chosen_strategy,
        },
        target_table=branch_fqn,
    ) as recorder:
        try:
            create_body = CreateSchema.from_dict(
                {
                    "catalog_name": catalog,
                    "name": branch_name,
                    "storage_root": branch_storage_root,
                }
            )
            _create_schema.sync(client=client, body=create_body)

            tables = _list_source_tables(client, catalog, source_schema)
            for table in tables:
                table_count += 1
                table_name = table.get("name")
                if not isinstance(table_name, str):
                    continue
                source_table_uri = table.get("storage_location") or (
                    f"{parent_storage_root.rstrip('/')}/{table_name}"
                )
                branch_table_uri = f"{branch_storage_root.rstrip('/')}/{table_name}"

                version_at_create = _clone_one_table(
                    source_uri=source_table_uri,
                    branch_uri=branch_table_uri,
                    strategy=chosen_strategy,
                )
                parent_versions[table_name] = version_at_create

                _register_branch_table(
                    client=client,
                    catalog=catalog,
                    branch_name=branch_name,
                    table=table,
                    branch_table_uri=branch_table_uri,
                )

            branch_tags.apply_branch_tags_sync(
                client,
                branch_fqn,
                parent_schema=source_schema_fqn,
                parent_version_at_create=parent_versions,
                created_by_run_id=agent_run_id,
                strategy=chosen_strategy,
            )

            recorder.extra_params.update(
                {
                    "table_count": table_count,
                    "parent_versions": parent_versions,
                    "branch_storage_root": branch_storage_root,
                }
            )
        except httpx.ConnectError as exc:
            raise CatalogUnavailableError(
                f"Cannot reach soyuz-catalog while creating branch {branch_fqn!r}."
            ) from exc

    _record_branch_audit_log(
        branch_schema_fqn=branch_fqn,
        parent_schema_fqn=source_schema_fqn,
        action="create",
        run_id=agent_run_id,
        payload={
            "strategy": chosen_strategy,
            "parent_versions": parent_versions,
            "branch_storage_root": branch_storage_root,
            "table_count": table_count,
        },
    )

    _emit_branch_created_event(
        settings=settings,
        parent_schema=source_schema_fqn,
        branch_schema=branch_fqn,
        run_id=agent_run_id,
        strategy=chosen_strategy,
        table_count=table_count,
    )

    return branch_fqn


def _pick_strategy(
    requested: Literal["auto", "symlink", "deep_copy"],
    scheme: Literal["local", "cloud"],
    settings: Settings,
) -> str:
    """Select the per-call clone strategy.

    ``"auto"`` resolves to ``"symlink"`` on local FS and to either
    ``"deep_copy"`` or :class:`BranchCloudUnsupportedError` on cloud
    storage, depending on ``settings.branch.cloud_strategy``.

    Args:
        requested: Caller's explicit pick or ``"auto"``.
        scheme: Storage classification.
        settings: Resolved :class:`Settings`.

    Returns:
        :data:`STRATEGY_SYMLINK` or :data:`STRATEGY_DEEP_COPY`.

    Raises:
        BranchCloudUnsupportedError: ``"auto"`` on cloud +
            ``cloud_strategy='error'``.
    """
    if requested == "symlink":
        return STRATEGY_SYMLINK
    if requested == "deep_copy":
        return STRATEGY_DEEP_COPY
    if scheme == "local":
        return STRATEGY_SYMLINK
    if settings.branch.cloud_strategy == "deep_copy":
        return STRATEGY_DEEP_COPY
    msg = (
        "cannot branch a cloud-stored schema with "
        "branch.cloud_strategy='error' (the default).  Either set "
        "POINTLESSQL_BRANCH_CLOUD_STRATEGY=deep_copy or pass "
        "strategy='deep_copy' on the call."
    )
    raise BranchCloudUnsupportedError(msg)


def _clone_one_table(
    *,
    source_uri: str,
    branch_uri: str,
    strategy: str,
) -> int:
    """Dispatch to the symlink or deep-copy local clone.

    Cloud-side ``deep_copy`` against true object storage is not yet
    wired ( ships local + local-deep-copy); a cloud
    deep-copy that goes via httpx + SigV4 is a  follow-up.
    For now any cloud-storage URI hits :func:`_uri_to_local_path`'s
    error path before reaching here.

    Args:
        source_uri: Source-table URI.
        branch_uri: Branch-table URI.
        strategy: Picked strategy.

    Returns:
        Source version at clone time.
    """
    if strategy == STRATEGY_SYMLINK:
        return _clone_table_local_symlink(source_uri, branch_uri)
    return _clone_table_local_deep_copy(source_uri, branch_uri)


def _register_branch_table(
    *,
    client: Client,
    catalog: str,
    branch_name: str,
    table: Mapping[str, Any],
    branch_table_uri: str,
) -> None:
    """Register one branch-side table in UC mirroring the source's schema.

    The branch table inherits ``columns``, ``data_source_format``,
    and ``table_type`` from the source row but points its
    ``storage_location`` at the branch's per-table URI.

    Args:
        client: soyuz client.
        catalog: Parent catalog.
        branch_name: Branch schema name (without catalog prefix).
        table: One entry from :func:`_list_source_tables`.
        branch_table_uri: Per-table storage URI under the branch root.
    """
    table_name = table.get("name")
    columns: list[Any] = list(table.get("columns") or [])
    body_dict: dict[str, Any] = {
        "catalog_name": catalog,
        "schema_name": branch_name,
        "name": table_name,
        "table_type": table.get("table_type", "MANAGED"),
        "data_source_format": table.get("data_source_format", "DELTA"),
        "columns": columns,
        "storage_location": branch_table_uri,
    }
    body = CreateTable.from_dict(body_dict)
    _create_table.sync(client=client, body=body)


def _emit_branch_event(
    *,
    settings: Settings,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Best-effort fire of one ``pointlessql.branch.*`` CloudEvent.

    Persists into ``governance_events`` and fans out to active sinks.
    Failures are swallowed so a flaky audit-stream cannot break a
    successful branch operation — :func:`emit_governance_event`
    already logs internally.  If no DB is bound (purely interactive
    PQL with no metadata DB) the event is silently dropped, mirroring
    :func:`emit_governance_event` semantics.

    Args:
        settings: Resolved :class:`Settings`.
        event_type: One of the ``pointlessql.branch.*`` event types
            registered in :mod:`pointlessql.services.governance_events`.
        data: Event payload dict (must JSON-serialise).
    """
    import asyncio

    from pointlessql.db import get_session_factory
    from pointlessql.services.governance_events import emit_governance_event

    try:
        factory = get_session_factory()
    except RuntimeError:
        return

    coro = emit_governance_event(
        event_type,
        data,
        settings=settings,
        session_factory=factory,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        # No running loop — fresh event loop drives the emission.
        try:
            asyncio.run(coro)
        except RuntimeError as exc:  # pragma: no cover — defensive
            logger.warning(
                "_emit_branch_event(%s): asyncio.run failed: %s",
                event_type,
                exc,
            )
        return
    # Running loop already (e.g. inside an async scheduler executor).
    # Fire-and-forget on the loop; emission errors are already logged
    # internally by emit_governance_event.
    loop.create_task(coro)


def _emit_branch_created_event(
    *,
    settings: Settings,
    parent_schema: str,
    branch_schema: str,
    run_id: str | None,
    strategy: str,
    table_count: int,
) -> None:
    """Fire the ``pointlessql.branch.created.v1`` CloudEvent.

    Args:
        settings: Resolved :class:`Settings`.
        parent_schema: Source schema FQN.
        branch_schema: Branch schema FQN.
        run_id: Active run id or ``None``.
        strategy: Picked clone strategy.
        table_count: Number of tables cloned.
    """
    from pointlessql.services.governance_events import EVENT_TYPE_BRANCH_CREATED

    _emit_branch_event(
        settings=settings,
        event_type=EVENT_TYPE_BRANCH_CREATED,
        data={
            "parent_schema": parent_schema,
            "branch_schema": branch_schema,
            "run_id": run_id,
            "strategy": strategy,
            "table_count": table_count,
        },
    )


def _record_branch_audit_log(
    *,
    branch_schema_fqn: str,
    parent_schema_fqn: str | None,
    action: str,
    run_id: str | None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one row to ``branch_audit_log``.

    Survives the discard of the underlying UC schema so auditors can
    reconstruct branch life-cycle weeks after the schema is gone.
    A no-op when the metadata DB isn't bound (interactive-only path).

    Args:
        branch_schema_fqn: ``catalog.schema`` of the branch.
        parent_schema_fqn: ``catalog.schema`` of the source, or
            ``None`` when unknown (legacy auto_cleanup rows).
        action: One of the values in
            :data:`pointlessql.models.BRANCH_ACTIONS`.
        run_id: Active run id or ``None``.
        payload: Free-form JSON-serialisable details.  Stored as a
            JSON string capped by convention at ~1 MiB.
    """
    import datetime

    from pointlessql.db import get_session_factory
    from pointlessql.models import BranchAuditLog

    try:
        factory = get_session_factory()
    except RuntimeError:
        return

    try:
        with factory() as session:
            row = BranchAuditLog(
                branch_schema_fqn=branch_schema_fqn,
                parent_schema_fqn=parent_schema_fqn,
                action=action,
                run_id=run_id,
                payload_json=json.dumps(payload, default=str) if payload else None,
                created_at=datetime.datetime.now(datetime.UTC),
            )
            session.add(row)
            session.commit()
    except Exception:  # noqa: BLE001 — audit-log failures must not break the op
        logger.exception(
            "_record_branch_audit_log: failed to persist row for action=%s branch=%s",
            action,
            branch_schema_fqn,
        )


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
    catalog, branch_name = _split_two_part(branch_schema_fqn, "branch_schema")

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
        msg = (
            f"cannot discard branch {branch_schema_fqn!r}: "
            f"status='promoted' (promotion is final)"
        )
        raise BranchInUseError(msg)
    if tags.status == STATUS_DISCARDED:
        logger.warning(
            "discard_branch_schema: %s already status='discarded' — no-op",
            branch_schema_fqn,
        )
        return

    storage_root = _resolve_storage_root(existing, branch_schema_fqn) if isinstance(
        existing, SchemaInfo
    ) else None

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    with operation_context(
        factory,
        agent_run_id=agent_run_id,
        op_name="branch_discard",
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

    _record_branch_audit_log(
        branch_schema_fqn=branch_schema_fqn,
        parent_schema_fqn=tags.parent_schema,
        action="discard",
        run_id=agent_run_id,
        payload={
            "strategy": tags.strategy,
            "parent_versions": tags.parent_version_at_create,
            "deleted_storage_root": storage_root,
        },
    )

    _emit_branch_event(
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

    catalog, schema = _split_two_part(parent_schema_fqn, "parent_schema")
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


def _rename_schema(client: Client, full_name: str, new_name: str) -> None:
    """Rename a UC schema in place via the generated PATCH route.

    Wraps :func:`_update_schema.sync` with the ``new_name`` patch
    body.  The schema's ``storage_root`` is *not* touched — UC
    pointer-swap is the whole point of .

    Args:
        client: soyuz client.
        full_name: Current ``catalog.schema``.
        new_name: New schema name (without catalog prefix).
    """
    body = UpdateSchema.from_dict({"new_name": new_name})
    _update_schema.sync(full_name=full_name, client=client, body=body)


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

    catalog, branch_name = _split_two_part(branch_schema_fqn, "branch_schema")

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
    _, parent_name = _split_two_part(parent_fqn, "parent_schema")
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
        agent_run_id=agent_run_id,
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
            _rename_schema(client, parent_fqn, backup_name)
            try:
                _rename_schema(client, branch_schema_fqn, parent_name)
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
                    _rename_schema(client, backup_fqn, parent_name)
                except Exception:
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

    _record_branch_audit_log(
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

    _emit_branch_event(
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
    catalog, schema = _split_two_part(tags.parent_schema, "parent_schema")
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
    scheme = _classify_storage_scheme(storage_root)
    if scheme == "cloud":
        msg = (
            f"cloud-storage discard not implemented in v1 (storage_root={storage_root!r}); "
            f"this is a  follow-up"
        )
        raise ValueError(msg)
    branch_path = _uri_to_local_path(storage_root)
    if branch_path.exists():
        shutil.rmtree(branch_path)
