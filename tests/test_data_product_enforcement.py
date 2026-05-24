"""Tests for the contract-enforcement hook.

Validates the diff helper, the enforcement service, and the
end-to-end behaviour of ``pql.write_table`` against a yaml-declared
contract: compliant writes stamp ``compliant`` events, breaking
writes raise :class:`DataProductContractViolation` *before* any
Delta IO happens, and schema-drift writes stamp warnings without
raising.
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import (
    DataProductContractViolation,
    DataProductTableContract,
    diff_contract_against_engine_columns,
    load_contract,
)
from pointlessql.data_products._diff import ActualColumn, _diff_columns
from pointlessql.data_products._enforce import check_contract_for_write
from pointlessql.data_products._schema import DataProductColumnSpec
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.models.catalog._data_products import DataProductContractEvent

ORDERS_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id,    type: long,      nullable: false}
        - {name: customer_id, type: long,      nullable: false}
        - {name: order_total, type: double,    nullable: true}
"""


def _write_yaml(tmp_path: Path) -> Path:
    """Write the canonical orders contract and return the yaml path."""
    p = tmp_path / "pointlessql.yaml"
    p.write_text(ORDERS_YAML, encoding="utf-8")
    return p


def _seed_agent_run(workspace_id: int = 1) -> str:
    """Insert one ``agent_runs`` row and return its id."""
    factory = app.state.session_factory
    run_id = uuid.uuid4().hex
    with factory() as session:
        run = AgentRun(
            id=run_id,
            workspace_id=workspace_id,
            principal="test-principal",
            notebook_path="test/path.py",
            status="running",
            started_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(run)
        session.commit()
    return run_id


# ---------------------------------------------------------------------------
# Pure-diff core
# ---------------------------------------------------------------------------


def _orders_contract() -> DataProductTableContract:
    """Return the orders table contract used across the diff tests."""
    return DataProductTableContract(
        name="orders",
        primary_key=("order_id",),
        columns=(
            DataProductColumnSpec(name="order_id", type="long", nullable=False),
            DataProductColumnSpec(name="customer_id", type="long", nullable=False),
            DataProductColumnSpec(name="order_total", type="double", nullable=True),
        ),
    )


def test_diff_compliant() -> None:
    """Identical schema → no diffs, not breaking."""
    contract = _orders_contract()
    actual = [
        ActualColumn(name="order_id", type="long", nullable=False),
        ActualColumn(name="customer_id", type="long", nullable=False),
        ActualColumn(name="order_total", type="double", nullable=True),
    ]
    result = _diff_columns(contract, actual)
    assert result.is_breaking is False
    assert result.missing_columns == ()
    assert result.extra_columns == ()
    assert result.type_mismatches == ()


def test_diff_missing_required_column() -> None:
    """A missing contract column flags the diff as breaking."""
    contract = _orders_contract()
    actual = [
        ActualColumn(name="order_id", type="long", nullable=False),
        ActualColumn(name="customer_id", type="long", nullable=False),
    ]
    result = _diff_columns(contract, actual)
    assert result.is_breaking is True
    assert result.missing_columns == ("order_total",)


def test_diff_dropped_pk_is_breaking() -> None:
    """Dropping a PK-declared column is breaking even if it's nullable."""
    contract = _orders_contract()
    actual = [
        ActualColumn(name="customer_id", type="long", nullable=False),
        ActualColumn(name="order_total", type="double", nullable=True),
    ]
    result = _diff_columns(contract, actual)
    assert result.is_breaking is True
    assert "order_id" in result.dropped_pk_columns


def test_diff_extra_column_is_drift_not_breaking() -> None:
    """Extra columns surface as drift but don't escalate to breaking."""
    contract = _orders_contract()
    actual = [
        ActualColumn(name="order_id", type="long", nullable=False),
        ActualColumn(name="customer_id", type="long", nullable=False),
        ActualColumn(name="order_total", type="double", nullable=True),
        ActualColumn(name="region", type="string", nullable=True),
    ]
    result = _diff_columns(contract, actual)
    assert result.is_breaking is False
    assert result.extra_columns == ("region",)


def test_diff_type_mismatch_is_breaking() -> None:
    """A swapped contract type (long → string) is breaking."""
    contract = _orders_contract()
    actual = [
        ActualColumn(name="order_id", type="string", nullable=False),
        ActualColumn(name="customer_id", type="long", nullable=False),
        ActualColumn(name="order_total", type="double", nullable=True),
    ]
    result = _diff_columns(contract, actual)
    assert result.is_breaking is True
    assert any(name == "order_id" for (name, _c, _a) in result.type_mismatches)


def test_diff_canonicalises_aliases() -> None:
    """``int64`` collapses to ``long``; ``float64`` to ``double``."""
    contract = _orders_contract()
    actual = [
        ActualColumn(name="order_id", type="int64", nullable=False),
        ActualColumn(name="customer_id", type="bigint", nullable=False),
        ActualColumn(name="order_total", type="float64", nullable=True),
    ]
    result = _diff_columns(contract, actual)
    assert result.is_breaking is False


# ---------------------------------------------------------------------------
# Engine-tuples adapter
# ---------------------------------------------------------------------------


def test_engine_columns_adapter_round_trips() -> None:
    """The engine adapter keeps the diff result identical to the core."""
    contract = _orders_contract()
    columns = [
        ("order_id", "LONG", "long", False),
        ("customer_id", "LONG", "long", False),
        ("order_total", "DOUBLE", "double", True),
    ]
    result = diff_contract_against_engine_columns(contract, columns)
    assert result.is_breaking is False


# ---------------------------------------------------------------------------
# Enforcement service (DB-resolution path)
# ---------------------------------------------------------------------------


def test_enforce_no_factory_short_circuits() -> None:
    """Interactive PQL (no factory) returns ``no_contract`` cheaply."""
    result = check_contract_for_write(
        factory=None,
        agent_run_id="abc",
        catalog="main",
        schema="sales_gold",
        table="orders",
        df_columns=[],
        mode="overwrite",
    )
    assert result.outcome == "no_contract"
    assert result.violation is None


def test_enforce_no_cached_row_returns_no_contract(tmp_path: Path) -> None:
    """A schema with no cached contract returns ``no_contract`` cleanly."""
    factory = app.state.session_factory
    run_id = _seed_agent_run()
    result = check_contract_for_write(
        factory=factory,
        agent_run_id=run_id,
        catalog="other",
        schema="schema_without_contract",
        table="t",
        df_columns=[("a", "LONG", "long", False)],
        mode="overwrite",
    )
    assert result.outcome == "no_contract"
    assert result.violation is None


def test_enforce_undeclared_table_returns_no_contract(tmp_path: Path) -> None:
    """Loading a contract for one table doesn't enforce on others."""
    yaml_path = _write_yaml(tmp_path)
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    run_id = _seed_agent_run()

    result = check_contract_for_write(
        factory=factory,
        agent_run_id=run_id,
        catalog="main",
        schema="sales_gold",
        table="undeclared_table",
        df_columns=[("a", "LONG", "long", False)],
        mode="overwrite",
    )
    assert result.outcome == "no_contract"
    # The cached product was matched but no per-table contract.
    assert result.data_product_id is not None


def test_enforce_compliant_write_stamps_compliant(tmp_path: Path) -> None:
    """A frame matching the contract returns ``compliant``."""
    yaml_path = _write_yaml(tmp_path)
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    run_id = _seed_agent_run()

    result = check_contract_for_write(
        factory=factory,
        agent_run_id=run_id,
        catalog="main",
        schema="sales_gold",
        table="orders",
        df_columns=[
            ("order_id", "LONG", "long", False),
            ("customer_id", "LONG", "long", False),
            ("order_total", "DOUBLE", "double", True),
        ],
        mode="overwrite",
    )
    assert result.outcome == "compliant"
    assert result.violation is None
    assert result.data_product_id is not None


def test_enforce_breaking_write_raises_violation(tmp_path: Path) -> None:
    """A frame missing a required column produces a violation object."""
    yaml_path = _write_yaml(tmp_path)
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    run_id = _seed_agent_run()

    result = check_contract_for_write(
        factory=factory,
        agent_run_id=run_id,
        catalog="main",
        schema="sales_gold",
        table="orders",
        df_columns=[
            ("order_id", "LONG", "long", False),
            ("customer_id", "LONG", "long", False),
            # order_total dropped on purpose
        ],
        mode="overwrite",
    )
    assert result.outcome == "violated"
    assert isinstance(result.violation, DataProductContractViolation)
    assert "order_total" in result.violation.breaking_diff["missing_columns"]


def test_enforce_drift_warning_does_not_raise(tmp_path: Path) -> None:
    """Extra columns are warnings, not violations."""
    yaml_path = _write_yaml(tmp_path)
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    run_id = _seed_agent_run()

    result = check_contract_for_write(
        factory=factory,
        agent_run_id=run_id,
        catalog="main",
        schema="sales_gold",
        table="orders",
        df_columns=[
            ("order_id", "LONG", "long", False),
            ("customer_id", "LONG", "long", False),
            ("order_total", "DOUBLE", "double", True),
            ("region", "STRING", "string", True),
        ],
        mode="append",
    )
    assert result.outcome == "schema_drift_warning"
    assert result.violation is None
    assert "region" in result.details["extra_columns"]


# ---------------------------------------------------------------------------
# End-to-end: pql.write_table records compliance event
# ---------------------------------------------------------------------------


def test_e2e_compliant_write_records_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full path: yaml load → pql.write_table → ``compliant`` event row."""
    pytest.importorskip("deltalake")

    from unittest.mock import MagicMock

    from soyuz_catalog_client.errors import UnexpectedStatus

    import pointlessql.db as db_mod
    from pointlessql.pql import PandasEngine, write_table

    yaml_path = _write_yaml(tmp_path)
    factory = app.state.session_factory
    monkeypatch.setattr(db_mod, "get_session_factory", lambda: factory)
    load_contract(yaml_path, factory=factory)
    run_id = _seed_agent_run()

    # Pre-create the parent schema directory so derive_storage_location's
    # soyuz call can find a storage_root.  The simplest path is to mock
    # the soyuz client outright — write_table only needs storage URI +
    # CreateTable acknowledgement.
    storage_dir = tmp_path / "delta_orders"
    storage_dir.mkdir()

    client = MagicMock()
    # Mock _get_table.sync raising 404 (table does not yet exist).
    raise_404 = UnexpectedStatus(status_code=404, content=b"")

    def _raise_404(**_kwargs: object) -> object:
        raise raise_404

    # Patch the imports used inside write_table.
    import pointlessql.pql._write as write_mod

    monkey_get_table = write_mod._get_table  # noqa: SLF001
    monkey_create_table = write_mod._create_table  # noqa: SLF001
    monkey_get_schema = write_mod._get_schema  # noqa: SLF001

    write_mod._get_table = type(  # noqa: SLF001
        "S", (), {"sync": staticmethod(_raise_404)}
    )()  # type: ignore[assignment]
    write_mod._create_table = type(  # noqa: SLF001
        "S", (), {"sync": staticmethod(lambda **_: None)}
    )()  # type: ignore[assignment]

    from soyuz_catalog_client.models.schema_info import SchemaInfo

    fake_schema = SchemaInfo(name="sales_gold", catalog_name="main")
    fake_schema.storage_root = str(storage_dir)
    write_mod._get_schema = type(  # noqa: SLF001
        "S", (), {"sync": staticmethod(lambda **_: fake_schema)}
    )()  # type: ignore[assignment]

    try:
        df = pd.DataFrame(
            {
                "order_id": [1, 2, 3],
                "customer_id": [10, 20, 30],
                "order_total": [9.99, 19.99, 29.99],
            }
        )
        write_table(
            client=client,
            engine=PandasEngine(),
            df=df,
            full_name="main.sales_gold.orders",
            mode="overwrite",
            unreachable_msg="unreachable",
            agent_run_id=run_id,
        )
    finally:
        write_mod._get_table = monkey_get_table  # noqa: SLF001
        write_mod._create_table = monkey_create_table  # noqa: SLF001
        write_mod._get_schema = monkey_get_schema  # noqa: SLF001

    with factory() as session:
        events = session.execute(select(DataProductContractEvent)).scalars().all()
        assert len(events) == 1
        assert events[0].outcome == "compliant"
        op = session.get(AgentRunOperation, events[0].agent_run_operation_id)
        assert op is not None
        assert op.error_message is None


def test_e2e_breaking_write_blocks_delta_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A breaking write raises BEFORE any Delta IO happens."""
    pytest.importorskip("deltalake")

    from unittest.mock import MagicMock

    from soyuz_catalog_client.errors import UnexpectedStatus
    from soyuz_catalog_client.models.schema_info import SchemaInfo

    import pointlessql.db as db_mod
    import pointlessql.pql._write as write_mod
    from pointlessql.pql import PandasEngine, write_table

    yaml_path = _write_yaml(tmp_path)
    factory = app.state.session_factory
    monkeypatch.setattr(db_mod, "get_session_factory", lambda: factory)
    load_contract(yaml_path, factory=factory)
    run_id = _seed_agent_run()

    storage_dir = tmp_path / "delta_orders_breaking"
    storage_dir.mkdir()

    client = MagicMock()

    raise_404 = UnexpectedStatus(status_code=404, content=b"")

    def _raise_404(**_kwargs: object) -> object:
        raise raise_404

    fake_schema = SchemaInfo(name="sales_gold", catalog_name="main")
    fake_schema.storage_root = str(storage_dir)

    write_calls: list[tuple[object, str, str]] = []

    class _SpyEngine(PandasEngine):
        def write(self, frame: object, storage_location: str, mode: str) -> None:  # type: ignore[override]
            write_calls.append((frame, storage_location, mode))
            super().write(frame, storage_location, mode)  # type: ignore[arg-type]

    monkey_get_table = write_mod._get_table  # noqa: SLF001
    monkey_create_table = write_mod._create_table  # noqa: SLF001
    monkey_get_schema = write_mod._get_schema  # noqa: SLF001

    write_mod._get_table = type(  # noqa: SLF001
        "S", (), {"sync": staticmethod(_raise_404)}
    )()  # type: ignore[assignment]
    write_mod._create_table = type(  # noqa: SLF001
        "S", (), {"sync": staticmethod(lambda **_: None)}
    )()  # type: ignore[assignment]
    write_mod._get_schema = type(  # noqa: SLF001
        "S", (), {"sync": staticmethod(lambda **_: fake_schema)}
    )()  # type: ignore[assignment]

    try:
        df_missing_total = pd.DataFrame(
            {
                "order_id": [1, 2, 3],
                "customer_id": [10, 20, 30],
            }
        )
        with pytest.raises(DataProductContractViolation):
            write_table(
                client=client,
                engine=_SpyEngine(),
                df=df_missing_total,
                full_name="main.sales_gold.orders",
                mode="overwrite",
                unreachable_msg="unreachable",
                agent_run_id=run_id,
            )
    finally:
        write_mod._get_table = monkey_get_table  # noqa: SLF001
        write_mod._create_table = monkey_create_table  # noqa: SLF001
        write_mod._get_schema = monkey_get_schema  # noqa: SLF001

    # Engine.write was NEVER invoked.
    assert write_calls == []

    # The audit row carries the violation; the contract event row is
    # 'violated'.
    with factory() as session:
        events = session.execute(select(DataProductContractEvent)).scalars().all()
        assert len(events) == 1
        assert events[0].outcome == "violated"
        details = json.loads(events[0].details_json)
        assert "order_total" in details["missing_columns"]
        op = session.get(AgentRunOperation, events[0].agent_run_operation_id)
        assert op is not None
        assert op.error_message is not None
        assert "DataProductContractViolation" in op.error_message
