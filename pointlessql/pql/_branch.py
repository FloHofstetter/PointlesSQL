"""Helpers for the Phase 16.5 Delta-branching primitives.

Implements ``pql.branch`` (Sprint 16.5.2), ``pql.branch_discard``
(Sprint 16.5.3), and ``pql.branch_promote`` (Sprint 16.5.4) on top
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
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_schema import CreateSchema
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.pql._branch_errors import (
    BranchAlreadyExistsError,
    BranchCloudUnsupportedError,
    BranchOfBranchError,
)
from pointlessql.services import branch_tags
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.branch_tags import (
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
        f"Phase 16.5 branching requires a known storage root on the parent schema."
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
    wired (Sprint 16.5.2 ships local + local-deep-copy); a cloud
    deep-copy that goes via httpx + SigV4 is a Phase-16.5 follow-up.
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


def _emit_branch_created_event(
    *,
    settings: Settings,
    parent_schema: str,
    branch_schema: str,
    run_id: str | None,
    strategy: str,
    table_count: int,
) -> None:
    """Best-effort fire of the ``pointlessql.branch.created.v1`` CloudEvent.

    Persists into ``governance_events`` and fans out to active sinks.
    Failures are swallowed so a flaky audit-stream cannot break a
    successful branch creation — :func:`emit_governance_event`
    already logs internally.

    Args:
        settings: Resolved :class:`Settings`.
        parent_schema: Source schema FQN.
        branch_schema: Branch schema FQN.
        run_id: Active run id or ``None``.
        strategy: Picked clone strategy.
        table_count: Number of tables cloned.
    """
    import asyncio

    from pointlessql.db import get_session_factory
    from pointlessql.services.governance_events import (
        EVENT_TYPE_BRANCH_CREATED,
        emit_governance_event,
    )

    try:
        factory = get_session_factory()
    except RuntimeError:
        # No DB bound — interactive-only path; CloudEvent is silently
        # dropped to mirror :func:`emit_governance_event` semantics.
        return

    try:
        asyncio.run(
            emit_governance_event(
                EVENT_TYPE_BRANCH_CREATED,
                {
                    "parent_schema": parent_schema,
                    "branch_schema": branch_schema,
                    "run_id": run_id,
                    "strategy": strategy,
                    "table_count": table_count,
                },
                settings=settings,
                session_factory=factory,
            )
        )
    except RuntimeError as exc:  # pragma: no cover — defensive
        logger.warning("emit_branch_created_event: asyncio.run failed: %s", exc)
