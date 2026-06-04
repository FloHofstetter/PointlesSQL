"""Behaviour tests targeting surviving mutants in ``pointlessql.services.audit``.

These tests pin observable outputs of the audit-cockpit service
layer: the saved-query CRUD + safe-execute path
(:mod:`pointlessql.services.audit.saved_queries`), the saved-filter
CRUD path (:mod:`pointlessql.services.audit._saved_filters`), the
reverse-index ``runs by table`` queries
(:mod:`pointlessql.services.audit.by_table`), the Delta-direct read
instrumentation (:mod:`pointlessql.services.audit._read`), and the
audit-log retention sweep
(:mod:`pointlessql.services.audit._core`).

The fixtures reuse the in-memory SQLite engine + seeded workspace
wired by ``tests/conftest.py`` through ``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AuditLog,
    AuditSavedFilter,
    LineageValueChange,
    QueryHistory,
    QueryHistoryTable,
    SavedAuditQuery,
)
from pointlessql.services.audit import _core, _read, _saved_filters, by_table
from pointlessql.services.audit import saved_queries as sq
from pointlessql.types import QueryStatus, ReadKind


@pytest.fixture
def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


# ---------------------------------------------------------------------
# make_slug
# ---------------------------------------------------------------------


def test_make_slug_is_lowercase_with_six_hex_suffix() -> None:
    slug = sq.make_slug("My Mixed CASE Title")
    # ``.upper()`` mutant would yield uppercase characters; the slug
    # must be entirely lowercase + hyphen + digits.
    assert slug == slug.lower()
    base, _, suffix = slug.rpartition("-")
    assert base == "my-mixed-case-title"
    # ``token_hex(3)`` → 6 hex chars; a ``token_hex(4)`` mutant gives 8.
    assert len(suffix) == 6
    assert all(c in "0123456789abcdef" for c in suffix)


def test_make_slug_empty_title_falls_back_to_audit_query() -> None:
    slug = sq.make_slug("   ")
    base = slug.rpartition("-")[0]
    # Fallback literal must be lowercase ``audit-query`` (not the
    # ``AUDIT-QUERY`` / inverted-condition mutants).
    assert base == "audit-query"


def test_make_slug_empty_string_uses_default_base() -> None:
    slug = sq.make_slug("")
    assert slug.rpartition("-")[0] == "audit-query"


def test_make_slug_truncates_long_base_to_cap() -> None:
    # 300-char base; cap is 200-7=193, then a 7-char "-<hex>" suffix.
    slug = sq.make_slug("a" * 300)
    base = slug.rpartition("-")[0]
    # Off-by-one mutants on ``200 - 7`` (e.g. +7, -8) or ``>``→``>=``
    # change this length; pin it exactly.
    assert len(base) == 193
    assert len(slug) == 200


def test_make_slug_rstrip_trailing_hyphen_not_lstrip() -> None:
    # Title that sanitises to a trailing hyphen before truncation —
    # the cap lands exactly on a hyphen boundary so rstrip removes it.
    title = "a" * 192 + " " + "b" * 50
    slug = sq.make_slug(title)
    base = slug.rpartition("-")[0]
    # ``rstrip("-")`` removes the trailing hyphen left at the 193 cut;
    # an ``lstrip`` mutant would leave it and strip from the front.
    assert not base.endswith("-")
    assert base.startswith("a")


# ---------------------------------------------------------------------
# validate_sql
# ---------------------------------------------------------------------


def test_validate_sql_returns_referenced_table_set() -> None:
    referenced = sq.validate_sql("SELECT * FROM audit_log JOIN users ON 1=1")
    assert referenced == {"audit_log", "users"}


def test_validate_sql_empty_raises_with_message() -> None:
    with pytest.raises(ValidationError) as exc:
        sq.validate_sql("   ")
    assert str(exc.value) == "SQL text must not be empty"


def test_validate_sql_rejects_non_select() -> None:
    with pytest.raises(ValidationError) as exc:
        sq.validate_sql("DELETE FROM audit_log")
    assert str(exc.value) == "Only SELECT statements are allowed in saved audit queries"


def test_validate_sql_rejects_table_outside_allowlist() -> None:
    with pytest.raises(ValidationError) as exc:
        sq.validate_sql("SELECT * FROM secret_payroll")
    msg = str(exc.value)
    assert msg.startswith("SQL references tables outside the audit allow-list:")
    assert "secret_payroll" in msg


def test_validate_sql_allowlisted_select_returns_single_table() -> None:
    assert sq.validate_sql("SELECT id FROM agent_runs") == {"agent_runs"}


# ---------------------------------------------------------------------
# create
# ---------------------------------------------------------------------


def _factory() -> Any:
    return app.state.session_factory


def test_create_persists_expected_flags_and_fields() -> None:
    result = sq.create(
        _factory(),
        owner_id=42,
        title="My Query",
        description="  why it matters  ",
        sql_text="SELECT * FROM audit_log",
        alert_threshold_count=7,
    )
    # Persisted-column mutants (owner_id=None, is_shared=None/False,
    # is_starter=None, description=None, alert_threshold=None) all
    # change one of these observable serialised fields.
    assert result["owner_id"] == 42
    assert result["is_shared"] is True
    assert result["is_starter"] is False
    assert result["description"] == "why it matters"
    assert result["alert_threshold_count"] == 7
    assert result["sql_text"] == "SELECT * FROM audit_log"
    assert result["title"] == "My Query"


def test_create_empty_title_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as exc:
        sq.create(
            _factory(),
            owner_id=1,
            title="   ",
            description=None,
            sql_text="SELECT * FROM audit_log",
        )
    assert str(exc.value) == "Title must not be empty"


def test_create_invalid_sql_rejected_before_insert() -> None:
    with pytest.raises(ValidationError):
        sq.create(
            _factory(),
            owner_id=1,
            title="bad",
            description=None,
            sql_text="SELECT * FROM not_allowed_table",
        )
    # Nothing was inserted.
    with _factory()() as s:
        assert s.scalar(select(SavedAuditQuery)) is None


# ---------------------------------------------------------------------
# list_paginated
# ---------------------------------------------------------------------


def test_list_paginated_empty_db_total_is_zero() -> None:
    rows, total = sq.list_paginated(_factory())
    # ``or 0`` → ``or 1`` mutant would report 1 on an empty DB.
    assert rows == []
    assert total == 0


def test_list_paginated_limit_one_returns_single_row() -> None:
    sq.bootstrap_starter_rows(_factory())
    rows, total = sq.list_paginated(_factory(), offset=0, limit=1)
    # ``max(limit, 1)`` → ``max(limit, 2)`` mutant would return 2 rows.
    assert len(rows) == 1
    assert total >= 5  # five starter rows seeded


def test_list_paginated_total_counts_all_rows() -> None:
    sq.bootstrap_starter_rows(_factory())
    _rows, total = sq.list_paginated(_factory(), offset=0, limit=2)
    with _factory()() as s:
        actual = len(list(s.scalars(select(SavedAuditQuery))))
    assert total == actual


# ---------------------------------------------------------------------
# execute — truncation boundary + result shape
# ---------------------------------------------------------------------


def _create_query(sql_text: str) -> str:
    row = sq.create(
        _factory(),
        owner_id=1,
        title="run me",
        description=None,
        sql_text=sql_text,
    )
    return row["slug"]


def _seed_saved_queries(n: int) -> None:
    """Insert ``n`` extra non-starter saved_audit_queries rows."""
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as s:
        for i in range(n):
            s.add(
                SavedAuditQuery(
                    slug=f"seed-{i}-{uuid.uuid4().hex[:6]}",
                    title=f"seed {i}",
                    description=None,
                    sql_text="SELECT 1",
                    owner_id=1,
                    is_shared=True,
                    is_starter=False,
                    alert_threshold_count=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        s.commit()


def test_execute_not_truncated_when_rows_under_cap() -> None:
    # Three rows in saved_audit_queries; cap is 5 → no truncation.
    _seed_saved_queries(3)
    slug = _create_query("SELECT id FROM saved_audit_queries")
    result = sq.execute(_factory(), slug, row_cap=5)
    assert result is not None
    # ``truncated = True`` (unconditional) mutant would flip this.
    assert result["truncated"] is False
    assert result["row_count"] == result["row_count"]  # sanity


def test_execute_truncates_when_rows_exceed_cap() -> None:
    _seed_saved_queries(4)
    slug = _create_query("SELECT id FROM saved_audit_queries")
    # saved_audit_queries now holds 4 seeds + 1 (the query itself) = 5.
    result = sq.execute(_factory(), slug, row_cap=2)
    assert result is not None
    assert result["truncated"] is True
    assert result["row_count"] == 2  # sliced to the cap


def test_execute_exact_cap_is_not_truncated() -> None:
    # Boundary: len(all_rows) == row_cap must NOT truncate
    # (``>`` vs ``>=`` mutant).
    _seed_saved_queries(2)
    slug = _create_query("SELECT id FROM saved_audit_queries")
    # Total rows in saved_audit_queries = 2 seeds + 1 (this query) = 3.
    with _factory()() as s:
        total = len(list(s.scalars(select(SavedAuditQuery))))
    result = sq.execute(_factory(), slug, row_cap=total)
    assert result is not None
    assert result["row_count"] == total
    assert result["truncated"] is False


def test_execute_result_dict_keys_and_referenced_tables() -> None:
    slug = _create_query("SELECT id FROM audit_log")
    result = sq.execute(_factory(), slug)
    assert result is not None
    # Key-rename mutants (slug→SLUG, referenced_tables→REFERENCED_TABLES)
    # would change this key set.
    assert set(result.keys()) == {
        "slug",
        "columns",
        "rows",
        "row_count",
        "truncated",
        "referenced_tables",
    }
    assert result["slug"] == slug
    assert result["referenced_tables"] == ["audit_log"]


def test_execute_unknown_slug_returns_none() -> None:
    assert sq.execute(_factory(), "does-not-exist") is None


# ---------------------------------------------------------------------
# _read.record_read — kwargs forwarded to record_query
# ---------------------------------------------------------------------


def test_record_read_none_factory_is_silent_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    called = MagicMock()
    monkeypatch.setattr(_read, "record_query", called)
    out = _read.record_read(
        None,
        table_fqn="c.s.t",
        started_at=datetime.datetime.now(datetime.UTC),
        finished_at=datetime.datetime.now(datetime.UTC),
    )
    assert out is None
    called.assert_not_called()


def test_record_read_forwards_exact_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_record_query(factory: Any, **kwargs: Any) -> int:
        captured["factory"] = factory
        captured.update(kwargs)
        return 99

    monkeypatch.setattr(_read, "record_query", fake_record_query)
    factory = _factory()
    started = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    finished = datetime.datetime(2024, 1, 2, tzinfo=datetime.UTC)
    result = _read.record_read(
        factory,
        table_fqn="cat.sch.tbl",
        read_kind=ReadKind.ENGINE_DIRECT,
        agent_run_id="run-123",
        principal="alice@example.com",
        started_at=started,
        finished_at=finished,
        status=QueryStatus.SUCCEEDED,
        row_count=17,
        duration_ms=42,
        error_message="boom",
    )
    assert result == 99
    # Each of these pins one record_query kwarg the mutants null out.
    assert captured["factory"] is factory
    assert captured["user_id"] == 0
    assert captured["user_email"] == "alice@example.com"
    assert captured["sql_text"] == "SELECT * FROM cat.sch.tbl"
    assert captured["started_at"] == started
    assert captured["finished_at"] == finished
    assert captured["status"] == QueryStatus.SUCCEEDED
    assert captured["row_count"] == 17
    assert captured["duration_ms"] == 42
    assert captured["referenced_tables"] == ["cat.sch.tbl"]
    assert captured["error_message"] == "boom"
    assert str(captured["agent_run_id"]) == "run-123"
    assert captured["read_kind"] == ReadKind.ENGINE_DIRECT


def test_record_read_defaults_principal_to_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POINTLESSQL_PRINCIPAL", raising=False)
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        _read,
        "record_query",
        lambda factory, **kwargs: captured.update(kwargs) or 1,
    )
    _read.record_read(
        _factory(),
        table_fqn="c.s.t",
        started_at=datetime.datetime.now(datetime.UTC),
        finished_at=datetime.datetime.now(datetime.UTC),
    )
    # ``"system"`` default (not ``"SYSTEM"`` / wrong env key).
    assert captured["user_email"] == "system"


def test_resolve_principal_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POINTLESSQL_PRINCIPAL", "bob@example.com")
    assert _read._resolve_principal(None) == "bob@example.com"
    # Explicit arg wins over env.
    assert _read._resolve_principal("explicit@x.com") == "explicit@x.com"


def test_resolve_principal_default_when_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POINTLESSQL_PRINCIPAL", raising=False)
    assert _read._resolve_principal(None) == "system"


# ---------------------------------------------------------------------
# by_table — kind dispatch + since/until boundary
# ---------------------------------------------------------------------


def _seed_run(
    *,
    run_id: str,
    started_at: datetime.datetime,
    tables_touched: str | None = None,
    principal: str = "alice@example.com",
) -> None:
    with _factory()() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal=principal,
                agent_id="etl",
                notebook_path="nb.py",
                status="succeeded",
                tables_touched=tables_touched,
                started_at=started_at,
                finished_at=started_at,
            )
        )
        s.commit()


def test_runs_by_table_invalid_kind_raises_value_error() -> None:
    with pytest.raises(ValueError) as exc:
        by_table.runs_by_table(_factory(), fqn="c.s.t", kind="bogus")  # type: ignore[arg-type]
    assert "bogus" in str(exc.value)


def test_runs_by_table_touched_matches_only_quoted_fqn() -> None:
    today = datetime.datetime.now(datetime.UTC)
    _seed_run(
        run_id=str(uuid.uuid4()),
        started_at=today,
        tables_touched='["cat.sch.target"]',
    )
    _seed_run(
        run_id=str(uuid.uuid4()),
        started_at=today,
        tables_touched='["cat.sch.other"]',
    )
    rows = by_table.runs_by_table(_factory(), fqn="cat.sch.target", kind="touched")
    assert len(rows) == 1
    assert rows[0]["tables_touched"] == ["cat.sch.target"]


def test_runs_by_table_since_is_inclusive_until_is_exclusive() -> None:
    base = datetime.datetime(2024, 6, 1, 12, 0, tzinfo=datetime.UTC)
    before = base - datetime.timedelta(hours=1)
    at_since = base
    at_until = base + datetime.timedelta(hours=2)
    ids = {
        "before": str(uuid.uuid4()),
        "at_since": str(uuid.uuid4()),
        "at_until": str(uuid.uuid4()),
    }
    touched = '["cat.sch.t"]'
    _seed_run(run_id=ids["before"], started_at=before, tables_touched=touched)
    _seed_run(run_id=ids["at_since"], started_at=at_since, tables_touched=touched)
    _seed_run(run_id=ids["at_until"], started_at=at_until, tables_touched=touched)

    rows = by_table.runs_by_table(
        _factory(),
        fqn="cat.sch.t",
        kind="touched",
        since=at_since,
        until=at_until,
    )
    got = {r["id"] for r in rows}
    # since is ``>=`` (inclusive) → at_since IN; ``>`` mutant drops it.
    # until is ``<`` (exclusive) → at_until OUT; ``<=`` mutant adds it.
    # before is < since → always out.
    assert got == {ids["at_since"]}


def test_runs_by_table_written_via_op_and_value_change() -> None:
    today = datetime.datetime.now(datetime.UTC)
    op_run = str(uuid.uuid4())
    vc_run = str(uuid.uuid4())
    other_run = str(uuid.uuid4())
    _seed_run(run_id=op_run, started_at=today)
    _seed_run(run_id=vc_run, started_at=today)
    _seed_run(run_id=other_run, started_at=today)
    with _factory()() as s:
        s.add(
            AgentRunOperation(
                agent_run_id=op_run,
                ordinal=1,
                op_name="merge",
                params_json="{}",
                target_table="cat.sch.written",
                rows_affected=1,
                started_at=today,
                finished_at=today,
            )
        )
        # The value-change axis needs a backing op row (op_id is NOT
        # NULL); point it at a different table so only the value-change
        # axis — not the op axis — surfaces vc_run for cat.sch.written.
        vc_op = AgentRunOperation(
            agent_run_id=vc_run,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="cat.sch.elsewhere",
            rows_affected=1,
            started_at=today,
            finished_at=today,
        )
        s.add(vc_op)
        s.flush()
        s.add(
            LineageValueChange(
                run_id=vc_run,
                op_id=vc_op.id,
                target_table="cat.sch.written",
                target_row_id="r0",
                target_column="email",
                old_value="a",
                new_value="b",
                created_at=today,
            )
        )
        s.commit()
    rows = by_table.runs_by_table(_factory(), fqn="cat.sch.written", kind="written")
    got = {r["id"] for r in rows}
    # Both the op-axis run and the value-change-axis run surface;
    # the unrelated run does not.
    assert got == {op_run, vc_run}


def test_runs_by_table_read_via_query_history() -> None:
    today = datetime.datetime.now(datetime.UTC)
    read_run = str(uuid.uuid4())
    other_run = str(uuid.uuid4())
    _seed_run(run_id=read_run, started_at=today)
    _seed_run(run_id=other_run, started_at=today)
    with _factory()() as s:
        qh = QueryHistory(
            user_id=1,
            user_email="alice@example.com",
            sql_text="SELECT * FROM cat.sch.readtbl",
            started_at=today,
            finished_at=today,
            status="succeeded",
            agent_run_id=read_run,
            read_kind="pql_table",
        )
        s.add(qh)
        s.flush()
        s.add(
            QueryHistoryTable(
                query_history_id=qh.id,
                full_name="cat.sch.readtbl",
                access_type="read",
            )
        )
        s.commit()
    rows = by_table.runs_by_table(_factory(), fqn="cat.sch.readtbl", kind="read")
    got = {r["id"] for r in rows}
    assert got == {read_run}


def test_runs_by_table_dispatch_routes_to_correct_kind() -> None:
    # Same fqn appears in a touched run and a written run; each kind
    # must return only its own axis (guards the kind→helper dispatch
    # and the since/until/limit forwarding mutants).
    today = datetime.datetime.now(datetime.UTC)
    touched_run = str(uuid.uuid4())
    written_run = str(uuid.uuid4())
    _seed_run(run_id=touched_run, started_at=today, tables_touched='["cat.sch.x"]')
    _seed_run(run_id=written_run, started_at=today)
    with _factory()() as s:
        s.add(
            AgentRunOperation(
                agent_run_id=written_run,
                ordinal=1,
                op_name="merge",
                params_json="{}",
                target_table="cat.sch.x",
                rows_affected=1,
                started_at=today,
                finished_at=today,
            )
        )
        s.commit()
    touched = {r["id"] for r in by_table.runs_by_table(_factory(), fqn="cat.sch.x", kind="touched")}
    written = {r["id"] for r in by_table.runs_by_table(_factory(), fqn="cat.sch.x", kind="written")}
    assert touched == {touched_run}
    assert written == {written_run}


# ---------------------------------------------------------------------
# _saved_filters — CRUD + auth + workspace logic
# ---------------------------------------------------------------------


def _admin_user_id() -> int:
    """Return the seeded admin test user's id."""
    from pointlessql.models import User

    with _factory()() as s:
        user = s.scalar(select(User).where(User.email == "test@test.com"))
        assert user is not None
        return user.id


def test_create_filter_persists_fields() -> None:
    uid = _admin_user_id()
    entry = _saved_filters.create_filter(
        _factory(),
        owner_user_id=uid,
        name="  my filter  ",
        filters={"principal": "alice"},
        is_shared_workspace=True,
        workspace_id=1,
    )
    assert entry["name"] == "my filter"
    assert entry["filters"] == {"principal": "alice"}
    assert entry["is_shared_workspace"] is True
    assert entry["workspace_id"] == 1


def test_create_filter_private_does_not_pin_workspace() -> None:
    uid = _admin_user_id()
    entry = _saved_filters.create_filter(
        _factory(),
        owner_user_id=uid,
        name="private",
        filters={},
        is_shared_workspace=False,
        workspace_id=5,
    )
    # ``workspace_id if is_shared_workspace else None`` → private filter
    # must drop the workspace pin.
    assert entry["is_shared_workspace"] is False
    assert entry["workspace_id"] is None


def test_create_filter_empty_name_raises() -> None:
    uid = _admin_user_id()
    with pytest.raises(ValueError) as exc:
        _saved_filters.create_filter(
            _factory(),
            owner_user_id=uid,
            name="   ",
            filters={},
        )
    assert str(exc.value) == "saved filter name cannot be empty"


def test_create_filter_default_is_not_shared() -> None:
    uid = _admin_user_id()
    entry = _saved_filters.create_filter(
        _factory(),
        owner_user_id=uid,
        name="defaults",
        filters={},
    )
    # ``is_shared_workspace: bool = False`` default — a ``True`` mutant
    # would flip this.
    assert entry["is_shared_workspace"] is False


def _make_filter(uid: int, name: str = "f") -> int:
    entry = _saved_filters.create_filter(
        _factory(),
        owner_user_id=uid,
        name=name,
        filters={"a": 1},
    )
    return entry["id"]


def test_update_filter_persists_json_payload() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    out = _saved_filters.update_filter(
        _factory(),
        filter_id=fid,
        actor_user_id=uid,
        filters={"new": "value"},
    )
    # ``filters_json = None`` / ``json.dumps(None)`` mutants would
    # corrupt this round-trip.
    assert out["filters"] == {"new": "value"}


def test_update_filter_only_updates_filters_when_not_none() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    out = _saved_filters.update_filter(
        _factory(),
        filter_id=fid,
        actor_user_id=uid,
        name="renamed",
        filters=None,
    )
    # ``if filters is not None`` inverted mutant would overwrite the
    # original payload with ``json.dumps(None)``; the original stays.
    assert out["name"] == "renamed"
    assert out["filters"] == {"a": 1}


def test_update_filter_unshare_clears_workspace() -> None:
    uid = _admin_user_id()
    entry = _saved_filters.create_filter(
        _factory(),
        owner_user_id=uid,
        name="shared",
        filters={},
        is_shared_workspace=True,
        workspace_id=1,
    )
    out = _saved_filters.update_filter(
        _factory(),
        filter_id=entry["id"],
        actor_user_id=uid,
        is_shared_workspace=False,
    )
    # ``if not is_shared_workspace: workspace_id = None`` — un-sharing
    # must null the workspace.
    assert out["is_shared_workspace"] is False
    assert out["workspace_id"] is None


def test_update_filter_not_owner_raises_authorization() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    with pytest.raises(AuthorizationError) as exc:
        _saved_filters.update_filter(
            _factory(),
            filter_id=fid,
            actor_user_id=uid + 999,
        )
    # The privilege string is observable on the raised error.
    assert exc.value.privilege == "audit-saved-filter-edit"


def test_update_filter_missing_id_raises_not_found() -> None:
    uid = _admin_user_id()
    with pytest.raises(ResourceNotFoundError):
        _saved_filters.update_filter(
            _factory(),
            filter_id=987654,
            actor_user_id=uid,
        )


def test_delete_filter_not_owner_raises_authorization() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    with pytest.raises(AuthorizationError) as exc:
        _saved_filters.delete_filter(
            _factory(),
            filter_id=fid,
            actor_user_id=uid + 999,
        )
    assert exc.value.privilege == "audit-saved-filter-delete"
    # Row survived the rejected delete.
    with _factory()() as s:
        assert s.get(AuditSavedFilter, fid) is not None


def test_delete_filter_owner_removes_row() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    _saved_filters.delete_filter(_factory(), filter_id=fid, actor_user_id=uid)
    with _factory()() as s:
        assert s.get(AuditSavedFilter, fid) is None


def test_list_for_user_owner_or_shared_in_workspace() -> None:
    uid = _admin_user_id()
    other = uid + 500
    # owner-private (mine), shared-in-ws-1 (other), shared-in-ws-2 (other).
    _saved_filters.create_filter(_factory(), owner_user_id=uid, name="mine", filters={})
    _saved_filters.create_filter(
        _factory(),
        owner_user_id=other,
        name="shared-ws1",
        filters={},
        is_shared_workspace=True,
        workspace_id=1,
    )
    _saved_filters.create_filter(
        _factory(),
        owner_user_id=other,
        name="shared-ws2",
        filters={},
        is_shared_workspace=True,
        workspace_id=2,
    )
    names = {
        e["name"] for e in _saved_filters.list_for_user(_factory(), user_id=uid, workspace_id=1)
    }
    # OR (mine) | (shared AND workspace==1).  The ``&``→``|`` and
    # ``==``→``!=`` mutants on the workspace clause change this set.
    assert names == {"mine", "shared-ws1"}


# ---------------------------------------------------------------------
# _core.cleanup_old_entries — retention boundary
# ---------------------------------------------------------------------


def _seed_audit_row(created_at: datetime.datetime, action: str) -> None:
    with _factory()() as s:
        s.add(
            AuditLog(
                workspace_id=1,
                user_id=1,
                user_email="a@x.com",
                actor_role="user",
                action=action,
                target="t",
                client_ip=None,
                detail=None,
                created_at=created_at,
            )
        )
        s.commit()


def test_cleanup_old_entries_prunes_rows_older_than_retention() -> None:
    now = datetime.datetime.now(datetime.UTC)
    _seed_audit_row(now - datetime.timedelta(days=10), "old")
    _seed_audit_row(now, "fresh")
    deleted = _core.cleanup_old_entries(_factory(), retention_days=1)
    assert deleted == 1
    with _factory()() as s:
        remaining = {r.action for r in s.scalars(select(AuditLog))}
    assert remaining == {"fresh"}


def test_cleanup_old_entries_zero_retention_keeps_everything() -> None:
    now = datetime.datetime.now(datetime.UTC)
    _seed_audit_row(now - datetime.timedelta(days=100), "ancient")
    # ``retention_days <= 0`` disables retention; ``<= 1`` mutant would
    # also disable for retention_days=1, but here 0 means keep-all.
    deleted = _core.cleanup_old_entries(_factory(), retention_days=0)
    assert deleted == 0
    with _factory()() as s:
        assert s.scalar(select(AuditLog)) is not None


def test_cleanup_old_entries_retention_one_still_prunes() -> None:
    # Guards the ``<= 0`` → ``<= 1`` boundary mutant: retention_days=1
    # must NOT be treated as "disabled" — old rows still get pruned.
    now = datetime.datetime.now(datetime.UTC)
    _seed_audit_row(now - datetime.timedelta(days=5), "stale")
    deleted = _core.cleanup_old_entries(_factory(), retention_days=1)
    assert deleted == 1
