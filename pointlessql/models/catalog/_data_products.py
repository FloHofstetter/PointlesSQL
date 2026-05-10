"""Data-product cache + contract-event log (Phase 50).

Two tables:

* ``data_products`` — one row per ``(workspace, catalog, schema)``
  triple that was declared as a data product via a
  ``pointlessql.yaml`` file.  Yaml is canonical (git-blame is the
  audit log); this row is a cache that
  :func:`pointlessql.data_products.load_contract` materialises so
  the ``/api/data-products`` UI and the hermes-plugin tools don't
  need filesystem access to the data team's repo.
* ``data_product_contract_events`` — append-only log: every
  ``pql.write`` / ``pql.merge`` against a product-bearing schema
  stamps one row with the outcome (``compliant`` /
  ``schema_drift_warning`` / ``violated`` / ``no_contract``).
  Powers the Compliance tab on the product detail page and the
  ``pql_data_product_compliance_history`` plugin tool.

Storage decision: PointlesSQL metadata DB.  No new credential
surface; the rows reference the existing soyuz UC schema by name
(no FK because UC lives in a separate process).
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

CONTRACT_EVENT_OUTCOMES: tuple[str, ...] = (
    "compliant",
    "schema_drift_warning",
    "violated",
    "no_contract",
)


class DataProduct(Base):
    """Cached metadata for one UC schema declared as a data product.

    The yaml file is the source of truth — this row exists so HTTP
    + plugin callers don't need filesystem access.  Every load
    UPSERTs by ``(workspace_id, catalog_name, schema_name)`` and
    refreshes ``contract_yaml_hash`` + ``contract_json`` +
    ``last_loaded_at``.

    ``contract_json`` is the JSON-serialised
    :class:`pointlessql.data_products.DataProductContract` after
    pydantic validation.  Re-validating it on read is cheap and
    keeps the ORM layer free of pydantic awareness.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this product belongs to.  FK on
            ``workspaces.id``; ``server_default='1'`` so the
            seeded default workspace adopts every pre-Phase-29
            row at upgrade time.
        catalog_name: UC catalog segment.
        schema_name: UC schema segment.  ``(workspace_id,
            catalog_name, schema_name)`` is unique.
        steward_user_id: Nullable FK on ``users.id``.  Set when
            the yaml's ``steward_email`` resolves to a persisted
            user; left NULL otherwise.  The detail-page UI falls
            back to a mailto link in the NULL case.
        version: SemVer string from the yaml (e.g. ``"1.2.0"``).
        description: One-paragraph description from the yaml.
        sla_minutes: Optional freshness SLA in minutes; NULL
            means "no SLA expectation" — the freshness scanner
            (Sprint 50.4) skips these rows.
        contract_yaml_hash: SHA-256 of the yaml file as it was
            last loaded.  Drift detection compares this against
            a fresh hash on re-load and triggers a re-cache.
        contract_json: The pydantic-validated contract serialised
            as JSON.  Read by the diff helper, the enforcement
            hook, and the plugin tools without re-reading yaml.
        last_loaded_at: Wall-clock when ``load_contract`` last
            UPSERTed this row.
        last_alerted_at: Wall-clock when the freshness scanner
            last emitted a SLA-violation event.  Used for re-
            alert suppression (analogue to
            :class:`ExpectedLineageInbound`).
        created_at: Wall-clock when the row was first inserted.
    """

    __tablename__ = "data_products"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "catalog_name",
            "schema_name",
            name="uq_data_products_ws_catalog_schema",
        ),
        Index(
            "ix_data_products_workspace_loaded",
            "workspace_id",
            "last_loaded_at",
        ),
        Index("ix_data_products_steward", "steward_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    catalog_name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    steward_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sla_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_yaml_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_json: Mapped[str] = mapped_column(Text, nullable=False)
    last_loaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_alerted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DataProductContractEvent(Base):
    """Append-only audit row: one per write against a product-schema.

    Stamped from
    :func:`pointlessql.services.agent_runs.operations._lifecycle`
    after a successful op-context exit (analogue to the existing
    ``pending_lineage_edges`` / ``pending_column_edges`` hooks).
    Populates the Compliance tab on the product detail page and
    feeds the ``pql_data_product_compliance_history`` plugin tool.

    ``data_product_id`` may be NULL when the write targeted a
    schema that has no cached contract — the row still records
    "we considered enforcement and saw nothing" so debug paths
    can distinguish "no row" from "row missed".

    Attributes:
        id: Auto-incremented primary key.
        agent_run_operation_id: FK on
            ``agent_run_operations.id`` with CASCADE delete.
        data_product_id: Nullable FK on ``data_products.id``.
        outcome: One of :data:`CONTRACT_EVENT_OUTCOMES`.
        details_json: Free-form JSON describing the diff.  Empty
            object ``{}`` for ``compliant`` / ``no_contract`` rows;
            populated for ``violated`` and ``schema_drift_warning``
            with the breaking diff or drift summary.
        created_at: Wall-clock the row was stamped.
    """

    __tablename__ = "data_product_contract_events"

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('compliant','schema_drift_warning','violated','no_contract')",
            name="ck_data_product_contract_events_outcome",
        ),
        Index(
            "ix_data_product_contract_events_product_created",
            "data_product_id",
            "created_at",
        ),
        Index(
            "ix_data_product_contract_events_op",
            "agent_run_operation_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_run_operation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agent_run_operations.id", ondelete="CASCADE"),
        nullable=False,
    )
    data_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
