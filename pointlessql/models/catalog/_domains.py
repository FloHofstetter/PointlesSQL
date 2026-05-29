"""Domain ownership entities — the federated-ownership foundation.

Three tables that give data products an addressable *owner* beyond a
single steward user:

* ``domains`` — one row per business domain inside a workspace.  A
  domain carries an *archetype* (source-aligned / aggregate /
  consumer-aligned) that classifies its orientation; products inherit
  that orientation from the domain they belong to.  Soft-archived via
  ``archived_at`` (mirrors :class:`Workspace`) so historical
  references always resolve.
* ``domain_members`` — M:M junction between users and domains, each
  membership carrying a ``role`` (owner = responsibility, developer =
  build).  Mirrors :class:`WorkspaceMember`'s shape so a domain can
  list many owners + developers without elevating anyone to a
  tenant-wide admin.
* ``data_product_transformations`` — binds the *code* that produces a
  product (a notebook, or a dbt model named by string) to the product
  itself, so "this product = this transformation + this output" is a
  first-class link rather than a naming convention.

Storage decision: PointlesSQL metadata DB.  Domains reference the
existing soyuz UC schema only indirectly — a data product (already
keyed on ``(workspace, catalog, schema)``) gains a nullable
``domain_id`` rather than the domain pointing at UC.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

#: Allowed values for :attr:`Domain.archetype`.  The three orientations
#: come straight from Dehghani's domain taxonomy; stored as a plain
#: ``String`` (matching the schema's enum-via-tuple convention) so a
#: future archetype addition doesn't force a native-enum migration.
DOMAIN_ARCHETYPES: tuple[str, ...] = (
    "source-aligned",
    "aggregate",
    "consumer-aligned",
)

#: Allowed values for :attr:`DomainMember.role`.  ``owner`` carries
#: responsibility / sign-off; ``developer`` builds the products.
DOMAIN_MEMBER_ROLES: tuple[str, ...] = ("owner", "developer")

#: Allowed values for :attr:`DataProductTransformation.kind`.
#: ``notebook`` points at a persisted ``notebooks`` row; ``dbt_model``
#: names a dbt model by string because dbt models are not persisted as
#: their own entity (they live in the data team's project files).
DP_TRANSFORMATION_KINDS: tuple[str, ...] = ("notebook", "dbt_model")


class Domain(Base):
    """One business domain inside a workspace.

    A domain is the addressable owner that "Federated" governance
    needs — products, contracts, and (later) policies hang off a
    domain rather than a single steward user.  The ``archetype``
    classifies the domain's orientation and drives a discovery
    filter + a UI badge.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this domain belongs to.  FK on
            ``workspaces.id``; ``server_default='1'`` so a fresh
            single-tenant install adopts the seeded default
            workspace without a data migration.
        slug: URL-safe identifier, unique per workspace.  Used in
            ``/domains/{slug}`` and as the stable handle agents pass
            when assigning a product.
        name: Human-readable label (e.g. "Sales").
        description: Free-form one-paragraph note (nullable).
        archetype: One of :data:`DOMAIN_ARCHETYPES`.
        created_at: Wall-clock when the domain was created.
        archived_at: Wall-clock when an admin archived the domain;
            ``None`` for active domains.  Archived domains drop out
            of listings but keep their rows so product references
            still resolve.
    """

    __tablename__ = "domains"

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_domains_ws_slug"),
        Index("ix_domains_workspace", "workspace_id"),
        CheckConstraint(
            "archetype IN ('source-aligned','aggregate','consumer-aligned')",
            name="ck_domains_archetype",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    archetype: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DomainMember(Base):
    """One user's membership in one domain, with an owner/developer role.

    The M:M shape lets a domain carry several owners and developers
    at once — distinct from the single ``DataProduct.steward_user_id``
    pointer this layer complements.  The per-membership ``role`` grants
    domain-local responsibility without elevating the user to a
    tenant-wide :attr:`User.is_admin`.

    Attributes:
        id: Auto-incremented primary key.
        domain_id: FK on ``domains.id`` with CASCADE delete so a
            removed domain takes its memberships with it.
        user_id: FK on ``users.id``.
        role: One of :data:`DOMAIN_MEMBER_ROLES`.
        created_at: Wall-clock the membership was granted.
    """

    __tablename__ = "domain_members"

    __table_args__ = (
        UniqueConstraint("domain_id", "user_id", name="uq_domain_members_identity"),
        Index("ix_domain_members_user", "user_id"),
        CheckConstraint(
            "role IN ('owner','developer')",
            name="ck_domain_members_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("domains.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductTransformation(Base):
    """Binds the code that produces a product to the product itself.

    A product may declare more than one transformation (e.g. a build
    notebook plus a test dbt model), so this is a one-to-many table
    rather than a column on ``data_products``.  Exactly one of
    ``notebook_id`` / ``dbt_model_name`` is populated per row,
    depending on ``kind``.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.
        kind: One of :data:`DP_TRANSFORMATION_KINDS`.
        notebook_id: FK on ``notebooks.id`` (SET NULL on delete) when
            ``kind == 'notebook'``; ``None`` otherwise.
        dbt_model_name: dbt model name when ``kind == 'dbt_model'``;
            ``None`` otherwise.  dbt models are not persisted as their
            own rows, so the binding stores the model name verbatim.
        created_by_user_id: Nullable FK on ``users.id`` recording who
            bound the transformation.
        created_at: Wall-clock the binding was created.
    """

    __tablename__ = "data_product_transformations"

    __table_args__ = (
        Index("ix_dp_transformations_product", "data_product_id"),
        CheckConstraint(
            "kind IN ('notebook','dbt_model')",
            name="ck_dp_transformations_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    notebook_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="SET NULL"),
        nullable=True,
    )
    dbt_model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
