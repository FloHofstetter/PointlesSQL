"""Tests for the Delta-Sharing table_update trigger source."""

from __future__ import annotations

from unittest.mock import MagicMock

import pointlessql.services.delta_sharing_consumer as dsc
import pointlessql.services.scheduler.triggers as triggers


def _fake_client(status: int, headers: dict[str, str] | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.headers = headers or {}
    client = MagicMock()
    client.get.return_value = response
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    return client


def test_parse_delta_table_version() -> None:
    assert dsc._parse_delta_table_version({"Delta-Table-Version": "42"}) == 42
    assert dsc._parse_delta_table_version({"Delta-Table-Version": "  7 "}) == 7
    assert dsc._parse_delta_table_version({}) is None
    assert dsc._parse_delta_table_version({"Delta-Table-Version": "nope"}) is None


def test_remote_table_version_reads_header(monkeypatch) -> None:
    client = _fake_client(200, {"Delta-Table-Version": "11"})
    monkeypatch.setattr(dsc, "_client_for", lambda factory, provider: client)
    version = dsc.remote_table_version(None, object(), share="s", schema="sc", table="t")
    assert version == 11
    assert "/shares/s/schemas/sc/tables/t/version" in client.get.call_args[0][0]


def test_remote_table_version_non_200_is_none(monkeypatch) -> None:
    client = _fake_client(404)
    monkeypatch.setattr(dsc, "_client_for", lambda factory, provider: client)
    assert dsc.remote_table_version(None, object(), share="s", schema="sc", table="t") is None


async def test_sharing_trigger_routes_to_remote_version(monkeypatch) -> None:
    monkeypatch.setattr(dsc, "get_provider", lambda factory, *, workspace_id, name: object())
    monkeypatch.setattr(
        dsc,
        "remote_table_version",
        lambda factory, provider, *, share, schema, table: 9,
    )
    job = MagicMock()
    job.id = 1
    job.workspace_id = 1
    config = {"provider": "p", "share": "s", "schema": "sc", "table": "t"}
    assert await triggers._sharing_table_version(None, job, config) == "9"


async def test_sharing_trigger_missing_fields_is_none() -> None:
    job = MagicMock()
    job.id = 1
    job.workspace_id = 1
    assert await triggers._sharing_table_version(None, job, {"provider": "p"}) is None


async def test_sharing_trigger_unknown_provider_is_none(monkeypatch) -> None:
    monkeypatch.setattr(dsc, "get_provider", lambda factory, *, workspace_id, name: None)
    job = MagicMock()
    job.id = 1
    job.workspace_id = 1
    config = {"provider": "p", "share": "s", "schema": "sc", "table": "t"}
    assert await triggers._sharing_table_version(None, job, config) is None
