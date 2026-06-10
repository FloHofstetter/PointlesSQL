"""Per-product contract tests + synthetic fixtures + run-result ledger.

Three tables that turn the discovery contract from a passive
declaration into an executable, repeatable smoke test consumers can
run against a product:

* ``data_product_fixtures`` — a Faker spec per declared table; the
  generator turns the spec into an Arrow table the runner evaluates
  contract tests against without touching the live storage layer.
* ``data_product_contract_tests`` — declarative assertion definitions
  ('row_count_range', 'column_present', 'value_distribution',
  'null_rate', 'referential', 'freshness') with severity + enabled
  flag.
* ``data_product_contract_test_results`` — append-only ledger of
  every run; pagination by ``run_at``.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
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

#: Assertion kinds the evaluator knows.  CHECK-bounded in the DB.
ASSERTION_KINDS: tuple[str, ...] = (
    "row_count_range",
    "column_present",
    "value_distribution",
    "null_rate",
    "referential",
    "freshness",
)

#: Severity ladder for a failing test.  ``info`` lands a result row
#: without raising; ``warn`` lands a row + emits a warn-shaped audit;
#: ``error`` does the same plus is what the runner reports as ``failed``.
CONTRACT_TEST_SEVERITIES: tuple[str, ...] = ("info", "warn", "error")

#: Outcome statuses a single run produces.
CONTRACT_TEST_STATUSES: tuple[str, ...] = ("pass", "fail", "error")


class DataProductFixture(Base):
    """Synthetic-data spec for one declared table.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE.
        table_name: UC table name the fixture stands in for; unique
            inside the product.
        generator_spec_json: JSON-encoded list of per-column generator
            descriptors (e.g. ``[{"column": "email", "kind": "email"}]``).
        row_count: How many rows the runner asks the generator for.
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the row was first inserted.
    """

    __tablename__ = "data_product_fixtures"

    __table_args__ = (
        UniqueConstraint(
            "data_product_id",
            "table_name",
            name="uq_data_product_fixtures_product_table",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_name: Mapped[str] = mapped_column(String(200), nullable=False)
    generator_spec_json: Mapped[str] = mapped_column(Text(), nullable=False)
    row_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductContractTest(Base):
    """One declarative contract assertion bound to a product.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE.
        name: Human-readable test name; unique inside the product.
        assertion_kind: One of :data:`ASSERTION_KINDS`.  CHECK-bounded.
        assertion_spec_json: JSON-encoded assertion parameters; the
            evaluator picks the parameters relevant to the kind.
        severity: One of :data:`CONTRACT_TEST_SEVERITIES`.
        enabled: When False the scheduler + ``run_tests`` skip this
            test.  Disabled tests still surface in the listing.
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the row was first inserted.
    """

    __tablename__ = "data_product_contract_tests"

    __table_args__ = (
        CheckConstraint(
            "assertion_kind IN ('row_count_range','column_present',"
            "'value_distribution','null_rate','referential','freshness')",
            name="ck_contract_tests_assertion_kind",
        ),
        CheckConstraint(
            "severity IN ('info','warn','error')",
            name="ck_contract_tests_severity",
        ),
        UniqueConstraint("data_product_id", "name", name="uq_contract_tests_product_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    assertion_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    assertion_spec_json: Mapped[str] = mapped_column(Text(), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(8), nullable=False, default="warn", server_default="warn"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductContractTestResult(Base):
    """One row per contract-test evaluation.

    Attributes:
        id: Auto-incremented primary key.
        contract_test_id: FK on ``data_product_contract_tests.id``
            with CASCADE.
        run_at: Wall-clock the run finished.
        status: One of :data:`CONTRACT_TEST_STATUSES`.  CHECK-bounded.
        observation_json: Free-form JSON carrying the evaluator's
            metrics — actual row count, observed null rate, etc.
        duration_ms: Evaluator latency in milliseconds.
    """

    __tablename__ = "data_product_contract_test_results"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pass','fail','error')",
            name="ck_contract_test_results_status",
        ),
        Index(
            "ix_contract_test_results_test",
            "contract_test_id",
            "run_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_test_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_contract_tests.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    observation_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
