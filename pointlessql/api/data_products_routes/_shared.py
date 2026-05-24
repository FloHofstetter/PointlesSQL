"""Shared helpers used across the data_products_routes sub-modules.

The listing / detail / diff / lineage / reload sub-modules — and
the upcoming Phase-71 comment / review / follow / readme handlers —
all need a way to serialise a :class:`DataProduct` ORM row and to
look up one product (plus its parsed pydantic contract + steward)
by ``(workspace_id, catalog, schema)``.  Centralising those tiny
helpers here keeps the import graph one-way: every sub-module
depends on ``_shared``, and ``_shared`` depends on nothing else
inside the package.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from pointlessql.data_products import DataProductContract
from pointlessql.data_products._diff import ContractDiffResult
from pointlessql.exceptions import AuthorizationError, ResourceNotFoundError
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.types._user_types import UserInfo


def serialise_product(
    row: DataProduct,
    *,
    steward_email: str | None,
    steward_display_name: str | None,
) -> dict[str, Any]:
    """Render one ``DataProduct`` cache row as a JSON-friendly dict.

    Used by both the listing and detail handlers so the wire format
    stays consistent.

    Args:
        row: The persisted data-product row.
        steward_email: Pre-resolved steward email, or ``None`` when
            the row's ``steward_user_id`` is NULL.
        steward_display_name: Pre-resolved steward display name.

    Returns:
        Dict ready for ``jsonable_encoder`` / FastAPI response.
    """
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "catalog": row.catalog_name,
        "schema": row.schema_name,
        "ref": f"{row.catalog_name}.{row.schema_name}",
        "version": row.version,
        "description": row.description,
        "sla_minutes": row.sla_minutes,
        "steward": {
            "user_id": row.steward_user_id,
            "email": steward_email,
            "display_name": steward_display_name,
        },
        "contract_yaml_hash": row.contract_yaml_hash,
        "last_loaded_at": row.last_loaded_at.isoformat(),
        "last_alerted_at": (
            row.last_alerted_at.isoformat() if row.last_alerted_at else None
        ),
    }


def load_one(
    session_factory: Any,
    workspace_id: int,
    catalog: str,
    schema: str,
) -> tuple[DataProduct, DataProductContract, str | None, str | None]:
    """Look up the product + parsed contract; raise 404 when missing.

    Args:
        session_factory: SQLAlchemy session factory from app state.
        workspace_id: Active workspace id resolved from the request.
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        Tuple of ``(row, contract, steward_email, steward_display)``.

    Raises:
        ResourceNotFoundError: When no product matches the
            ``(workspace_id, catalog, schema)`` tuple.
    """
    with session_factory() as session:
        row = session.execute(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        ).scalar_one_or_none()
        if row is None:
            raise ResourceNotFoundError(
                f"data product {catalog}.{schema!r} not found"
            )
        contract = DataProductContract.model_validate(json.loads(row.contract_json))
        if row.steward_user_id is not None:
            user = session.get(User, row.steward_user_id)
            steward_email = user.email if user else None
            steward_display = user.display_name if user else None
        else:
            steward_email = None
            steward_display = None
        return row, contract, steward_email, steward_display


def diff_to_payload(
    table_name: str, diff: ContractDiffResult | str
) -> dict[str, Any]:
    """Render a diff result (or error string) as a JSON-friendly dict."""
    if isinstance(diff, str):
        return {"name": table_name, "error": diff}
    return {"name": table_name, **diff.as_dict()}


def resolve_agent_for_principal(
    session_factory: Any,
    *,
    workspace_id: int,
    slug: str,
    user: UserInfo,
) -> int:
    """Resolve an ``?as_agent=<slug>`` token to an :class:`Agent` PK.

    Authorisation rule (Phase 76.5+): only the agent's
    ``principal_user_id`` (or install-admin) may speak as the
    agent.  Anyone else gets an :class:`AuthorizationError`.

    Args:
        session_factory: SQLAlchemy sessionmaker from app state.
        workspace_id: Active workspace id resolved from the request.
        slug: Agent slug straight from the query string.  Trimmed
            and lower-cased before lookup.
        user: Decoded session :class:`UserInfo` typed-dict.

    Returns:
        The persisted agent id ready to write into
        ``author_agent_id`` / ``applied_by_agent_id``.

    Raises:
        HTTPException: 404 when the slug doesn't resolve.
        AuthorizationError: When the caller is neither the agent's
            ``principal_user_id`` nor install-admin.
    """
    agent_slug = slug.strip().lower()
    with session_factory() as session:
        agent = session.execute(
            select(Agent).where(
                Agent.workspace_id == workspace_id, Agent.slug == agent_slug
            )
        ).scalar_one_or_none()
        if agent is None:
            # Phase 121.1.i — enrich the 404 with the workspace's
            # known agent slugs so callers can self-correct typos.
            known = list(
                session.execute(
                    select(Agent.slug).where(Agent.workspace_id == workspace_id)
                ).scalars()
            )
            raise ResourceNotFoundError.not_found(
                what=f"agent slug {agent_slug!r}",
                alternatives=known,
            )
        is_principal = agent.principal_user_id == user["id"]
        is_admin = bool(user["is_admin"])
        if not (is_principal or is_admin):
            raise AuthorizationError(
                principal=user["email"],
                privilege="post_as_agent",
                securable_type="agent",
                full_name=agent_slug,
            )
        return int(agent.id)
