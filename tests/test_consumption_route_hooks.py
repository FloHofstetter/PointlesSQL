"""Route-layer D2 consumption-enforcement: dep + hook + audit (Phase 134.1)."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest
from sqlalchemy import select
from starlette.datastructures import Headers, QueryParams

from pointlessql.api._consumption_hook import enforce_consumption_for_read
from pointlessql.api.dependencies import get_authoring_product
from pointlessql.api.main import app
from pointlessql.models import (
    AuditLog,
    DataProduct,
    DataProductInputPort,
    DataProductPolicy,
    WorkspaceGovernancePolicy,
)
from pointlessql.services.governance import (
    CONSUMPTION_BLOCKED_ACTION,
    CONSUMPTION_UNDECLARED_ACTION,
    ConsumptionViolation,
)
from pointlessql.types import UserInfo


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": [],
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


def _add_upstream(consumer_id: int, source_ref: str) -> None:
    with _factory()() as session:
        session.add(
            DataProductInputPort(
                data_product_id=consumer_id,
                name=f"in_{source_ref.replace('.', '_')}",
                kind="upstream_product",
                source_ref=source_ref,
                description="",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


def _set_product_mode(product_id: int, mode: str) -> None:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        row = session.scalar(
            select(DataProductPolicy).where(DataProductPolicy.data_product_id == product_id)
        )
        if row is None:
            row = DataProductPolicy(
                data_product_id=product_id,
                consumption_enforcement=mode,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.consumption_enforcement = mode
            row.updated_at = now
        session.commit()


def _set_workspace_mode(workspace_id: int, mode: str) -> None:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        row = session.scalar(
            select(WorkspaceGovernancePolicy).where(
                WorkspaceGovernancePolicy.workspace_id == workspace_id
            )
        )
        if row is None:
            row = WorkspaceGovernancePolicy(
                workspace_id=workspace_id,
                consumption_enforcement=mode,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.consumption_enforcement = mode
            row.updated_at = now
        session.commit()


def _fake_request(
    *,
    header: str | None = None,
    query: str | None = None,
    state_product: int | None = None,
) -> Any:
    """Construct a minimal Request-like object for dep / hook tests."""

    class _State:
        pass

    class _Client:
        host = "127.0.0.1"

    headers_dict: dict[str, str] = {}
    if header is not None:
        headers_dict["x-pointlessql-authoring-product"] = header
    query_str = f"as_product={query}" if query is not None else ""

    class _Request:
        def __init__(self) -> None:
            self.headers = Headers(headers_dict)
            self.query_params = QueryParams(query_str)
            self.state = _State()
            self.app = app
            self.client = _Client()
            if state_product is not None:
                self.state.authoring_data_product_id = state_product

    return _Request()


def _user(
    *, user_id: int = 1, email: str = "tester@example.com", is_admin: bool = False
) -> UserInfo:
    return UserInfo(
        id=user_id,
        email=email,
        display_name="Tester",
        is_admin=is_admin,
        is_supervisor=False,
        is_auditor=False,
    )


# ---------------------------------------------------------------------------
# get_authoring_product dep
# ---------------------------------------------------------------------------


def test_dep_header_resolves_product() -> None:
    pid = _seed_dp("cons", "hdr")
    request = _fake_request(header="cons.hdr")
    assert get_authoring_product(request) == pid


def test_dep_header_unknown_product_returns_none() -> None:
    request = _fake_request(header="nope.nada")
    assert get_authoring_product(request) is None


def test_dep_query_param_resolves_product() -> None:
    pid = _seed_dp("cons", "qry")
    request = _fake_request(query="cons.qry")
    assert get_authoring_product(request) == pid


def test_dep_state_takes_over_when_no_header_or_query() -> None:
    request = _fake_request(state_product=42)
    assert get_authoring_product(request) == 42


def test_dep_missing_returns_none() -> None:
    request = _fake_request()
    assert get_authoring_product(request) is None


def test_dep_malformed_header_returns_none() -> None:
    request = _fake_request(header="not_dotted")
    assert get_authoring_product(request) is None


def test_dep_header_beats_state() -> None:
    pid = _seed_dp("cons", "prio")
    request = _fake_request(header="cons.prio", state_product=999)
    assert get_authoring_product(request) == pid


# ---------------------------------------------------------------------------
# enforce_consumption_for_read hook
# ---------------------------------------------------------------------------


def _count_actions(action: str) -> int:
    with _factory()() as session:
        rows = session.scalars(select(AuditLog).where(AuditLog.action == action)).all()
        return len(rows)


def test_hook_noop_when_no_authoring_product() -> None:
    before = _count_actions(CONSUMPTION_UNDECLARED_ACTION)
    enforce_consumption_for_read(
        _fake_request(),
        factory=_factory(),
        workspace_id=1,
        user=_user(),
        authoring_product_id=None,
        source_fqn="anything.goes.table",
    )
    assert _count_actions(CONSUMPTION_UNDECLARED_ACTION) == before


def test_hook_advisory_emits_audit_and_allows() -> None:
    pid = _seed_dp("cons", "advhook")
    _set_product_mode(pid, "advisory")
    before = _count_actions(CONSUMPTION_UNDECLARED_ACTION)
    enforce_consumption_for_read(
        _fake_request(),
        factory=_factory(),
        workspace_id=1,
        user=_user(),
        authoring_product_id=pid,
        source_fqn="raw.events.orders",
    )
    assert _count_actions(CONSUMPTION_UNDECLARED_ACTION) == before + 1


def test_hook_strict_blocks_and_emits_audit() -> None:
    pid = _seed_dp("cons", "strhook")
    _set_product_mode(pid, "strict")
    before_blocked = _count_actions(CONSUMPTION_BLOCKED_ACTION)
    with pytest.raises(ConsumptionViolation):
        enforce_consumption_for_read(
            _fake_request(),
            factory=_factory(),
            workspace_id=1,
            user=_user(),
            authoring_product_id=pid,
            source_fqn="forbidden.x.y",
        )
    assert _count_actions(CONSUMPTION_BLOCKED_ACTION) == before_blocked + 1


def test_hook_declared_passes_silently_no_audit() -> None:
    pid = _seed_dp("cons", "declhook")
    _set_product_mode(pid, "strict")
    _add_upstream(pid, "raw.events")
    before = _count_actions(CONSUMPTION_UNDECLARED_ACTION) + _count_actions(
        CONSUMPTION_BLOCKED_ACTION
    )
    enforce_consumption_for_read(
        _fake_request(),
        factory=_factory(),
        workspace_id=1,
        user=_user(),
        authoring_product_id=pid,
        source_fqn="raw.events.orders",
    )
    after = _count_actions(CONSUMPTION_UNDECLARED_ACTION) + _count_actions(
        CONSUMPTION_BLOCKED_ACTION
    )
    assert after == before


def test_hook_workspace_inheritance() -> None:
    pid = _seed_dp("cons", "wsinh")
    _set_workspace_mode(1, "strict")
    with pytest.raises(ConsumptionViolation):
        enforce_consumption_for_read(
            _fake_request(),
            factory=_factory(),
            workspace_id=1,
            user=_user(),
            authoring_product_id=pid,
            source_fqn="unrelated.thing.t",
        )
    # restore ws default
    _set_workspace_mode(1, "advisory")


def test_violation_status_code_and_extension_members() -> None:
    pid = _seed_dp("cons", "ext")
    _set_product_mode(pid, "strict")
    with pytest.raises(ConsumptionViolation) as excinfo:
        enforce_consumption_for_read(
            _fake_request(),
            factory=_factory(),
            workspace_id=1,
            user=_user(),
            authoring_product_id=pid,
            source_fqn="bad.bad.t",
        )
    err = excinfo.value
    assert err.status_code == 403
    extras = err.extension_members()
    assert extras is not None
    assert extras["mode"] == "strict"
    assert extras["consumer_product_id"] == pid
    assert extras["source"] == "bad.bad.t"
    assert extras["declared"] is False
