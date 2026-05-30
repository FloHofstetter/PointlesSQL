"""Write-time enforcement of the breaking-change policy.

The enforcer compares the schema the writer is presenting against the
currently-registered schema for the matching output port; if the diff
classifies as ``major`` and the policy mode says ``block`` the call
raises :class:`SchemaBreakingChangeError` (a subclass of
:class:`PermissionDeniedError` mapped to HTTP 403).

The enforcer is intentionally idempotent on the no-op path so it can
be wired into :mod:`pql._hooks` ``before_write`` without slowing the
hot path.  When no port maps to the target table or no prior schema
exists, the enforcer returns immediately with a ``none`` outcome.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.exceptions import PermissionDeniedError
from pointlessql.models import DataProductOutputPort
from pointlessql.services.schema_versioning._diff import (
    SchemaDiff,
    compute_diff,
)


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


class SchemaBreakingChangeError(PermissionDeniedError):
    """Raised when a write would introduce a MAJOR-class change.

    Mirrors the shape of :class:`Iso8601Violation` from phase 136 —
    a :class:`PermissionDeniedError` subclass so the FastAPI handler
    returns 403 with a structured envelope.
    """

    def __init__(self, *, port_name: str, version: str, diff: SchemaDiff) -> None:
        detail = (
            f"breaking schema change on port {port_name} at version {version}: "
            f"removed={diff.columns_removed}, narrowed={diff.columns_type_changed}, "
            f"tightened={diff.columns_nullable_tightened}"
        )
        super().__init__(detail=detail)
        self.port_name = port_name
        self.version = version
        self.diff = diff


@dataclasses.dataclass(slots=True, frozen=True)
class EnforcementOutcome:
    """Outcome of one :func:`assert_schema_compatibility` call.

    Attributes:
        mode: Active policy mode (``block`` / ``warn`` / ``off``).
        diff: Classified diff between previous + presented schema.
        version: The currently-registered semver on the port.
        port_name: The port's name for surfacing in warnings.
    """

    mode: str
    diff: SchemaDiff
    version: str
    port_name: str


def assert_schema_compatibility(
    session_factory: _SessionFactory,
    *,
    data_product_id: int,
    table_name: str | None,
    new_schema: dict[str, Any],
    mode: str = "warn",
) -> EnforcementOutcome | None:
    """Resolve the matching port and enforce the policy.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the write targets.
        table_name: Optional table name; used to pick the right port
            when the product has multiple.  When ``None`` the
            enforcer picks the first registered port (sufficient for
            the common single-port-per-product shape).
        new_schema: The schema dict the writer is presenting.
        mode: One of ``block`` / ``warn`` / ``off``.  ``off`` returns
            without doing any work; ``warn`` records the diff but
            does not raise; ``block`` raises on a MAJOR diff.

    Returns:
        :class:`EnforcementOutcome` for the surface to render; or
        ``None`` when no matching port exists.

    Raises:
        SchemaBreakingChangeError: In ``block`` mode on a MAJOR diff.
    """
    if mode == "off":
        return None
    with session_factory() as session:
        port = session.scalar(
            select(DataProductOutputPort)
            .where(DataProductOutputPort.data_product_id == data_product_id)
            .order_by(DataProductOutputPort.id)
        )
        if port is None:
            return None
        from pointlessql.services.schema_versioning._crud import current_schema

        prior = current_schema(
            session_factory, output_port_id=int(port.id)
        )
        version = str(port.version_semver or "0.1.0")
        port_name = str(port.name)
    diff = compute_diff(prior, new_schema)
    outcome = EnforcementOutcome(
        mode=mode, diff=diff, version=version, port_name=port_name
    )
    if mode == "block" and diff.is_breaking():
        raise SchemaBreakingChangeError(
            port_name=port_name, version=version, diff=diff
        )
    return outcome


def serialise_schema(schema: dict[str, Any]) -> str:
    """Return a deterministic JSON encoding of *schema* for storage."""
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))
