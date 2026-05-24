"""Get-or-create resolver for :class:`SocialTarget` (Phase 77.0).

The resolver is the single chokepoint that every social write
route uses to translate an ``(workspace_id, entity_kind,
entity_ref)`` triple into a ``social_targets.id`` value.  Race-
safe via dialect-specific upsert: PG uses
``INSERT … ON CONFLICT DO NOTHING`` + a second SELECT;
SQLite goes the same route via ``INSERT OR IGNORE``.  Both
fall back to ``SELECT FOR UPDATE`` semantics implicitly because
the unique constraint ``uq_social_targets_entity`` is the
serialisation point.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._social_target import (
    ENTITY_KINDS,
    SocialTarget,
)

logger = logging.getLogger(__name__)


def get_or_create_target(
    session: Session,
    *,
    workspace_id: int,
    kind: str,
    ref: str,
    data_product_id: int | None = None,
) -> SocialTarget:
    """Return the anchor row for ``(workspace_id, kind, ref)``.

    Args:
        session: Active SQLAlchemy session.  The caller owns
            the transaction; this function flushes but does
            not commit.
        workspace_id: Tenant scope.
        kind: Discriminator from :data:`ENTITY_KINDS`.
        ref: Opaque reference string for the entity within
            its kind.  See
            :mod:`pointlessql.models.social._social_target`
            for the shape contract per kind.
        data_product_id: Required when ``kind='dp'``, must be
            ``None`` for every other kind.  Mirrors the CHECK
            constraint ``ck_social_targets_dp_backref`` so the
            caller gets a clear Python error before the DB
            rejects it.

    Returns:
        The existing or freshly-inserted :class:`SocialTarget`.

    Raises:
        ValueError: If ``kind`` is not in :data:`ENTITY_KINDS`,
            or if the ``kind/data_product_id`` parity is wrong.
    """
    if kind not in ENTITY_KINDS:
        msg = f"unknown entity_kind: {kind!r}"
        raise ValueError(msg)
    if kind == "dp" and data_product_id is None:
        msg = "kind='dp' requires a data_product_id back-pointer"
        raise ValueError(msg)
    if kind != "dp" and data_product_id is not None:
        msg = (
            f"kind={kind!r} must not carry a data_product_id "
            "(only kind='dp' rows do)"
        )
        raise ValueError(msg)

    existing = session.execute(
        select(SocialTarget).where(
            SocialTarget.workspace_id == workspace_id,
            SocialTarget.entity_kind == kind,
            SocialTarget.entity_ref == ref,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    target = SocialTarget(
        workspace_id=workspace_id,
        entity_kind=kind,
        entity_ref=ref,
        data_product_id=data_product_id,
    )
    session.add(target)
    try:
        session.flush()
    except IntegrityError:
        # Lost the insert race.  Roll back the savepoint and
        # re-read — the unique constraint guarantees one row.
        session.rollback()
        winner = session.execute(
            select(SocialTarget).where(
                SocialTarget.workspace_id == workspace_id,
                SocialTarget.entity_kind == kind,
                SocialTarget.entity_ref == ref,
            )
        ).scalar_one()
        return winner
    return target


def resolve_dp_target(
    session: Session,
    *,
    workspace_id: int,
    catalog_name: str,
    schema_name: str,
) -> SocialTarget:
    """Resolve a DP target via legacy `(workspace_id, catalog, schema)` lookup.

    Looks up the :class:`DataProduct` row for
    ``(workspace_id, catalog_name, schema_name)`` and then calls
    :func:`get_or_create_target` with ``kind='dp'``.

    Args:
        session: Active SQLAlchemy session.
        workspace_id: Tenant scope.
        catalog_name: UC catalog name.
        schema_name: UC schema name.

    Returns:
        The anchor row for the DP.

    Raises:
        LookupError: If no DP row exists at the requested
            ``(catalog_name, schema_name)`` in the workspace.
    """
    dp = session.execute(
        select(DataProduct).where(
            DataProduct.workspace_id == workspace_id,
            DataProduct.catalog_name == catalog_name,
            DataProduct.schema_name == schema_name,
        )
    ).scalar_one_or_none()
    if dp is None:
        msg = (
            f"no DataProduct at {catalog_name}.{schema_name} "
            f"in workspace {workspace_id}"
        )
        raise LookupError(msg)
    return get_or_create_target(
        session,
        workspace_id=workspace_id,
        kind="dp",
        ref=f"{catalog_name}.{schema_name}",
        data_product_id=int(dp.id),
    )


def resolve_workspace_for_entity(
    session_factory: Any,
    kind: str,
    ref: str,
) -> int | None:
    """Probe which workspace owns a given entity.

    For ``kind='dp'`` this is straightforward — the DP carries
    its own ``workspace_id``.  For other kinds the resolver is
    intentionally minimal in Phase 77.0; each later sub-phase
    extends this when it registers its kind (e.g. tables resolve
    via the workspace's pinned-catalog set in 77.1).

    Args:
        session_factory: SQLAlchemy session factory.
        kind: Discriminator.
        ref: Entity reference.

    Returns:
        The owning ``workspaces.id`` or ``None`` if the entity
        cannot be unambiguously placed.  Callers fall back to
        the request's current workspace when ``None``.
    """
    if kind == "dp":
        parts = ref.split(".", 1)
        if len(parts) != 2:
            return None
        catalog_name, schema_name = parts
        with session_factory() as session:
            row = session.execute(
                select(DataProduct.workspace_id).where(
                    DataProduct.catalog_name == catalog_name,
                    DataProduct.schema_name == schema_name,
                )
            ).first()
            if row is None:
                return None
            return int(row[0])
    if kind == "catalog":
        return _workspace_for_catalog(session_factory, ref)
    if kind == "schema":
        parts = ref.split(".", 1)
        if len(parts) != 2 or not all(parts):
            return None
        return _workspace_for_catalog(session_factory, parts[0])
    if kind == "notebook_cell":
        return _workspace_for_notebook_cell(session_factory, ref)
    # Other kinds register their resolver in later sub-phases;
    # until then return None so callers fall back to the request's
    # current workspace.
    return None


def _workspace_for_notebook_cell(
    session_factory: Any, entity_ref: str
) -> int | None:
    """Probe the workspace owning a ``"{notebook_uuid}:{cell_uuid}"`` ref.

    Phase 95 — notebook-cell social anchors join through the parent
    notebook's ``workspace_id``.  The cell-uuid half is unique on its
    own but the cheap probe is via ``notebooks.id`` (already indexed).

    Args:
        session_factory: SQLAlchemy session factory.
        entity_ref: Composite ``{notebook_uuid}:{cell_uuid}`` string.

    Returns:
        The notebook's ``workspace_id`` or ``None`` when the ref is
        malformed or no notebook exists for the given UUID.
    """
    if not entity_ref or ":" not in entity_ref:
        return None
    notebook_uuid, _, cell_uuid = entity_ref.partition(":")
    if not notebook_uuid or not cell_uuid:
        return None
    from pointlessql.models.notebook import Notebook

    with session_factory() as session:
        row = session.execute(
            select(Notebook.workspace_id).where(Notebook.id == notebook_uuid)
        ).first()
        if row is None:
            return None
        return int(row[0])


def _workspace_for_catalog(
    session_factory: Any, catalog_name: str
) -> int | None:
    """Probe ``workspace_catalog_pins`` for the workspace owning *catalog_name*.

    Args:
        session_factory: SQLAlchemy session factory.
        catalog_name: UC catalog name (one ASCII identifier).

    Returns:
        The pinned workspace id, or ``None`` when no workspace has
        the catalog pinned.  Phase 77.5 factored this out of the
        ``kind='table'`` path so schemas + catalogs share the same
        probe.
    """
    if not catalog_name:
        return None
    # Imported lazily to avoid the heavy workspace module on the
    # social hot-path when no resolver is needed.
    from pointlessql.models.workspace import WorkspaceCatalogPin

    with session_factory() as session:
        row = session.execute(
            select(WorkspaceCatalogPin.workspace_id).where(
                WorkspaceCatalogPin.catalog_name == catalog_name,
            )
        ).first()
        if row is None:
            return None
        return int(row[0])


__all__: list[str] = [
    "get_or_create_target",
    "resolve_dp_target",
    "resolve_workspace_for_entity",
]
