"""Behaviour tests targeting surviving mutants in ``_saved_filters``.

These pin observable outputs of the audit saved-filter CRUD layer
(:mod:`pointlessql.services.audit._saved_filters`): the row→entry
serialiser dict keys and fallbacks, the JSON payload encoding, the
owner-or-shared list query ordering, and the authorization /
not-found error envelopes raised by ``update_filter`` /
``delete_filter``.

The DB-backed tests reuse the in-memory SQLite engine + seeded
workspace/admin user wired by ``tests/conftest.py`` through
``app.state.session_factory``.  The pure-serialiser tests drive
``_row_to_entry`` with a lightweight attribute stub so falsy
``created_at`` can be exercised without a DB round-trip.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.exceptions import AuthorizationError, ResourceNotFoundError
from pointlessql.models import AuditSavedFilter
from pointlessql.services.audit import _saved_filters


def _factory() -> Any:
    return app.state.session_factory


def _admin_user_id() -> int:
    """Return the seeded admin test user's id."""
    from pointlessql.models import User

    with _factory()() as s:
        user = s.scalar(select(User).where(User.email == "test@test.com"))
        assert user is not None
        return user.id


class _StubRow:
    """Minimal attribute carrier matching ``AuditSavedFilter`` shape."""

    def __init__(
        self,
        *,
        id: int = 1,
        owner_user_id: int = 7,
        name: str = "n",
        filters_json: str = "{}",
        is_shared_workspace: bool = False,
        workspace_id: int | None = None,
        created_at: datetime.datetime | None = None,
    ) -> None:
        self.id = id
        self.owner_user_id = owner_user_id
        self.name = name
        self.filters_json = filters_json
        self.is_shared_workspace = is_shared_workspace
        self.workspace_id = workspace_id
        self.created_at = created_at


# ---------------------------------------------------------------------
# _row_to_entry — dict keys + created_at fallback
# ---------------------------------------------------------------------


def test_row_to_entry_uses_exact_dict_keys() -> None:
    row = _StubRow(
        id=3,
        owner_user_id=9,
        name="combo",
        filters_json='{"a": 1}',
        is_shared_workspace=True,
        workspace_id=4,
        created_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
    )
    entry = _saved_filters._row_to_entry(row)  # type: ignore[arg-type]
    # Key-rename mutants (created_at→CREATED_AT/XX..XX,
    # owner_user_id→OWNER_USER_ID/XX..XX) change this exact key set.
    assert set(entry.keys()) == {
        "id",
        "owner_user_id",
        "name",
        "filters",
        "is_shared_workspace",
        "workspace_id",
        "created_at",
    }
    assert entry["owner_user_id"] == 9
    assert entry["created_at"] == "2024-01-01T00:00:00+00:00"


def test_row_to_entry_created_at_none_falls_back_to_empty_string() -> None:
    row = _StubRow(created_at=None)
    entry = _saved_filters._row_to_entry(row)  # type: ignore[arg-type]
    # ``else ""`` fallback — a ``"XXXX"`` mutant would surface that
    # sentinel instead of the empty string.
    assert entry["created_at"] == ""


# ---------------------------------------------------------------------
# create_filter — JSON encoding of non-serialisable payloads
# ---------------------------------------------------------------------


def test_create_filter_serialises_non_json_values_via_str_default() -> None:
    uid = _admin_user_id()
    when = datetime.datetime(2024, 5, 6, 7, 8, 9, tzinfo=datetime.UTC)
    entry = _saved_filters.create_filter(
        _factory(),
        owner_user_id=uid,
        name="has-datetime",
        filters={"when": when},
    )
    # ``json.dumps(filters, default=str)`` lets a non-serialisable
    # ``datetime`` round-trip as its ``str(...)`` form; the
    # ``default=None`` / dropped-``default`` mutants would raise
    # ``TypeError`` instead of persisting the row.
    assert entry["filters"] == {"when": str(when)}


# ---------------------------------------------------------------------
# list_for_user — ordering by created_at desc
# ---------------------------------------------------------------------


def test_list_for_user_orders_by_created_at_descending() -> None:
    uid = _admin_user_id()
    base = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    # Insert three owner-private rows out of chronological order.
    with _factory()() as s:
        s.add(
            AuditSavedFilter(
                owner_user_id=uid,
                name="middle",
                filters_json="{}",
                is_shared_workspace=False,
                workspace_id=None,
                created_at=base + datetime.timedelta(days=2),
            )
        )
        s.add(
            AuditSavedFilter(
                owner_user_id=uid,
                name="oldest",
                filters_json="{}",
                is_shared_workspace=False,
                workspace_id=None,
                created_at=base,
            )
        )
        s.add(
            AuditSavedFilter(
                owner_user_id=uid,
                name="newest",
                filters_json="{}",
                is_shared_workspace=False,
                workspace_id=None,
                created_at=base + datetime.timedelta(days=4),
            )
        )
        s.commit()
    entries = _saved_filters.list_for_user(_factory(), user_id=uid, workspace_id=1)
    order = [e["name"] for e in entries]
    # ``.order_by(created_at.desc())`` — the ``.order_by(None)`` mutant
    # drops ordering, breaking this newest-first sequence.
    assert order == ["newest", "middle", "oldest"]


# ---------------------------------------------------------------------
# update_filter — JSON payload + workspace logic
# ---------------------------------------------------------------------


def _make_filter(uid: int, name: str = "f") -> int:
    entry = _saved_filters.create_filter(
        _factory(),
        owner_user_id=uid,
        name=name,
        filters={"a": 1},
    )
    return entry["id"]


def test_update_filter_serialises_non_json_values_via_str_default() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    when = datetime.datetime(2024, 9, 9, tzinfo=datetime.UTC)
    out = _saved_filters.update_filter(
        _factory(),
        filter_id=fid,
        actor_user_id=uid,
        filters={"when": when},
    )
    # ``json.dumps(filters, default=str)`` round-trips the datetime;
    # ``default=None`` / dropped-``default`` mutants raise instead.
    assert out["filters"] == {"when": str(when)}


def test_update_filter_share_sets_is_shared_true() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    out = _saved_filters.update_filter(
        _factory(),
        filter_id=fid,
        actor_user_id=uid,
        is_shared_workspace=True,
        workspace_id=3,
    )
    # ``row.is_shared_workspace = bool(is_shared_workspace)`` —
    # ``bool(None)`` mutant would force this to False.
    assert out["is_shared_workspace"] is True
    assert out["workspace_id"] == 3


def test_update_filter_workspace_pin_requires_shared() -> None:
    uid = _admin_user_id()
    # Owner-private filter (not shared).
    entry = _saved_filters.create_filter(
        _factory(),
        owner_user_id=uid,
        name="private",
        filters={},
        is_shared_workspace=False,
    )
    out = _saved_filters.update_filter(
        _factory(),
        filter_id=entry["id"],
        actor_user_id=uid,
        workspace_id=8,
    )
    # ``workspace_id is not None and (is_shared or row.is_shared)`` —
    # since the row is private and no share flag is passed, the pin
    # must NOT land.  The ``and``→``or`` mutant would set it; the
    # ``is not None``→``is None`` mutant would skip a real pin.
    assert out["workspace_id"] is None


def test_update_filter_shared_workspace_pin_lands() -> None:
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
        workspace_id=9,
    )
    # Row already shared → the pin applies and stores the new id.
    # The ``row.workspace_id = None`` mutant would null it; the
    # ``or``→``and`` mutant on the share clause would skip the assign
    # (only is_shared_workspace arg, not row flag, is checked there).
    assert out["workspace_id"] == 9


def test_update_filter_missing_id_message_names_the_id() -> None:
    uid = _admin_user_id()
    with pytest.raises(ResourceNotFoundError) as exc:
        _saved_filters.update_filter(
            _factory(),
            filter_id=424242,
            actor_user_id=uid,
        )
    # ``ResourceNotFoundError(f"saved filter id={filter_id} not found")``
    # — the ``ResourceNotFoundError(None)`` mutant loses the message.
    assert exc.value.detail == "saved filter id=424242 not found"


def test_update_filter_not_owner_error_carries_full_triple() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    with pytest.raises(AuthorizationError) as exc:
        _saved_filters.update_filter(
            _factory(),
            filter_id=fid,
            actor_user_id=uid + 999,
        )
    err = exc.value
    # Each of these pins one AuthorizationError kwarg the mutants null
    # out or mangle (principal=None/str(None), securable_type=None/
    # XX..XX/UPPER, full_name=None/str(None)).
    assert err.principal == str(uid + 999)
    assert err.securable_type == "audit_saved_filter"
    assert err.full_name == str(fid)
    assert err.privilege == "audit-saved-filter-edit"


# ---------------------------------------------------------------------
# delete_filter — auth + not-found envelopes
# ---------------------------------------------------------------------


def test_delete_filter_missing_id_message_names_the_id() -> None:
    uid = _admin_user_id()
    with pytest.raises(ResourceNotFoundError) as exc:
        _saved_filters.delete_filter(
            _factory(),
            filter_id=515151,
            actor_user_id=uid,
        )
    assert exc.value.detail == "saved filter id=515151 not found"


def test_delete_filter_not_owner_error_carries_full_triple() -> None:
    uid = _admin_user_id()
    fid = _make_filter(uid)
    with pytest.raises(AuthorizationError) as exc:
        _saved_filters.delete_filter(
            _factory(),
            filter_id=fid,
            actor_user_id=uid + 777,
        )
    err = exc.value
    assert err.principal == str(uid + 777)
    assert err.securable_type == "audit_saved_filter"
    assert err.full_name == str(fid)
    assert err.privilege == "audit-saved-filter-delete"
