"""Tests for volumes surface."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.services import volumes as vol_service

# ---------------------------------------------------------------------------
# Service-level helpers


def test_volume_url_shape() -> None:
    assert (
        vol_service.volume_url("http://test/", "main.s.v")
        == "http://test/api/2.1/unity-catalog/volumes/main.s.v/files"
    )
    assert (
        vol_service.volume_url("http://test", "main.s.v", path="a/b.csv")
        == "http://test/api/2.1/unity-catalog/volumes/main.s.v/files/a/b.csv"
    )


def test_build_headers_only_sets_principal_when_present() -> None:
    assert vol_service.build_headers(None) == {}
    assert vol_service.build_headers("flo@test.com") == {"X-Principal": "flo@test.com"}


# ---------------------------------------------------------------------------
# httpx round-trips using a MockTransport


def _mock_transport(
    handler: Any,
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_upload_file_posts_multipart() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["ctype"] = request.headers.get("content-type")
        captured["principal"] = request.headers.get("x-principal")
        captured["body"] = bytes(request.content)
        return httpx.Response(
            200,
            json={"file": {"path": "hello.csv", "size_bytes": 4, "is_dir": False}},
        )

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        body = await vol_service.upload_file(
            client,
            "http://soyuz",
            "main.ops.vol",
            path="hello.csv",
            upload_name="hello.csv",
            upload_bytes=b"a,b\n",
            principal="flo@test.com",
        )
    assert body["file"]["path"] == "hello.csv"
    assert captured["method"] == "POST"
    assert "path=hello.csv" in captured["url"]
    assert "multipart/form-data" in (captured["ctype"] or "")
    assert captured["principal"] == "flo@test.com"
    assert b"a,b\n" in captured["body"]


@pytest.mark.asyncio
async def test_browse_files_returns_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "files": [
                    {"path": "a.csv", "size_bytes": 10, "is_dir": False},
                    {"path": "b.csv", "size_bytes": 20, "is_dir": False},
                ]
            },
        )

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        files = await vol_service.browse_files(
            client,
            "http://soyuz",
            "main.ops.vol",
            principal=None,
        )
    assert [f["path"] for f in files] == ["a.csv", "b.csv"]


@pytest.mark.asyncio
async def test_delete_file_surfaces_boolean() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(200, json={"deleted": True})

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        ok = await vol_service.delete_file(
            client,
            "http://soyuz",
            "main.ops.vol",
            "a.csv",
            principal=None,
        )
    assert ok is True


@pytest.mark.asyncio
async def test_download_file_streams_bytes() -> None:
    payload = b"hello world"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    received = bytearray()
    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        async for chunk in vol_service.download_file(
            client,
            "http://soyuz",
            "main.ops.vol",
            "hello.txt",
            principal=None,
        ):
            received.extend(chunk)
    assert bytes(received) == payload
