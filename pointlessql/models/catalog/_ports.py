"""Declared input/output ports of a data product.

Two tables that turn a data product from passive metadata into an
addressable *quantum* by declaring how data enters and leaves it:

* ``data_product_output_ports`` — the externally addressable access
  modes a product exposes.  The SQL access mode always exists
  implicitly (the data is queryable through PQL / the SQL API); a
  declared output port records the *additional* modes — a Parquet
  file export, an event/pub-sub stream — plus their format and a
  human note, so consumers can see at a glance how to natively
  access the product.
* ``data_product_input_ports`` — the declared upstream sources a
  product consumes (an operational system, an upstream data product,
  or an external feed).  Declaring inputs gives a *declared* lineage
  graph alongside the runtime-captured one; ``upstream_product`` rows
  carry a ``catalog.schema`` ref so the UI can link to the producing
  product.

Storage decision: PointlesSQL metadata DB.  Ports are edited via the
steward/admin API + agent plugin tools rather than authored in the
yaml contract, so they reference the product by ``data_product_id``
FK and cascade on product delete.
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

#: Allowed values for :attr:`DataProductOutputPort.kind`.  ``sql`` is
#: the always-implicit query access mode; ``file`` is a downloadable
#: columnar export (Parquet); ``event`` is a pub-sub / stream mode.
OUTPUT_PORT_KINDS: tuple[str, ...] = ("sql", "file", "event")

#: Allowed values for :attr:`DataProductInputPort.kind`.  Mirrors
#: Dehghani's upstream-source taxonomy: an ``operational_system``
#: (an OLTP source), an ``upstream_product`` (another data product in
#: the mesh), or an ``external`` feed outside the platform.
INPUT_PORT_KINDS: tuple[str, ...] = (
    "operational_system",
    "upstream_product",
    "external",
)


class DataProductOutputPort(Base):
    """One declared access mode a product exposes to consumers.

    A product may declare several output ports (e.g. a Parquet file
    export plus an event stream), so this is a one-to-many table.
    The ``sql`` kind is normally implicit, but a row can still be
    declared for it to attach a description or location.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.
        name: Short label, unique per product (e.g. "parquet-export").
        kind: One of :data:`OUTPUT_PORT_KINDS`.
        description: Free-form note on how to consume the port.
        format: Optional payload format (e.g. ``parquet``); ``None``
            when not applicable.
        location: Optional address — a download path, a topic name,
            or a URI; ``None`` when the platform derives it.
        created_by_user_id: Nullable FK on ``users.id`` recording who
            declared the port.
        created_at: Wall-clock the port was declared.
    """

    __tablename__ = "data_product_output_ports"

    __table_args__ = (
        UniqueConstraint("data_product_id", "name", name="uq_dp_output_ports_name"),
        Index("ix_dp_output_ports_product", "data_product_id"),
        CheckConstraint(
            "kind IN ('sql','file','event')",
            name="ck_dp_output_ports_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    identity_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductInputPort(Base):
    """One declared upstream source a product consumes.

    Declaring inputs makes the dependency explicit (a *declared*
    lineage edge) rather than relying solely on runtime capture.  An
    ``upstream_product`` row stores a ``catalog.schema`` ref in
    ``source_ref`` so the UI can link to the producing product;
    other kinds use ``source_ref`` for a URI or a free-form name.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.
        name: Short label, unique per product.
        kind: One of :data:`INPUT_PORT_KINDS`.
        source_ref: ``catalog.schema`` for ``upstream_product``; a
            URI or system name otherwise; ``None`` when unspecified.
        description: Free-form note on the dependency.
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the input was declared.
    """

    __tablename__ = "data_product_input_ports"

    __table_args__ = (
        UniqueConstraint("data_product_id", "name", name="uq_dp_input_ports_name"),
        Index("ix_dp_input_ports_product", "data_product_id"),
        CheckConstraint(
            "kind IN ('operational_system','upstream_product','external')",
            name="ck_dp_input_ports_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
