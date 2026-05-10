"""Branch-creation workflow.

Owns :func:`create_branch_schema` plus the table-cloning helpers and the
``pointlessql.branch.created.v1`` CloudEvent.

Hybrid storage strategy:

* Local filesystem (``file://`` or absolute path): symlink each parquet
  inside the branch's storage prefix, then synth a Delta log
  referencing the symlinks by relative path.  Zero parquet bytes copied.
* Object storage: no symlink primitive — operator must opt into
  ``deep_copy`` via the ``branch.cloud_strategy`` setting, otherwise
  raises :class:`BranchCloudUnsupportedError`.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import pyarrow as pa
from deltalake import DeltaTable
from deltalake.transaction import AddAction
from soyuz_catalog_client import Client
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_schema import CreateSchema
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.schema_info import SchemaInfo

from pointlessql.config import Settings
from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.pql._branch_errors import (
    BranchAlreadyExistsError,
    BranchCloudUnsupportedError,
    BranchOfBranchError,
)
from pointlessql.pql.branch._common import (
    _create_schema,
    _create_table,
    _get_schema,
    branch_tags,
    classify_storage_scheme,
    derive_branch_storage_root,
    emit_branch_event,
    ensure_source_schema,
    record_branch_audit_log,
    resolve_storage_root,
    split_two_part,
    uri_to_local_path,
)
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.branch_tags import (
    STRATEGY_DEEP_COPY,
    STRATEGY_SYMLINK,
)
from pointlessql.types import BranchAction, OpName, RunId


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


def _clone_table_local_symlink(source_uri: str, branch_uri: str) -> int:
    """Build a symlinked Delta clone of *source_uri* at *branch_uri*.

    Returns the source's Delta version that the snapshot was taken
    from — recorded into ``parent_version_at_create`` for promotion-
    conflict detection.
    """
    return _clone_table_local(source_uri, branch_uri, mode="symlink")


def _clone_table_local_deep_copy(source_uri: str, branch_uri: str) -> int:
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
    src_path = uri_to_local_path(source_uri)
    branch_path = uri_to_local_path(branch_uri)
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
    catalog, source_schema = split_two_part(source_schema_fqn, "source_schema")
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

    source_info = ensure_source_schema(client, source_schema_fqn)
    parent_storage_root = resolve_storage_root(source_info, source_schema_fqn)
    scheme = classify_storage_scheme(parent_storage_root)

    chosen_strategy = _pick_strategy(strategy, scheme, settings)

    branch_storage_root = derive_branch_storage_root(parent_storage_root, branch_name)

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    parent_versions: dict[str, int] = {}
    table_count = 0

    with operation_context(
        factory,
        agent_run_id=cast(RunId | None, agent_run_id),
        op_name=OpName.BRANCH_CREATE,
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

    record_branch_audit_log(
        branch_schema_fqn=branch_fqn,
        parent_schema_fqn=source_schema_fqn,
        action=BranchAction.CREATE,
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


def _clone_one_table(*, source_uri: str, branch_uri: str, strategy: str) -> int:
    """Dispatch to the symlink or deep-copy local clone.

    Cloud-side ``deep_copy`` against true object storage is not yet
    wired (ships local + local-deep-copy); a cloud
    deep-copy that goes via httpx + SigV4 is a follow-up.
    For now any cloud-storage URI hits :func:`uri_to_local_path`'s
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
    """Fire the ``pointlessql.branch.created.v1`` CloudEvent.

    Args:
        settings: Resolved :class:`Settings`.
        parent_schema: Source schema FQN.
        branch_schema: Branch schema FQN.
        run_id: Active run id or ``None``.
        strategy: Picked clone strategy.
        table_count: Number of tables cloned.
    """
    from pointlessql.services.workspace.governance import EVENT_TYPE_BRANCH_CREATED

    emit_branch_event(
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
