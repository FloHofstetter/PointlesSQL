"""Declared-consumption verdict for product-bound reads (D2).

Resolves whether a read of ``catalog.schema.table`` from the context of
a *consuming* data product is permitted by the consumer's declared
input-ports.  The three modes ``off`` / ``advisory`` / ``strict`` follow
the platform's "honest split" — the default is ``advisory`` so an
upgrade never blocks an existing workflow; a steward flips to
``strict`` per-product (or per-workspace) once the inputs are
documented.

This module never *reads* the data — it only returns a verdict the
route layer acts on (audit-only in ``advisory``, HTTP 403 in
``strict``).  Identity-time checks (who is the caller, what is the
authoring product) live at the route hooks, mirroring the same
masking-at-the-port pattern the PII layer uses.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from sqlalchemy import select

from pointlessql.exceptions import PermissionDeniedError
from pointlessql.models import DataProductInputPort
from pointlessql.types import SessionFactory

#: Audit-log action emitted when an ``advisory`` verdict allows an
#: undeclared read.  Picked up by the Governance tab's "Recent
#: undeclared consumption" card.
CONSUMPTION_UNDECLARED_ACTION = "consumption.undeclared"

#: Audit-log action emitted when a ``strict`` verdict blocks a read.
CONSUMPTION_BLOCKED_ACTION = "consumption.blocked"


class ConsumptionVerdict(enum.StrEnum):
    """Three-way outcome of :func:`evaluate_consumption`."""

    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


@dataclasses.dataclass(frozen=True)
class ConsumptionDecision:
    """Result of a consumption check.

    Attributes:
        verdict: The three-way outcome.
        mode: The effective enforcement mode (``off`` / ``advisory`` /
            ``strict``) at the time of the check.
        consumer_product_id: Echoes the calling product, for audit.
        source_fqn: The source the consumer tried to read,
            ``catalog.schema.table`` form.
        declared: ``True`` if ``source_fqn`` matched a declared
            upstream-product input-port of the consumer.
        reason: Free-form rationale; surfaced into the audit detail
            payload when the verdict is ``WARN`` or ``BLOCK``.
    """

    verdict: ConsumptionVerdict
    mode: str
    consumer_product_id: int
    source_fqn: str
    declared: bool
    reason: str


class ConsumptionViolation(PermissionDeniedError):
    """Raised when a ``strict`` verdict blocks a route-layer read.

    Inherits from :class:`PermissionDeniedError` so the centralised
    FastAPI exception handler renders the block as a 403 with the
    structured decision surfaced through
    :meth:`extension_members`.
    """

    def __init__(self, decision: ConsumptionDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision

    def extension_members(self) -> dict[str, Any] | None:
        """Surface the structured consumption decision on the 403 envelope."""
        return {
            "mode": self.decision.mode,
            "consumer_product_id": self.decision.consumer_product_id,
            "source": self.decision.source_fqn,
            "declared": self.decision.declared,
        }



def _normalise_source(source_fqn: str) -> tuple[str, str, str | None]:
    """Split ``catalog.schema[.table]`` into a tuple.

    Returns ``(catalog, schema, table_or_none)``.
    """
    parts = source_fqn.split(".")
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) >= 3:
        return parts[0], parts[1], ".".join(parts[2:])
    raise ValueError(
        f"source_fqn {source_fqn!r} must be catalog.schema or catalog.schema.table"
    )


def _is_declared_upstream(
    factory: SessionFactory,
    *,
    consumer_product_id: int,
    source_catalog: str,
    source_schema: str,
) -> bool:
    """Return ``True`` when the consumer declares the source as an input-port.

    Match is on ``catalog.schema`` (table segment ignored).
    """
    expected = f"{source_catalog}.{source_schema}"
    with factory() as session:
        match = session.scalar(
            select(DataProductInputPort).where(
                DataProductInputPort.data_product_id == consumer_product_id,
                DataProductInputPort.kind == "upstream_product",
                DataProductInputPort.source_ref == expected,
            )
        )
    return match is not None


def evaluate_consumption(
    factory: SessionFactory,
    *,
    mode: str,
    consumer_product_id: int,
    source_fqn: str,
) -> ConsumptionDecision:
    """Return the verdict for one declared-vs-undeclared read.

    Args:
        factory: Sessionmaker callable.
        mode: Effective enforcement mode of the consumer
            (typically the value returned by
            :func:`pointlessql.services.governance.get_effective_policy`
            for ``consumption_enforcement``).
        consumer_product_id: PK of the product the read is happening
            "in the context of" — the *consumer*.
        source_fqn: The source being read, ``catalog.schema`` or
            ``catalog.schema.table`` form (the table segment is ignored
            for the declared-upstream check because input-ports are
            schema-grained).

    Returns:
        :class:`ConsumptionDecision` with the verdict + provenance.
    """
    source_catalog, source_schema, _ = _normalise_source(source_fqn)
    declared = _is_declared_upstream(
        factory,
        consumer_product_id=consumer_product_id,
        source_catalog=source_catalog,
        source_schema=source_schema,
    )
    if declared or mode == "off":
        return ConsumptionDecision(
            verdict=ConsumptionVerdict.ALLOW,
            mode=mode,
            consumer_product_id=consumer_product_id,
            source_fqn=source_fqn,
            declared=declared,
            reason="declared" if declared else "enforcement off",
        )
    if mode == "advisory":
        return ConsumptionDecision(
            verdict=ConsumptionVerdict.WARN,
            mode=mode,
            consumer_product_id=consumer_product_id,
            source_fqn=source_fqn,
            declared=False,
            reason=f"{source_catalog}.{source_schema} is not a declared input-port",
        )
    return ConsumptionDecision(
        verdict=ConsumptionVerdict.BLOCK,
        mode=mode,
        consumer_product_id=consumer_product_id,
        source_fqn=source_fqn,
        declared=False,
        reason=f"{source_catalog}.{source_schema} is not a declared input-port",
    )


def assert_declared_consumption(
    factory: SessionFactory,
    *,
    mode: str,
    consumer_product_id: int,
    source_fqn: str,
) -> ConsumptionDecision:
    """Like :func:`evaluate_consumption`, but raise on ``BLOCK``.

    Returns the decision so the caller can still emit an audit row in
    ``WARN`` mode.

    Raises:
        ConsumptionViolation: When the resolved verdict is
            :data:`ConsumptionVerdict.BLOCK`.
    """
    decision = evaluate_consumption(
        factory,
        mode=mode,
        consumer_product_id=consumer_product_id,
        source_fqn=source_fqn,
    )
    if decision.verdict is ConsumptionVerdict.BLOCK:
        raise ConsumptionViolation(decision)
    return decision


def emit_consumption_audit(
    factory: SessionFactory,
    *,
    decision: ConsumptionDecision,
    user_id: int,
    user_email: str,
    actor_role: str = "user",
    workspace_id: int = 1,
    client_ip: str | None = None,
) -> None:
    """Write an audit row for a non-``ALLOW`` consumption verdict.

    No-op for :data:`ConsumptionVerdict.ALLOW` — declared reads are
    silent.  ``WARN`` and ``BLOCK`` both produce a row; the action
    constant distinguishes them so the Governance tab's "Recent
    Undeclared Consumption" card can list advisory drift separately
    from strict refusals.

    Args:
        factory: Sessionmaker callable.
        decision: The verdict returned by
            :func:`evaluate_consumption` or
            :func:`assert_declared_consumption`.
        user_id: Acting user id (0 for system / background).
        user_email: Acting user email snapshot.
        actor_role: ``user`` / ``admin`` / ``system``.
        workspace_id: Workspace the read happened in.
        client_ip: Optional client IP for the audit row.
    """
    from pointlessql.services.audit import log_action

    if decision.verdict is ConsumptionVerdict.ALLOW:
        return
    action = (
        CONSUMPTION_BLOCKED_ACTION
        if decision.verdict is ConsumptionVerdict.BLOCK
        else CONSUMPTION_UNDECLARED_ACTION
    )
    log_action(
        factory,
        user_id,
        user_email,
        action,
        f"data_product:{decision.consumer_product_id}",
        detail={
            "mode": decision.mode,
            "source": decision.source_fqn,
            "declared": decision.declared,
            "reason": decision.reason,
        },
        actor_role=actor_role,
        client_ip=client_ip,
        workspace_id=workspace_id,
    )
