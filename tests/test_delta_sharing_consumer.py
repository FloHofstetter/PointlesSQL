"""Tests for the Delta Sharing consumer (profiles + protocol client)."""

from __future__ import annotations

import json
from io import BytesIO

import httpx
import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.sharing_providers import SharingProvider
from pointlessql.services import delta_sharing_consumer as consumer


def _factory():
    return app.state.session_factory


def _provider(name: str = "acme") -> SharingProvider:
    return consumer.create_provider(
        _factory(),
        workspace_id=1,
        name=name,
        endpoint_url="https://share.acme.example/delta-sharing",
        token="tok-secret-123",
        comment=None,
        principal="me@test.com",
    )


# ---------------------------------------------------------------------------
# provider profiles
# ---------------------------------------------------------------------------


def test_create_provider_encrypts_token_at_rest() -> None:
    row = _provider("crypt")
    with _factory()() as session:
        stored = session.scalar(select(SharingProvider).where(SharingProvider.id == row.id))
        assert stored is not None
        assert "tok-secret-123" not in stored.encrypted_token


def test_create_provider_validation() -> None:
    with pytest.raises(ValueError, match="provider name"):
        _provider("has space")
    with pytest.raises(ValueError, match="http"):
        consumer.create_provider(
            _factory(),
            workspace_id=1,
            name="bad-url",
            endpoint_url="ftp://nope",
            token="t",
            comment=None,
            principal=None,
        )
    _provider("dup-prov")
    with pytest.raises(ValueError, match="already exists"):
        _provider("dup-prov")


def test_delete_provider() -> None:
    row = _provider("gone")
    assert consumer.delete_provider(_factory(), provider_id=row.id)
    assert consumer.get_provider(_factory(), workspace_id=1, name="gone") is None


# ---------------------------------------------------------------------------
# protocol client (transport mocked)
# ---------------------------------------------------------------------------


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_parquet(buffer)
    return buffer.getvalue()


def _mock_client(provider: SharingProvider, handler) -> httpx.Client:
    return httpx.Client(
        base_url=provider.endpoint_url,
        headers={"Authorization": "Bearer tok-secret-123"},
        transport=httpx.MockTransport(handler),
    )


def test_list_remote_shares_and_tables(monkeypatch) -> None:
    provider = _provider("lister")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tok-secret-123"
        if request.url.path.endswith("/shares"):
            return httpx.Response(200, json={"items": [{"name": "sales"}, {"name": "ops"}]})
        if request.url.path.endswith("/all-tables"):
            return httpx.Response(
                200,
                json={"items": [{"share": "sales", "schema": "gold", "name": "orders"}]},
            )
        return httpx.Response(404)

    monkeypatch.setattr(consumer, "_client_for", lambda factory, prov: _mock_client(prov, handler))
    assert consumer.list_remote_shares(_factory(), provider) == ["sales", "ops"]
    tables = consumer.list_remote_tables(_factory(), provider, "sales")
    assert tables == [{"share": "sales", "schema": "gold", "name": "orders"}]


def test_query_table_as_pandas_concatenates_files(monkeypatch) -> None:
    provider = _provider("reader")
    part_a = _parquet_bytes(pd.DataFrame({"region": ["emea"], "n": [1]}))
    part_b = _parquet_bytes(pd.DataFrame({"region": ["apac"], "n": [2]}))

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/query"):
            lines = [
                json.dumps({"protocol": {"minReaderVersion": 1}}),
                json.dumps({"metaData": {"id": "m1"}}),
                json.dumps(
                    {
                        "file": {
                            "id": "f1",
                            "url": f"{provider.endpoint_url}/files/f1",
                            "size": len(part_a),
                        }
                    }
                ),
                json.dumps(
                    {
                        "file": {
                            "id": "f2",
                            "url": f"{provider.endpoint_url}/files/f2",
                            "size": len(part_b),
                        }
                    }
                ),
            ]
            return httpx.Response(200, text="\n".join(lines))
        if path.endswith("/files/f1"):
            return httpx.Response(200, content=part_a)
        if path.endswith("/files/f2"):
            return httpx.Response(200, content=part_b)
        return httpx.Response(404)

    monkeypatch.setattr(consumer, "_client_for", lambda factory, prov: _mock_client(prov, handler))
    frame = consumer.query_table_as_pandas(
        _factory(), provider, share="sales", schema="gold", table="orders"
    )
    assert sorted(frame["region"].tolist()) == ["apac", "emea"]
    assert int(frame["n"].sum()) == 3


def test_query_table_rejects_oversized_results(monkeypatch) -> None:
    provider = _provider("huge")

    def handler(request: httpx.Request) -> httpx.Response:
        lines = [
            json.dumps({"protocol": {"minReaderVersion": 1}}),
            json.dumps({"metaData": {"id": "m1"}}),
            json.dumps(
                {
                    "file": {
                        "id": "f1",
                        "url": f"{provider.endpoint_url}/files/f1",
                        "size": consumer.MAX_RESULT_BYTES + 1,
                    }
                }
            ),
        ]
        return httpx.Response(200, text="\n".join(lines))

    monkeypatch.setattr(consumer, "_client_for", lambda factory, prov: _mock_client(prov, handler))
    with pytest.raises(consumer.SharingProtocolError, match="cap"):
        consumer.query_table_as_pandas(_factory(), provider, share="s", schema="g", table="t")


def test_protocol_error_surfaces_status(monkeypatch) -> None:
    provider = _provider("denied")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errorCode": "UNAUTHENTICATED", "message": "bad token"})

    monkeypatch.setattr(consumer, "_client_for", lambda factory, prov: _mock_client(prov, handler))
    with pytest.raises(consumer.SharingProtocolError, match="401"):
        consumer.list_remote_shares(_factory(), provider)
