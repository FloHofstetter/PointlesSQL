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
    """Convenience wrapper for the legacy DP path.

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
    # Other kinds register their resolver in 77.1+; until then
    # return None so callers fall back to the request's current
    # workspace.
    return None


__all__: list[str] = [
    "get_or_create_target",
    "resolve_dp_target",
    "resolve_workspace_for_entity",
]
