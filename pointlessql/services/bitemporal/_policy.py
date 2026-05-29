"""Effective bitemporal policy = product override ⇐ workspace defaults.

Mirrors the governance-policy inheritance pattern: each field on
:class:`pointlessql.models.DataProductBitemporalPolicy` is nullable;
when ``None`` it inherits the workspace-level
:class:`pointlessql.config.BitemporalSettings`.  The resolver returns
a frozen dataclass so the write path can branch on a single typed
value rather than passing around a settings handle + an optional
ORM row.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.config import BitemporalSettings
from pointlessql.models import DataProductBitemporalPolicy


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


@dataclasses.dataclass(frozen=True)
class EffectiveBitemporal:
    """Resolved bitemporal policy ready to be applied to a write.

    Attributes:
        enforcement: ``off`` / ``opt_in`` / ``required``.
        inject_processing_time: Whether the write path should stamp
            the processing-time column.  Derived from
            *enforcement*: ``off`` → False, ``opt_in`` →
            settings flag, ``required`` → True.
        processing_time_column: Standard column name.
        event_time_column: Standard column name.
        require_event_time: Whether the write path must validate
            event-time presence + dtype before write.
        enforcement_source: ``'product'`` or ``'workspace'`` — which
            source supplied :attr:`enforcement`.
    """

    enforcement: str
    inject_processing_time: bool
    processing_time_column: str
    event_time_column: str
    require_event_time: bool
    enforcement_source: str


def _read_override(
    factory: _SessionFactory, data_product_id: int | None
) -> DataProductBitemporalPolicy | None:
    if data_product_id is None:
        return None
    with factory() as session:
        return session.scalar(
            select(DataProductBitemporalPolicy).where(
                DataProductBitemporalPolicy.data_product_id == data_product_id
            )
        )


def effective_policy(
    factory: _SessionFactory,
    *,
    settings: BitemporalSettings,
    data_product_id: int | None,
) -> EffectiveBitemporal:
    """Resolve the effective bitemporal policy for one product.

    Args:
        factory: Sessionmaker callable.
        settings: Workspace-level :class:`BitemporalSettings`.
        data_product_id: Product id to look up the override for; pass
            ``None`` to bypass override lookup (returns the workspace
            policy verbatim).

    Returns:
        :class:`EffectiveBitemporal` with the resolved per-product
        view.
    """
    override = _read_override(factory, data_product_id)
    if override is not None and override.enforcement is not None:
        enforcement = override.enforcement
        enforcement_source = "product"
    else:
        enforcement = settings.enforcement
        enforcement_source = "workspace"

    if enforcement == "required":
        do_inject = True
    elif enforcement == "off":
        do_inject = False
    else:
        do_inject = settings.inject_processing_time

    processing_col = (
        override.processing_time_column
        if override is not None and override.processing_time_column
        else settings.processing_time_column
    )
    event_col = (
        override.event_time_column
        if override is not None and override.event_time_column
        else settings.event_time_column
    )
    if override is not None and override.require_event_time is not None:
        require_evt = bool(override.require_event_time)
    else:
        require_evt = bool(settings.require_event_time)

    return EffectiveBitemporal(
        enforcement=enforcement,
        inject_processing_time=do_inject,
        processing_time_column=processing_col,
        event_time_column=event_col,
        require_event_time=require_evt,
        enforcement_source=enforcement_source,
    )


def set_product_policy(
    factory: _SessionFactory,
    *,
    data_product_id: int,
    fields: dict[str, Any],
    updated_by_user_id: int | None = None,
) -> DataProductBitemporalPolicy:
    """Upsert the product's bitemporal override row.

    Args:
        factory: Sessionmaker callable.
        data_product_id: Product to set the override on.
        fields: Mapping of nullable override values.  Accepted keys:
            ``enforcement``, ``processing_time_column``,
            ``event_time_column``, ``require_event_time``.  Pass
            ``None`` to clear back to "inherit".
        updated_by_user_id: Audit trail.

    Returns:
        The detached, updated row.

    Raises:
        ValueError: When ``enforcement`` is set to an invalid value.
    """
    now = datetime.datetime.now(datetime.UTC)
    enforcement = fields.get("enforcement", "_missing")
    if enforcement not in (None, "_missing") and enforcement not in (
        "off",
        "opt_in",
        "required",
    ):
        raise ValueError(
            f"enforcement {enforcement!r} not in ('off','opt_in','required')"
        )
    with factory() as session:
        row = session.scalar(
            select(DataProductBitemporalPolicy).where(
                DataProductBitemporalPolicy.data_product_id == data_product_id
            )
        )
        if row is None:
            row = DataProductBitemporalPolicy(
                data_product_id=data_product_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        if "enforcement" in fields:
            row.enforcement = fields["enforcement"]
        if "processing_time_column" in fields:
            row.processing_time_column = (
                str(fields["processing_time_column"]).strip() or None
                if fields["processing_time_column"]
                else None
            )
        if "event_time_column" in fields:
            row.event_time_column = (
                str(fields["event_time_column"]).strip() or None
                if fields["event_time_column"]
                else None
            )
        if "require_event_time" in fields:
            row.require_event_time = (
                None if fields["require_event_time"] is None
                else bool(fields["require_event_time"])
            )
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = now
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row
