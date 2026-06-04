"""Domain CRUD + product-assignment + transformation-binding primitives.

The functions here are the single write path for the domain ownership
layer — the admin CRUD routes, the browse API, and the data-product
assignment endpoint all go through them so validation (slug shape,
archetype / role membership, same-workspace assignment) lives in one
place rather than being re-implemented per route.

Every function takes a ``session_factory`` and returns detached ORM
rows (``session.expunge``) so callers can serialise them after the
session closes, matching the convention in
:mod:`pointlessql.services.workspace._crud`.
"""

from __future__ import annotations

import datetime
import re

from sqlalchemy import select

from pointlessql.models import (
    DOMAIN_ARCHETYPES,
    DOMAIN_MEMBER_ROLES,
    DP_TRANSFORMATION_KINDS,
    DataProduct,
    DataProductTransformation,
    Domain,
    DomainMember,
    Notebook,
)
from pointlessql.types import SessionFactory

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z0-9]$")



def _validate_slug(slug: str) -> str:
    """Return *slug* lowered + trimmed, or raise on shape violation.

    Domain slugs share the workspace-slug grammar so they are safe to
    drop into ``/domains/{slug}`` URLs and agent tool arguments
    without escaping.

    Args:
        slug: Caller-supplied domain slug.

    Returns:
        The cleaned slug (lower-cased, trimmed).

    Raises:
        ValueError: When the slug is empty, longer than 64 chars, or
            contains characters outside ``[a-z0-9_-]`` / starts / ends
            with a separator.
    """
    cleaned = slug.strip().lower()
    if not cleaned or len(cleaned) > 64:
        raise ValueError("domain slug must be 1..64 chars")
    if not _SLUG_RE.match(cleaned):
        raise ValueError(
            f"domain slug {cleaned!r} must match [a-z0-9_-] and not start/end with - or _"
        )
    return cleaned


def create_domain(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    slug: str,
    name: str,
    archetype: str,
    description: str | None = None,
    creator_user_id: int | None = None,
) -> Domain:
    """Insert a new :class:`Domain` + an owner membership for the creator.

    The creator (when given) is auto-added as a domain ``owner`` so the
    person who created the domain immediately has manage rights without
    a second call.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Owning workspace.
        slug: URL-safe identifier; see :func:`_validate_slug`.
        name: Human-readable label (max 200 chars).
        archetype: One of :data:`DOMAIN_ARCHETYPES`.
        description: Optional free-form note.
        creator_user_id: User who created the domain; auto-added as
            ``owner`` when set.

    Returns:
        The detached :class:`Domain` row.

    Raises:
        ValueError: On bad slug / name / archetype, or a slug already
            taken in the workspace.
    """
    cleaned_slug = _validate_slug(slug)
    cleaned_name = name.strip()
    if not cleaned_name or len(cleaned_name) > 200:
        raise ValueError("domain name must be 1..200 chars")
    if archetype not in DOMAIN_ARCHETYPES:
        raise ValueError(f"archetype {archetype!r} not in {DOMAIN_ARCHETYPES}")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        existing = session.scalar(
            select(Domain).where(
                Domain.workspace_id == workspace_id,
                Domain.slug == cleaned_slug,
            )
        )
        if existing is not None:
            raise ValueError(f"domain slug {cleaned_slug!r} already exists in this workspace")
        row = Domain(
            workspace_id=workspace_id,
            slug=cleaned_slug,
            name=cleaned_name,
            description=description.strip() if description else None,
            archetype=archetype,
            created_at=now,
        )
        session.add(row)
        session.flush()
        if creator_user_id is not None:
            session.add(
                DomainMember(
                    domain_id=row.id,
                    user_id=creator_user_id,
                    role="owner",
                    created_at=now,
                )
            )
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_domains(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    include_archived: bool = False,
) -> list[Domain]:
    """Return the workspace's domains ordered by name.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Workspace whose domains to list.
        include_archived: When ``True`` archived domains are included.

    Returns:
        Detached :class:`Domain` rows ordered by ``name`` ascending.
    """
    with session_factory() as session:
        stmt = select(Domain).where(Domain.workspace_id == workspace_id)
        if not include_archived:
            stmt = stmt.where(Domain.archived_at.is_(None))
        rows = list(session.scalars(stmt.order_by(Domain.name.asc())).all())
        for row in rows:
            session.expunge(row)
        return rows


def get_domain(session_factory: SessionFactory, *, domain_id: int) -> Domain | None:
    """Return the domain with *domain_id* or ``None``."""
    with session_factory() as session:
        row = session.get(Domain, domain_id)
        if row is not None:
            session.expunge(row)
        return row


def get_domain_by_slug(
    session_factory: SessionFactory, *, workspace_id: int, slug: str
) -> Domain | None:
    """Return the workspace domain with *slug* or ``None``."""
    cleaned = slug.strip().lower()
    with session_factory() as session:
        row = session.scalar(
            select(Domain).where(
                Domain.workspace_id == workspace_id,
                Domain.slug == cleaned,
            )
        )
        if row is not None:
            session.expunge(row)
        return row


def add_member(
    session_factory: SessionFactory,
    *,
    domain_id: int,
    user_id: int,
    role: str = "owner",
) -> DomainMember:
    """Grant *user_id* membership of *domain_id* with *role*.

    Idempotent: re-adding the same user updates the existing row's
    role in place rather than raising on the unique constraint.

    Args:
        session_factory: Sessionmaker callable.
        domain_id: FK to :class:`Domain`.
        user_id: FK to :class:`User`.
        role: One of :data:`DOMAIN_MEMBER_ROLES`.

    Returns:
        The detached :class:`DomainMember` row.

    Raises:
        ValueError: When *role* is not in :data:`DOMAIN_MEMBER_ROLES`.
    """
    if role not in DOMAIN_MEMBER_ROLES:
        raise ValueError(f"domain role {role!r} not in {DOMAIN_MEMBER_ROLES}")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        existing = session.scalar(
            select(DomainMember).where(
                DomainMember.domain_id == domain_id,
                DomainMember.user_id == user_id,
            )
        )
        if existing is not None:
            if existing.role != role:
                existing.role = role
                session.commit()
                session.refresh(existing)
            session.expunge(existing)
            return existing
        row = DomainMember(
            domain_id=domain_id,
            user_id=user_id,
            role=role,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def remove_member(session_factory: SessionFactory, *, domain_id: int, user_id: int) -> bool:
    """Remove a user from a domain.

    Returns:
        ``True`` when a membership row was deleted, ``False`` when
        none existed.
    """
    with session_factory() as session:
        member = session.scalar(
            select(DomainMember).where(
                DomainMember.domain_id == domain_id,
                DomainMember.user_id == user_id,
            )
        )
        if member is None:
            return False
        session.delete(member)
        session.commit()
        return True


def list_members(session_factory: SessionFactory, *, domain_id: int) -> list[DomainMember]:
    """Return every member of *domain_id* ordered by role then id."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DomainMember)
                .where(DomainMember.domain_id == domain_id)
                .order_by(DomainMember.role.asc(), DomainMember.id.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def assign_product_domain(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    data_product_id: int,
    domain_id: int | None,
) -> DataProduct:
    """Set (or clear) a data product's owning domain.

    Passing ``domain_id=None`` unassigns the product.  The product and
    the domain must live in the same workspace — cross-workspace
    assignment is rejected so a domain never owns a product outside its
    tenant boundary.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Active workspace.
        data_product_id: Product to (re)assign.
        domain_id: Target domain, or ``None`` to unassign.

    Returns:
        The detached, updated :class:`DataProduct` row.

    Raises:
        ValueError: When the product / domain does not exist in the
            workspace.
    """
    with session_factory() as session:
        product = session.scalar(
            select(DataProduct).where(
                DataProduct.id == data_product_id,
                DataProduct.workspace_id == workspace_id,
            )
        )
        if product is None:
            raise ValueError(f"data product id={data_product_id} not found in this workspace")
        if domain_id is not None:
            domain = session.scalar(
                select(Domain).where(
                    Domain.id == domain_id,
                    Domain.workspace_id == workspace_id,
                )
            )
            if domain is None:
                raise ValueError(f"domain id={domain_id} not found in this workspace")
        product.domain_id = domain_id
        session.commit()
        session.refresh(product)
        session.expunge(product)
        return product


def list_products_for_domain(
    session_factory: SessionFactory, *, domain_id: int
) -> list[DataProduct]:
    """Return every data product assigned to *domain_id*."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProduct)
                .where(DataProduct.domain_id == domain_id)
                .order_by(DataProduct.catalog_name.asc(), DataProduct.schema_name.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def bind_transformation(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    kind: str,
    notebook_id: str | None = None,
    dbt_model_name: str | None = None,
    created_by_user_id: int | None = None,
) -> DataProductTransformation:
    """Bind a notebook or dbt model to a data product.

    Exactly one of ``notebook_id`` / ``dbt_model_name`` must match the
    declared ``kind``.  Re-binding the same target is idempotent — the
    existing row is returned rather than creating a duplicate.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the transformation produces.
        kind: One of :data:`DP_TRANSFORMATION_KINDS`.
        notebook_id: ``notebooks.id`` when ``kind == 'notebook'``.
        dbt_model_name: dbt model name when ``kind == 'dbt_model'``.
        created_by_user_id: User who created the binding.

    Returns:
        The detached :class:`DataProductTransformation` row.

    Raises:
        ValueError: On bad kind, a missing/extra target for the kind,
            an unknown product, or (for notebooks) an unknown notebook.
    """
    if kind not in DP_TRANSFORMATION_KINDS:
        raise ValueError(f"transformation kind {kind!r} not in {DP_TRANSFORMATION_KINDS}")
    if kind == "notebook":
        if not notebook_id or dbt_model_name:
            raise ValueError("kind 'notebook' requires notebook_id and no dbt_model_name")
    else:
        cleaned_dbt = (dbt_model_name or "").strip()
        if not cleaned_dbt or notebook_id:
            raise ValueError("kind 'dbt_model' requires dbt_model_name and no notebook_id")
        dbt_model_name = cleaned_dbt
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        product = session.get(DataProduct, data_product_id)
        if product is None:
            raise ValueError(f"data product id={data_product_id} not found")
        if kind == "notebook":
            nb = session.get(Notebook, notebook_id)
            if nb is None:
                raise ValueError(f"notebook id={notebook_id!r} not found")
        existing = session.scalar(
            select(DataProductTransformation).where(
                DataProductTransformation.data_product_id == data_product_id,
                DataProductTransformation.kind == kind,
                DataProductTransformation.notebook_id == notebook_id,
                DataProductTransformation.dbt_model_name == dbt_model_name,
            )
        )
        if existing is not None:
            session.expunge(existing)
            return existing
        row = DataProductTransformation(
            data_product_id=data_product_id,
            kind=kind,
            notebook_id=notebook_id,
            dbt_model_name=dbt_model_name,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def unbind_transformation(
    session_factory: SessionFactory, *, data_product_id: int, transformation_id: int
) -> bool:
    """Remove a transformation binding from a product.

    Returns:
        ``True`` when a row was deleted, ``False`` when no matching
        binding existed for the product.
    """
    with session_factory() as session:
        row = session.scalar(
            select(DataProductTransformation).where(
                DataProductTransformation.id == transformation_id,
                DataProductTransformation.data_product_id == data_product_id,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_transformations(
    session_factory: SessionFactory, *, data_product_id: int
) -> list[DataProductTransformation]:
    """Return every transformation bound to *data_product_id*."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductTransformation)
                .where(DataProductTransformation.data_product_id == data_product_id)
                .order_by(DataProductTransformation.id.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows
