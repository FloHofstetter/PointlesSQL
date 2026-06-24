"""Data-product cache + contract-event log.

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

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
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

#: Allowed values for :attr:`DataProduct.lifecycle_state`.  Mirrors the
#: state machine the lifecycle service enforces and the SQL CHECK on
#: ``data_products.lifecycle_state``.
LIFECYCLE_STATES: tuple[str, ...] = (
    "draft",
    "active",
    "deprecated",
    "retired",
    "archived",
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
            seeded default workspace adopts every pre-existing
            row at upgrade time.
        catalog_name: UC catalog segment.
        schema_name: UC schema segment.  ``(workspace_id,
            catalog_name, schema_name)`` is unique.
        steward_user_id: Nullable FK on ``users.id``.  Set when
            the yaml's ``steward_email`` resolves to a persisted
            user; left NULL otherwise.  The detail-page UI falls
            back to a mailto link in the NULL case.
        domain_id: Nullable FK on ``domains.id``.  Set when the
            product is assigned to a business domain; ``SET NULL``
            on domain delete so a removed domain never orphans the
            product.  NULL means "unassigned".
        version: SemVer string from the yaml (e.g. ``"1.2.0"``).
        description: One-paragraph description from the yaml.
        sla_minutes: Optional freshness SLA in minutes; NULL
            means "no SLA expectation" — the freshness scanner
            skips these rows.
        contract_yaml_hash: SHA-256 of the yaml file as it was
            last loaded.  Drift detection compares this against
            a fresh hash on re-load and triggers a re-cache.
        contract_json: The pydantic-validated contract serialised
            as JSON.  Read by the diff helper, the enforcement
            hook, and the plugin tools without re-reading yaml.
        sample_sql: Optional example query that demonstrates how to
            use the product.  Surfaced in the discovery contract +
            the Semantic panel so a consumer has runnable starter
            code; ``None`` when no example was declared.
        last_loaded_at: Wall-clock when ``load_contract`` last
            UPSERTed this row.
        last_alerted_at: Wall-clock when the freshness scanner
            last emitted a SLA-violation event.  Used for re-
            alert suppression (analogue to
            :class:`ExpectedLineageInbound`).
        created_at: Wall-clock when the row was first inserted.
        lifecycle_state: Operational state.  One of
            :data:`LIFECYCLE_STATES`.  Default ``'active'``; the
            lifecycle service is the only writer.
        lifecycle_changed_at: Wall-clock of the last transition,
            or ``None`` if the product is still in its
            insert-time state.
        lifecycle_changed_by_user_id: Nullable FK on ``users.id``
            recording who drove the last transition.
        replacement_data_product_id: When the product is
            ``retired`` and a successor exists, nullable FK to the
            successor row so consumers can follow a redirect.
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
        Index("ix_data_products_domain", "domain_id"),
        Index("ix_data_products_lifecycle_state", "lifecycle_state"),
        CheckConstraint(
            "lifecycle_state IN ('draft','active','deprecated','retired','archived')",
            name="ck_data_products_lifecycle_state",
        ),
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
    domain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("domains.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sla_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_yaml_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_json: Mapped[str] = mapped_column(Text, nullable=False)
    sample_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_loaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_alerted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    lifecycle_changed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lifecycle_changed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    replacement_data_product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_products.id"), nullable=True
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
        correlation_id: Optional cross-product trace id linking this
            row to agent-run operations and audit-log rows.
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
        Index(
            "ix_data_product_contract_events_correlation_id",
            "correlation_id",
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
    correlation_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductStatistics(Base):
    """Self-generated statistics snapshot, stamped at write time.

    Every write against a product-bearing schema stamps one row
    (analogue to :class:`DataProductContractEvent`) so a product
    *generates its own* shape + freshness metrics rather than having
    them extracted by an external profiler later.  The latest row per
    ``(data_product_id, table_name)`` feeds the discovery contract +
    the Statistics panel.

    The shape is computed cheaply from the in-memory frame the write
    already holds (per-column null/distinct), so the write path never
    pays for a full table re-scan.  When a full on-demand profile
    already exists for the exact delta version (``table_stats`` cache),
    the post-commit hook upgrades ``shape_json`` from it and sets
    ``profile_kind='reused'``.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.  Always set — a row exists only because the write
            resolved to a product.
        agent_run_operation_id: Nullable FK on
            ``agent_run_operations.id`` (SET NULL on delete) — the
            snapshot is product history that outlives audit pruning.
        table_name: UC table name (last segment) the write targeted.
        delta_log_version: ``DeltaTable.version()`` after the write,
            or ``None`` when the version could not be read.
        row_count: Rows in the written frame, or ``None``.
        shape_json: JSON ``{"column_count": int, "columns":
            {"<col>": {"null_count": int, "distinct": int|null}}}``.
        profile_kind: ``light`` (in-memory shape), ``reused``
            (upgraded from the on-demand cache), or ``full``.
        freshness_lag_minutes: Left ``None`` at write (lag is ~0);
            the discovery reader computes lag at read time.
        created_at: Wall-clock the snapshot was stamped.
    """

    __tablename__ = "data_product_statistics"

    __table_args__ = (
        CheckConstraint(
            "profile_kind IN ('light','full','reused')",
            name="ck_data_product_statistics_profile_kind",
        ),
        Index(
            "ix_dp_statistics_latest",
            "data_product_id",
            "table_name",
            "created_at",
        ),
        Index("ix_dp_statistics_op", "agent_run_operation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_run_operation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agent_run_operations.id", ondelete="SET NULL"),
        nullable=True,
    )
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    delta_log_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    shape_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    profile_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="light")
    freshness_lag_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductCanvasGraph(Base):
    """One stored version of a data product's visual block-and-wire graph.

    The visual editor authors a DAG of typed blocks (InputPort, Filter,
    Join, GroupBy, OutputPort, …) that compiles to DuckDB SQL and
    materialises one or more output ports of the parent product.  This
    table keeps an append-only ledger of graph versions per product so
    the editor can offer named versions / restore / compare without
    losing prior edits.  ``version`` is monotonic per
    ``data_product_id`` (1-based), enforced by the UNIQUE constraint.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.  When a product is removed the graph history goes
            with it; there is no value in stranded canvases.
        version: 1-based monotonic version per product.  The executor
            mints the next integer above the current MAX on save.
        document: JSON serialisation of the ``CanvasDoc`` Pydantic
            envelope (nodes + edges + schema_version).  Text rather
            than dialect-specific JSON so the SQLite test path stays
            simple.
        author_user_id: User who authored this version, nullable
            (cleared on user deletion via SET NULL so history survives
            account removal).
        created_at: Wall-clock the version row was minted.
        is_production: True for the one row per ``data_product_id`` that
            is marked as the live production revision.  Enforced as
            "at most one per product" by a partial unique index on
            ``(data_product_id) WHERE is_production = TRUE``.  Default
            False; the column is opt-in and not auto-set on save.
    """

    __tablename__ = "data_product_canvas_graph"

    __table_args__ = (
        UniqueConstraint(
            "data_product_id",
            "version",
            name="uq_dp_canvas_graph_dp_version",
        ),
        Index("ix_dp_canvas_graph_dp", "data_product_id"),
        Index(
            "idx_unique_production_per_dp",
            "data_product_id",
            unique=True,
            sqlite_where=sa.text("is_production = 1"),
            postgresql_where=sa.text("is_production = TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_production: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
