"""Lifecycle transition driver + history reader.

The transition driver is the only writer to ``data_products.lifecycle_*``
columns outside of the initial INSERT (which always stamps
``'active'`` via the column default).  It runs the state-machine guard
in :mod:`._transitions` and stamps the audit log so the history view
can reassemble the full lifecycle timeline of a product.

The history view replays
:class:`pointlessql.models.AuditLog` rows targeted at
``data_product:{catalog}.{schema}`` with the lifecycle action — there is
no separate per-product history table because the audit log is already
the authoritative event store.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import AuditLog, DataProduct
from pointlessql.services.lifecycle._transitions import (
    LifecycleTransitionError,
    assert_transition,
)

#: Audit-log ``action`` written by :func:`transition` on every state change.
LIFECYCLE_CHANGED_ACTION = "data_product.lifecycle_changed"

#: Audit-log ``action`` written by :func:`propose_transition` when an
#: agent proposes a transition that a steward must approve.
LIFECYCLE_PROPOSED_ACTION = "data_product.lifecycle_proposed"


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


@dataclasses.dataclass(frozen=True)
class LifecycleHistoryEntry:
    """One row of the product's lifecycle timeline.

    Attributes:
        from_state: The state the product was in before the transition,
            or ``None`` for the original ``draft`` / insert-time row
            (when the audit log does not carry the prior state).
        to_state: The state the product moved to.
        actor_user_id: The user who drove the transition (``None`` for
            system-initiated rows).
        actor_email: Email snapshot from the audit-log row.
        proposed: ``True`` for proposed-by-agent rows that have not yet
            been executed.
        replacement_uri: URN of the successor when ``to_state ==
            'retired'`` and a replacement was named; ``None`` otherwise.
        note: Free-form note the actor attached, or empty string.
        created_at: Wall-clock the transition was recorded.
    """

    from_state: str | None
    to_state: str
    actor_user_id: int | None
    actor_email: str
    proposed: bool
    replacement_uri: str | None
    note: str
    created_at: datetime.datetime


def read_state(factory: _SessionFactory, *, data_product_id: int) -> str | None:
    """Return the product's current ``lifecycle_state``, or ``None`` if missing."""
    with factory() as session:
        product = session.get(DataProduct, data_product_id)
        if product is None:
            return None
        return product.lifecycle_state


def transition(
    factory: _SessionFactory,
    *,
    data_product_id: int,
    target: str,
    actor_user_id: int | None,
    replacement_data_product_id: int | None = None,
    note: str = "",
) -> DataProduct:
    """Move a product from its current state to *target*.

    Args:
        factory: Sessionmaker callable.
        data_product_id: PK of the product to transition.
        target: Target state from :data:`LIFECYCLE_STATES`.
        actor_user_id: User driving the transition; stamped onto
            ``lifecycle_changed_by_user_id``.
        replacement_data_product_id: When *target* is ``'retired'``,
            the optional successor product whose URN consumers can
            follow.  Ignored for other targets.
        note: Ignored at the service layer; the caller (route)
            stores it in the audit-log ``detail`` payload.

    Returns:
        The detached, updated :class:`DataProduct` row.

    Raises:
        LifecycleTransitionError: When *target* is not reachable from
            the current state or the product does not exist.
    """
    del note  # forwarded to the route layer for audit-detail; unused here.

    with factory() as session:
        product = session.get(DataProduct, data_product_id)
        if product is None:
            raise LifecycleTransitionError(
                f"data product id={data_product_id} not found"
            )
        assert_transition(product.lifecycle_state, target)
        if replacement_data_product_id is not None and target != "retired":
            raise LifecycleTransitionError(
                "replacement_data_product_id is only valid when retiring"
            )
        if replacement_data_product_id is not None:
            successor = session.get(DataProduct, replacement_data_product_id)
            if successor is None:
                raise LifecycleTransitionError(
                    f"replacement product id={replacement_data_product_id} not found"
                )
            if successor.workspace_id != product.workspace_id:
                raise LifecycleTransitionError(
                    "replacement product must live in the same workspace"
                )

        product.lifecycle_state = target
        product.lifecycle_changed_at = datetime.datetime.now(datetime.UTC)
        product.lifecycle_changed_by_user_id = actor_user_id
        if target == "retired":
            product.replacement_data_product_id = replacement_data_product_id
        elif target == "active":
            # Restoring from archived clears any lingering successor pointer.
            product.replacement_data_product_id = None
        session.commit()
        session.refresh(product)
        session.expunge(product)
        return product


def propose_transition(
    factory: _SessionFactory,
    *,
    data_product_id: int,
    target: str,
    actor_user_id: int | None,
    note: str = "",
) -> str:
    """Validate a proposed transition without applying it.

    Used by the agent-side plugin tool — agents may *suggest* a
    lifecycle move, but the actual write is steward/admin only.  Raises
    :class:`LifecycleTransitionError` if the move would be rejected so
    an agent gets the same up-front feedback a human would.

    Args:
        factory: Sessionmaker callable.
        data_product_id: PK of the product to propose against.
        target: Target state from :data:`LIFECYCLE_STATES`.
        actor_user_id: The proposing user (typically the agent's
            principal).  Currently unused at the service layer; the
            route stamps it into the audit log.
        note: Free-form rationale; surfaced in the audit-log detail.

    Returns:
        The product's current state — handy so a caller can show
        "proposed deprecated (currently active)" without a second
        round-trip.

    Raises:
        LifecycleTransitionError: When *target* would be rejected by
            :func:`assert_transition` or the product does not exist.
    """
    del actor_user_id, note  # forwarded to the route layer for audit-detail.
    with factory() as session:
        product = session.get(DataProduct, data_product_id)
        if product is None:
            raise LifecycleTransitionError(
                f"data product id={data_product_id} not found"
            )
        assert_transition(product.lifecycle_state, target)
        return product.lifecycle_state


def list_history(
    factory: _SessionFactory,
    *,
    workspace_id: int,
    catalog: str,
    schema: str,
    limit: int = 50,
) -> list[LifecycleHistoryEntry]:
    """Replay the lifecycle timeline for one product from the audit log.

    Reads :class:`AuditLog` rows targeted at
    ``data_product:{catalog}.{schema}`` with one of the lifecycle
    actions and returns them newest-first.

    Args:
        factory: Sessionmaker callable.
        workspace_id: Workspace scope for the audit query.
        catalog: UC catalog of the product.
        schema: UC schema of the product.
        limit: Cap the number of returned entries.

    Returns:
        List of :class:`LifecycleHistoryEntry` instances, newest first.
    """
    target = f"data_product:{catalog}.{schema}"
    actions = (LIFECYCLE_CHANGED_ACTION, LIFECYCLE_PROPOSED_ACTION)
    with factory() as session:
        rows = list(
            session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.workspace_id == workspace_id,
                    AuditLog.target == target,
                    AuditLog.action.in_(actions),
                )
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            ).all()
        )
    history: list[LifecycleHistoryEntry] = []
    for row in rows:
        try:
            detail = json.loads(row.detail) if row.detail else {}
        except (TypeError, ValueError):
            detail = {}
        history.append(
            LifecycleHistoryEntry(
                from_state=detail.get("from_state"),
                to_state=str(detail.get("to_state") or ""),
                actor_user_id=row.user_id if row.user_id else None,
                actor_email=row.user_email or "",
                proposed=row.action == LIFECYCLE_PROPOSED_ACTION,
                replacement_uri=detail.get("replacement_uri"),
                note=str(detail.get("note") or ""),
                created_at=row.created_at,
            )
        )
    return history
