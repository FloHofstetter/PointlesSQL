"""Tests for Sprint 18.2 PII resolver, mask helper, and reveal route."""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AuditLog,
    LineageValueChange,
)
from pointlessql.services import pii_mask, pii_resolver


@pytest.fixture(autouse=True)
def _reset_pii_cache() -> None:
    pii_resolver.invalidate_all()


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _non_admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    )


# ---------------------------------------------------------------------
# pii_mask
# ---------------------------------------------------------------------


def test_mask_email_renders_scrubbed_shape() -> None:
    assert pii_mask.mask_value("alice@example.com") == "***@***.***"


def test_mask_phone_keeps_last_four() -> None:
    out = pii_mask.mask_value("+49 555 123-4567")
    assert out.endswith("4567")
    assert out.startswith("***-***-")


def test_mask_short_default_full_redaction() -> None:
    assert pii_mask.mask_value("a") == "*"
    assert pii_mask.mask_value("ab") == "**"


def test_mask_default_keeps_first_and_last() -> None:
    out = pii_mask.mask_value("Schmidthausen")
    assert out.startswith("S")
    assert out.endswith("n")
    assert "*" in out


def test_mask_null_returns_literal_null() -> None:
    assert pii_mask.mask_value(None) == "NULL"


# ---------------------------------------------------------------------
# pii_resolver
# ---------------------------------------------------------------------


def _uc_with_tags(tags: list[dict[str, Any]] | Exception) -> Any:
    """Build a minimal UC client mock returning ``tags`` for get_tags()."""

    class _UC:
        get_tags = AsyncMock(side_effect=[tags] if isinstance(tags, Exception) else None)

    uc = _UC()
    if isinstance(tags, Exception):
        uc.get_tags = AsyncMock(side_effect=tags)
    else:
        uc.get_tags = AsyncMock(return_value=tags)
    return uc


@pytest.mark.asyncio
async def test_is_column_pii_true_when_tag_present() -> None:
    uc = _uc_with_tags([{"key": "pii", "value": "true"}])
    assert await pii_resolver.is_column_pii(uc, "cat.sch.t", "email") is True


@pytest.mark.asyncio
async def test_is_column_pii_false_when_no_pii_tag() -> None:
    uc = _uc_with_tags([{"key": "owner", "value": "alice"}])
    assert await pii_resolver.is_column_pii(uc, "cat.sch.t", "email") is False


@pytest.mark.asyncio
async def test_is_column_pii_handles_uppercase_pii_key() -> None:
    uc = _uc_with_tags([{"key": "PII_class", "value": "email"}])
    assert await pii_resolver.is_column_pii(uc, "cat.sch.t", "email") is True


@pytest.mark.asyncio
async def test_is_column_pii_treats_falsy_value_as_negative() -> None:
    uc = _uc_with_tags([{"key": "pii", "value": "false"}])
    assert await pii_resolver.is_column_pii(uc, "cat.sch.t", "email") is False


@pytest.mark.asyncio
async def test_is_column_pii_swallows_uc_errors() -> None:
    uc = _uc_with_tags(RuntimeError("soyuz down"))
    # Returns False on error, doesn't raise.
    assert await pii_resolver.is_column_pii(uc, "cat.sch.t", "email") is False


@pytest.mark.asyncio
async def test_is_column_pii_caches_response() -> None:
    uc = _uc_with_tags([{"key": "pii", "value": "yes"}])
    await pii_resolver.is_column_pii(uc, "cat.sch.t", "email", ttl_seconds=60)
    await pii_resolver.is_column_pii(uc, "cat.sch.t", "email", ttl_seconds=60)
    await pii_resolver.is_column_pii(uc, "cat.sch.t", "email", ttl_seconds=60)
    assert uc.get_tags.await_count == 1


@pytest.mark.asyncio
async def test_invalidate_busts_cache() -> None:
    uc = _uc_with_tags([{"key": "pii", "value": "yes"}])
    await pii_resolver.is_column_pii(uc, "cat.sch.t", "email")
    pii_resolver.invalidate("cat.sch.t", "email")
    await pii_resolver.is_column_pii(uc, "cat.sch.t", "email")
    assert uc.get_tags.await_count == 2


# ---------------------------------------------------------------------
# Reveal endpoint
# ---------------------------------------------------------------------


def _seed_value_change() -> tuple[str, int, str, str, str, str, str]:
    """Insert a (run, op, lineage_value_changes) triplet.  Return the keys
    needed to call the reveal endpoint plus the cleartext values.
    """
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    run_id = str(uuid.uuid4())
    table = "cat.sch.users"
    row_id = "row-abc"
    column = "email"
    old_value = "old@example.com"
    new_value = "new@example.com"
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="alice@example.com",
                agent_id="etl",
                notebook_path="x.py",
                status="succeeded",
                started_at=now,
                finished_at=now,
            )
        )
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table=table,
            rows_affected=1,
            started_at=now,
            finished_at=now,
        )
        s.add(op)
        s.flush()
        s.add(
            LineageValueChange(
                run_id=run_id,
                op_id=op.id,
                target_table=table,
                target_row_id=row_id,
                target_column=column,
                old_value=old_value,
                new_value=new_value,
                created_at=now,
            )
        )
        s.commit()
        s.refresh(op)
        return run_id, op.id, table, row_id, column, old_value, new_value


@pytest.mark.asyncio
async def test_reveal_endpoint_admin_only() -> None:
    run_id, op_id, table, row_id, column, *_ = _seed_value_change()
    async with _non_admin_client() as client:
        r = await client.post(
            "/api/audit/pii/reveal",
            json={
                "run_id": run_id,
                "op_id": op_id,
                "table": table,
                "row_id": row_id,
                "column": column,
            },
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_reveal_returns_cleartext_and_writes_audit_log() -> None:
    run_id, op_id, table, row_id, column, old_value, new_value = _seed_value_change()
    async with _admin_client() as client:
        r = await client.post(
            "/api/audit/pii/reveal",
            json={
                "run_id": run_id,
                "op_id": op_id,
                "table": table,
                "row_id": row_id,
                "column": column,
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["old_value"] == old_value
    assert body["new_value"] == new_value

    # Audit row landed.
    factory = app.state.session_factory
    with factory() as s:
        rows = list(
            s.scalars(
                select(AuditLog).where(AuditLog.action == "pii.value_revealed")
            )
        )
    assert rows
    assert rows[-1].target == f"{table}.{column}"


@pytest.mark.asyncio
async def test_reveal_missed_writes_distinct_audit_action() -> None:
    async with _admin_client() as client:
        r = await client.post(
            "/api/audit/pii/reveal",
            json={
                "run_id": str(uuid.uuid4()),
                "op_id": 9999,
                "table": "cat.sch.t",
                "row_id": "ghost",
                "column": "email",
            },
        )
    assert r.status_code == 200
    assert r.json() == {"found": False, "old_value": None, "new_value": None}
    factory = app.state.session_factory
    with factory() as s:
        rows = list(
            s.scalars(
                select(AuditLog).where(AuditLog.action == "pii.value_reveal_missed")
            )
        )
    assert rows


@pytest.mark.asyncio
async def test_reveal_validates_required_fields() -> None:
    async with _admin_client() as client:
        r = await client.post(
            "/api/audit/pii/reveal",
            json={"run_id": "", "op_id": 1, "table": "", "row_id": "", "column": ""},
        )
    assert r.status_code == 422
