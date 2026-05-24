"""Tests for the SQL-cell helpers + WS execute path."""

from __future__ import annotations

import pytest

from pointlessql.exceptions import AuthorizationError, CatalogNotFoundError
from pointlessql.pql import SQLParseError
from pointlessql.services.notebook import _sql_cell as notebook_sql_cell


def test_build_kernel_wrapper_default_var() -> None:
    """Defaults result_var to 'df' when None or empty."""
    snippet = notebook_sql_cell.build_kernel_wrapper(
        "SELECT 1",
        approved_tables={"a.b.c": "/tmp/x"},
        result_var=None,
    )
    assert "result_var='df'" in snippet
    assert "approved_tables={'a.b.c': '/tmp/x'}" in snippet
    assert "max_rows=1000" in snippet


def test_build_kernel_wrapper_named_var() -> None:
    """Honour the user-named result variable."""
    snippet = notebook_sql_cell.build_kernel_wrapper(
        "SELECT 1",
        approved_tables={},
        result_var="orders",
    )
    assert "result_var='orders'" in snippet


def test_build_kernel_wrapper_rejects_bad_identifier() -> None:
    """A non-identifier result_var falls back to 'df' (defence-in-depth)."""
    snippet = notebook_sql_cell.build_kernel_wrapper(
        "SELECT 1",
        approved_tables={},
        result_var="123abc; import os",
    )
    assert "result_var='df'" in snippet


def test_build_kernel_wrapper_escapes_sql() -> None:
    """SQL with single quotes round-trips via repr()."""
    snippet = notebook_sql_cell.build_kernel_wrapper(
        "SELECT 'hello'",
        approved_tables={},
        result_var="df",
    )
    # repr() picks one quote style; the escaped form must appear.
    assert "SELECT 'hello'" in snippet or "SELECT \\'hello\\'" in snippet


class _FakeUcClient:
    """Minimal stub satisfying ``resolve_approved_tables``."""

    def __init__(self, tables: dict[str, dict[str, object]]) -> None:
        self._tables = tables

    async def get_table(self, catalog: str, schema: str, name: str):
        return self._tables.get(f"{catalog}.{schema}.{name}")


@pytest.mark.asyncio
async def test_resolve_approved_tables_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns the storage-location map after a successful privilege check."""
    fake = _FakeUcClient({"main.public.foo": {"storage_location": "/tmp/foo"}})

    async def _fake_check_privilege(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(
        "pointlessql.services.authorization.check_privilege",
        _fake_check_privilege,
    )
    out = await notebook_sql_cell.resolve_approved_tables(
        "SELECT * FROM main.public.foo",
        uc_client=fake,
        actor_email="alice@test",
        is_admin=False,
    )
    assert out == {"main.public.foo": "/tmp/foo"}


@pytest.mark.asyncio
async def test_resolve_approved_tables_unknown_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown table → ``CatalogNotFoundError``."""
    fake = _FakeUcClient({})
    with pytest.raises(CatalogNotFoundError):
        await notebook_sql_cell.resolve_approved_tables(
            "SELECT * FROM main.public.gone",
            uc_client=fake,
            actor_email="alice@test",
            is_admin=False,
        )


@pytest.mark.asyncio
async def test_resolve_approved_tables_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``check_privilege`` raising propagates as ``AuthorizationError``."""
    fake = _FakeUcClient({"main.public.foo": {"storage_location": "/tmp/foo"}})

    async def _denied(*args, **kwargs) -> None:
        raise AuthorizationError(
            principal="alice@test",
            privilege="SELECT",
            securable_type="table",
            full_name="main.public.foo",
        )

    monkeypatch.setattr(
        "pointlessql.services.authorization.check_privilege",
        _denied,
    )
    with pytest.raises(AuthorizationError):
        await notebook_sql_cell.resolve_approved_tables(
            "SELECT * FROM main.public.foo",
            uc_client=fake,
            actor_email="alice@test",
            is_admin=False,
        )


@pytest.mark.asyncio
async def test_resolve_approved_tables_bad_sql() -> None:
    """Non-parseable SQL → ``SQLParseError``."""
    fake = _FakeUcClient({})
    with pytest.raises(SQLParseError):
        await notebook_sql_cell.resolve_approved_tables(
            "INSERT INTO foo VALUES (1)",
            uc_client=fake,
            actor_email="alice@test",
            is_admin=False,
        )
