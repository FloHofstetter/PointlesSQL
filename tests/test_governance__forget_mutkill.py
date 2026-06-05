"""Mutation-killing tests for the right-to-be-forgotten control op.

Pins observable behaviour of ``_forget`` that surviving mutants would
change: the empty-input guard, exact error messages, the wiring of the
UC client / PQL constructor, the cross-table delete accumulator, the
``executed_at`` stamp, and the newest-first ledger ordering.  Each test
asserts a value that is true on the real code and false on the mutant.
"""

from __future__ import annotations

import datetime
import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct, DataProductForgetRequest
from pointlessql.services.governance._forget import (
    execute_forget,
    list_forget_requests,
    propose_forget,
)


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str, *, tables=None) -> int:
    """Insert a minimal DataProduct row with a valid contract; return id."""
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": tables or [],
    }
    with _factory()() as session:
        row = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


# ---------------------------------------------------------------------------
# PQL / client-wiring recorder
# ---------------------------------------------------------------------------


class _RecordingPQL:
    """PQL stand-in that records its constructor kwargs and delete calls.

    Per-table delete metrics come from ``metrics_for`` (table -> dict);
    an absent table falls back to ``default_metrics``.
    """

    init_kwargs: dict[str, object] = {}
    init_has_client: bool = False
    init_has_settings: bool = False
    calls: list[tuple[str, str | None]] = []
    metrics_for: dict[str, dict[str, int]] = {}
    default_metrics: dict[str, int] = {"num_deleted_rows": 0}

    def __init__(self, **kwargs: object) -> None:
        _RecordingPQL.init_kwargs = dict(kwargs)
        _RecordingPQL.init_has_client = "client" in kwargs
        _RecordingPQL.init_has_settings = "settings" in kwargs

    def delete(self, target: str, *, where: str | None = None) -> dict[str, int]:
        _RecordingPQL.calls.append((target, where))
        table = target.rsplit(".", 1)[-1]
        return dict(_RecordingPQL.metrics_for.get(table, _RecordingPQL.default_metrics))


_SENTINEL_SERVICE_CLIENT = object()
_SENTINEL_PRINCIPAL_CLIENT = object()


def _install_recording_pql(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list]:
    """Wire the recording PQL + factory spies; return a record dict.

    The factories are patched to *two-positional-arg* callables so a
    mutant that drops or reorders an argument is observable either as a
    captured-args mismatch or as a raised ``TypeError``.
    """
    record: dict[str, list] = {"soyuz": [], "principal": []}

    def _make_soyuz(settings):  # noqa: ANN001 — recorder
        record["soyuz"].append(settings)
        return _SENTINEL_SERVICE_CLIENT

    def _make_principal(settings, principal):  # noqa: ANN001 — recorder
        record["principal"].append((settings, principal))
        return _SENTINEL_PRINCIPAL_CLIENT

    _RecordingPQL.init_kwargs = {}
    _RecordingPQL.init_has_client = False
    _RecordingPQL.init_has_settings = False
    _RecordingPQL.calls = []
    _RecordingPQL.metrics_for = {}
    _RecordingPQL.default_metrics = {"num_deleted_rows": 0}

    monkeypatch.setattr("pointlessql.pql.PQL", _RecordingPQL)
    monkeypatch.setattr("pointlessql.services.soyuz_client.make_soyuz_client", _make_soyuz)
    monkeypatch.setattr("pointlessql.services.soyuz_client.make_principal_client", _make_principal)
    return record


def _orders_dp(schema: str) -> int:
    return _seed_dp(
        "main",
        schema,
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )


# ---------------------------------------------------------------------------
# execute_forget — empty-input guard (OR, not AND) + error messages
# ---------------------------------------------------------------------------


def test_execute_forget_empty_column_present_value_raises_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty column with a present value still trips the OR guard."""
    dp_id = _orders_dp("fe_guard_or")
    _install_recording_pql(monkeypatch)
    with pytest.raises(ValueError) as exc:
        execute_forget(
            _factory(),
            None,
            data_product_id=dp_id,
            catalog="main",
            schema="fe_guard_or",
            subject_column="   ",
            subject_value="present",
            declared_tables=[("orders", ["customer_id"])],
            principal=None,
        )
    # The exact required-field message — distinguishes the OR->AND flip
    # (which would fall through to the undeclared-column error) and any
    # message-string mutation.
    assert str(exc.value) == "subject_column and subject_value are required"
    assert _RecordingPQL.calls == []


def test_execute_forget_empty_value_present_column_raises_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dp_id = _orders_dp("fe_guard_val")
    _install_recording_pql(monkeypatch)
    with pytest.raises(ValueError) as exc:
        execute_forget(
            _factory(),
            None,
            data_product_id=dp_id,
            catalog="main",
            schema="fe_guard_val",
            subject_column="customer_id",
            subject_value="",
            declared_tables=[("orders", ["customer_id"])],
            principal=None,
        )
    assert str(exc.value) == "subject_column and subject_value are required"
    assert _RecordingPQL.calls == []


# ---------------------------------------------------------------------------
# execute_forget — client / PQL constructor wiring
# ---------------------------------------------------------------------------


def test_execute_forget_service_client_wired_when_no_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no principal the service client is built and handed to PQL."""
    dp_id = _orders_dp("fe_svc")
    record = _install_recording_pql(monkeypatch)
    settings = object()
    execute_forget(
        _factory(),
        settings,
        data_product_id=dp_id,
        catalog="main",
        schema="fe_svc",
        subject_column="customer_id",
        subject_value="abc",
        declared_tables=[("orders", ["customer_id"])],
        principal=None,
    )
    # The service factory ran with the real settings (not None), the
    # principal factory did not run, and PQL received the resulting
    # client + settings under both kwargs.
    assert record["soyuz"] == [settings]
    assert record["principal"] == []
    assert _RecordingPQL.init_kwargs["client"] is _SENTINEL_SERVICE_CLIENT
    assert _RecordingPQL.init_kwargs["settings"] is settings
    assert _RecordingPQL.init_has_client is True
    assert _RecordingPQL.init_has_settings is True


def test_execute_forget_principal_client_wired_with_settings_and_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A principal routes through the principal factory with both args."""
    dp_id = _orders_dp("fe_principal")
    record = _install_recording_pql(monkeypatch)
    settings = object()
    execute_forget(
        _factory(),
        settings,
        data_product_id=dp_id,
        catalog="main",
        schema="fe_principal",
        subject_column="customer_id",
        subject_value="abc",
        declared_tables=[("orders", ["customer_id"])],
        principal="alice@example.com",
    )
    # The principal factory is called exactly once with (settings,
    # principal) in that order — pins arg presence, value, and order.
    assert record["soyuz"] == []
    assert record["principal"] == [(settings, "alice@example.com")]
    # PQL got the principal client (not the service one, not None).
    assert _RecordingPQL.init_kwargs["client"] is _SENTINEL_PRINCIPAL_CLIENT
    assert _RecordingPQL.init_kwargs["settings"] is settings


# ---------------------------------------------------------------------------
# execute_forget — cross-table delete accumulator + summary
# ---------------------------------------------------------------------------


def test_execute_forget_sums_deletes_across_multiple_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row counter accumulates across tables (+=, not overwrite)."""
    dp_id = _seed_dp(
        "main",
        "fe_multi",
        tables=[
            {"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]},
            {"name": "events", "columns": [{"name": "customer_id", "type": "string"}]},
        ],
    )
    record = _install_recording_pql(monkeypatch)
    # Distinct per-table counts so a "keep only the last" mutant differs
    # from the true sum.
    _RecordingPQL.metrics_for = {
        "orders": {"num_deleted_rows": 3},
        "events": {"num_deleted_rows": 4},
    }
    settings = object()
    summary = execute_forget(
        _factory(),
        settings,
        data_product_id=dp_id,
        catalog="main",
        schema="fe_multi",
        subject_column="customer_id",
        subject_value="abc",
        declared_tables=[("orders", ["customer_id"]), ("events", ["customer_id"])],
        principal=None,
    )
    # 3 + 4 = 7, not 4 (the last table alone).
    assert summary["rows_deleted"] == 7
    assert summary["tables_affected"] == [
        {"table": "orders", "rows_deleted": 3},
        {"table": "events", "rows_deleted": 4},
    ]
    assert record["principal"] == []
    # The persisted ledger row also carries the accumulated total.
    with _factory()() as session:
        stored = session.get(DataProductForgetRequest, summary["request_id"])
        assert stored is not None
        assert stored.rows_deleted == 7


def test_execute_forget_stamps_executed_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ledger row records a non-null executed_at on completion."""
    dp_id = _orders_dp("fe_stamp")
    _install_recording_pql(monkeypatch)
    _RecordingPQL.metrics_for = {"orders": {"num_deleted_rows": 2}}
    summary = execute_forget(
        _factory(),
        object(),
        data_product_id=dp_id,
        catalog="main",
        schema="fe_stamp",
        subject_column="customer_id",
        subject_value="abc",
        declared_tables=[("orders", ["customer_id"])],
        principal=None,
    )
    with _factory()() as session:
        stored = session.get(DataProductForgetRequest, summary["request_id"])
        assert stored is not None
        # executed_at is stamped (not left None) when the op runs.
        assert stored.executed_at is not None


def test_execute_forget_hash_mismatch_exact_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Executing a proposal with a wrong value raises the exact message."""
    dp_id = _orders_dp("fe_msg")
    proposal = propose_forget(
        _factory(),
        data_product_id=dp_id,
        subject_column="customer_id",
        subject_value="real-subject",
    )
    _install_recording_pql(monkeypatch)
    with pytest.raises(ValueError) as exc:
        execute_forget(
            _factory(),
            None,
            data_product_id=dp_id,
            catalog="main",
            schema="fe_msg",
            subject_column="customer_id",
            subject_value="wrong-subject",
            declared_tables=[("orders", ["customer_id"])],
            principal=None,
            request_id=proposal.id,
        )
    # Exact wording pins the message-wrapping mutation, which a substring
    # match would let through.
    assert str(exc.value) == "supplied subject value does not match the proposed request"
    assert _RecordingPQL.calls == []


# ---------------------------------------------------------------------------
# hash_subject — empty-hash fallback string
# ---------------------------------------------------------------------------


def test_hash_subject_falls_back_to_empty_string_not_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the hasher yields a falsy value, the stored hash is ''."""
    dp_id = _seed_dp("main", "fp_emptyhash")
    # Force the underlying hasher to a falsy result so the ``or ""``
    # fallback is exercised.
    monkeypatch.setattr(
        "pointlessql.services.governance._forget.hash_value",
        lambda _v, *, secret: None,
    )
    row = propose_forget(
        _factory(),
        data_product_id=dp_id,
        subject_column="customer_id",
        subject_value="anything",
    )
    # The fallback is the empty string, not a placeholder token.
    assert row.subject_value_hash == ""
    with _factory()() as session:
        stored = session.get(DataProductForgetRequest, row.id)
        assert stored is not None
        assert stored.subject_value_hash == ""


# ---------------------------------------------------------------------------
# list_forget_requests — newest-first ordering
# ---------------------------------------------------------------------------


def test_list_forget_requests_is_ordered_newest_first() -> None:
    """The ledger is sorted by created_at descending, not insertion order."""
    dp_id = _seed_dp("main", "fl_order")
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    # Insert in ascending-time order; the correct query returns them
    # reversed.  An order_by(None) mutant would surface insertion order.
    ids: list[int] = []
    with _factory()() as session:
        for i in range(3):
            r = DataProductForgetRequest(
                data_product_id=dp_id,
                subject_column="customer_id",
                subject_value_hash=f"h{i}",
                status="proposed",
                tables_affected_json="[]",
                created_at=base + datetime.timedelta(days=i),
            )
            session.add(r)
            session.flush()
            ids.append(r.id)
        session.commit()
    rows = list_forget_requests(_factory(), data_product_id=dp_id)
    # Newest created_at first => reverse of insertion order.
    assert [row.id for row in rows] == list(reversed(ids))


# ---------------------------------------------------------------------------
# propose_forget — exact required-field message
# ---------------------------------------------------------------------------


def test_propose_forget_empty_column_raises_exact_required_message() -> None:
    """An empty column trips the guard with the verbatim message text."""
    dp_id = _seed_dp("main", "fp_msg_col")
    with pytest.raises(ValueError) as exc:
        propose_forget(
            _factory(),
            data_product_id=dp_id,
            subject_column="   ",
            subject_value="present",
        )
    # Exact wording pins the string-literal mutation that a substring
    # ("required") match would let through.
    assert str(exc.value) == "subject_column and subject_value are required"


def test_propose_forget_empty_value_raises_exact_required_message() -> None:
    """The symmetric empty-value case raises the same verbatim message."""
    dp_id = _seed_dp("main", "fp_msg_val")
    with pytest.raises(ValueError) as exc:
        propose_forget(
            _factory(),
            data_product_id=dp_id,
            subject_column="customer_id",
            subject_value="",
        )
    assert str(exc.value) == "subject_column and subject_value are required"
