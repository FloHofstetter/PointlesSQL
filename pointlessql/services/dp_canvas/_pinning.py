"""Pin / unpin a saved canvas version as the live production revision.

The visual editor's "Versions ▾" dropdown lets a steward (or admin)
mark one stored ``data_product_canvas_graph`` row per product as
``is_production = TRUE``.  The flag is enforced as "at most one
production version per product" by a partial unique index in the
``data_product_canvas_graph`` table; the helpers below preserve that
invariant in application code so concurrent pin attempts surface as
a friendly :class:`ValidationError` rather than a raw integrity error.

``pin_version`` is transactional: it first clears any existing pinned
row for the product, then flips the target row.  ``unpin_version`` is
a single-row update.  Both helpers emit an :data:`AuditLog` row via
``log_action`` so the change shows up in the audit cockpit.

Reads (``get_pinned_version``) skip the audit hop — pin lookups happen
on every editor open + materialise pre-flight and must stay cheap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update

from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import DataProductCanvasGraph
from pointlessql.services.audit import log_action

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def get_pinned_version(
    session: Session, *, dp_id: int
) -> int | None:
    """Return the version-int of the pinned row for *dp_id*, else ``None``."""
    row = session.execute(
        select(DataProductCanvasGraph.version)
        .where(DataProductCanvasGraph.data_product_id == dp_id)
        .where(DataProductCanvasGraph.is_production.is_(True))
    ).scalar_one_or_none()
    return row


def pin_version(
    factory: sessionmaker[Session],
    *,
    dp_id: int,
    version: int,
    actor_user_id: int,
    actor_user_email: str,
    workspace_id: int,
    client_ip: str | None = None,
) -> None:
    """Pin *version* of canvas *dp_id* as the production revision.

    Idempotent at the row level: if *version* is already pinned the
    helper still writes an audit row (the steward intentionally
    re-pinned, which is a real user action) but the SQL is a no-op.
    """
    with factory() as session:
        target = session.execute(
            select(DataProductCanvasGraph)
            .where(DataProductCanvasGraph.data_product_id == dp_id)
            .where(DataProductCanvasGraph.version == version)
        ).scalar_one_or_none()
        if target is None:
            raise ResourceNotFoundError(
                f"canvas version dp={dp_id} v={version} not found"
            )
        session.execute(
            update(DataProductCanvasGraph)
            .where(DataProductCanvasGraph.data_product_id == dp_id)
            .where(DataProductCanvasGraph.is_production.is_(True))
            .where(DataProductCanvasGraph.version != version)
            .values(is_production=False)
        )
        session.execute(
            update(DataProductCanvasGraph)
            .where(DataProductCanvasGraph.id == target.id)
            .values(is_production=True)
        )
        session.commit()

    log_action(
        factory,
        user_id=actor_user_id,
        user_email=actor_user_email,
        action="canvas_pin",
        target=f"data_product_canvas_graph:{dp_id}:v{version}",
        detail={"dp_id": dp_id, "version": version},
        workspace_id=workspace_id,
        client_ip=client_ip,
    )


def unpin_version(
    factory: sessionmaker[Session],
    *,
    dp_id: int,
    version: int,
    actor_user_id: int,
    actor_user_email: str,
    workspace_id: int,
    client_ip: str | None = None,
) -> None:
    """Clear the production flag on *version* of canvas *dp_id*.

    Silently no-ops when *version* was not pinned in the first place
    (so re-running an "unpin" button after a manual SQL repair stays
    idempotent).  Always emits an audit row when called via the route
    layer so the intent is recorded even when the data was already in
    the desired shape.
    """
    with factory() as session:
        target = session.execute(
            select(DataProductCanvasGraph)
            .where(DataProductCanvasGraph.data_product_id == dp_id)
            .where(DataProductCanvasGraph.version == version)
        ).scalar_one_or_none()
        if target is None:
            raise ResourceNotFoundError(
                f"canvas version dp={dp_id} v={version} not found"
            )
        session.execute(
            update(DataProductCanvasGraph)
            .where(DataProductCanvasGraph.id == target.id)
            .where(DataProductCanvasGraph.is_production.is_(True))
            .values(is_production=False)
        )
        session.commit()

    log_action(
        factory,
        user_id=actor_user_id,
        user_email=actor_user_email,
        action="canvas_unpin",
        target=f"data_product_canvas_graph:{dp_id}:v{version}",
        detail={"dp_id": dp_id, "version": version},
        workspace_id=workspace_id,
        client_ip=client_ip,
    )


__all__ = [
    "get_pinned_version",
    "pin_version",
    "unpin_version",
]
