"""Shared helpers and soyuz-API references for the branch primitives.

Holds:

* Soyuz API module references (``_get_schema``, ``_get_table``, ...)
  that the per-workflow modules and the tests patch.
* Storage-URI classification + path-derivation utilities.
* Schema lookup helpers (``ensure_source_schema`` / ``resolve_storage_root``).
* Audit-log + CloudEvent emission used by all three workflows.

Anything narrower lives next to the workflow that owns it
(``_create``, ``_discard``, ``_promote``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

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
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.types import Unset

from pointlessql.config import Settings
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.services import branch_tags
from pointlessql.types import BranchAction

logger = logging.getLogger(__name__)

CLOUD_SCHEMES = frozenset({"s3", "gs", "gcs", "abfss", "abfs", "wasbs", "wasb", "az"})
LOCAL_SCHEMES = frozenset({"file", ""})

__all__ = [
    "CLOUD_SCHEMES",
    "LOCAL_SCHEMES",
    "classify_storage_scheme",
    "_create_schema",
    "_create_table",
    "derive_branch_storage_root",
    "emit_branch_event",
    "ensure_source_schema",
    "_get_schema",
    "_get_table",
    "record_branch_audit_log",
    "rename_schema",
    "resolve_storage_root",
    "split_two_part",
    "_update_schema",
    "uri_to_local_path",
    "branch_tags",
    "logger",
]


def classify_storage_scheme(storage_uri: str) -> Literal["local", "cloud"]:
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


def uri_to_local_path(storage_uri: str) -> Path:
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
        msg = f"uri_to_local_path called on non-local URI {storage_uri!r}"
        raise ValueError(msg)
    if scheme == "file":
        return Path(unquote(parsed.path))
    return Path(storage_uri)


def derive_branch_storage_root(parent_storage_root: str, branch_name: str) -> str:
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


def split_two_part(name: str, kind: str) -> tuple[str, str]:
    """Split a ``catalog.schema`` two-part name; raise on malformed input."""
    parts = name.split(".")
    if len(parts) != 2 or not all(parts):
        msg = f"{kind} {name!r} must be a two-part 'catalog.schema' name"
        raise ValueError(msg)
    return parts[0], parts[1]


def ensure_source_schema(client: Client, source_schema_fqn: str) -> SchemaInfo:
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


def resolve_storage_root(schema_info: SchemaInfo, schema_fqn: str) -> str:
    """Return the schema's ``storage_root`` (preferring ``storage_location``)."""
    for field in (schema_info.storage_location, schema_info.storage_root):
        if not isinstance(field, Unset) and field:
            return field
    msg = (
        f"schema {schema_fqn!r} has no storage_location or storage_root.  "
        f" branching requires a known storage root on the parent schema."
    )
    raise CatalogNotFoundError(msg)


def rename_schema(client: Client, full_name: str, new_name: str) -> None:
    """Rename a UC schema in place via the generated PATCH route.

    Wraps :func:`_update_schema.sync` with the ``new_name`` patch
    body.  The schema's ``storage_root`` is *not* touched — UC
    pointer-swap is the whole point of promotion.

    Args:
        client: soyuz client.
        full_name: Current ``catalog.schema``.
        new_name: New schema name (without catalog prefix).
    """
    from soyuz_catalog_client.models.update_schema import UpdateSchema

    body = UpdateSchema.from_dict({"new_name": new_name})
    _update_schema.sync(full_name=full_name, client=client, body=body)


def emit_branch_event(
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
            registered in :mod:`pointlessql.services.workspace.governance`.
        data: Event payload dict (must JSON-serialise).
    """
    import asyncio

    from pointlessql.db import get_session_factory
    from pointlessql.services.workspace.governance import emit_governance_event

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
        try:
            asyncio.run(coro)
        except RuntimeError as exc:  # pragma: no cover — defensive
            logger.warning(
                "emit_branch_event(%s): asyncio.run failed: %s",
                event_type,
                exc,
            )
        return
    loop.create_task(coro)


def record_branch_audit_log(
    *,
    branch_schema_fqn: str,
    parent_schema_fqn: str | None,
    action: BranchAction,
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
            "record_branch_audit_log: failed to persist row for action=%s branch=%s",
            action,
            branch_schema_fqn,
        )
