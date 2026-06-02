"""Unit tests for the soyuz audit-log cross-reference reader.

``fetch_for_run`` is best-effort: a missing endpoint (404), any non-200,
a transport error, a non-JSON body, or a non-list payload must all return
``[]`` so the run-detail page never fails over it; a 200 list is returned
verbatim. A fake UC client supplies the httpx seam. ``asyncio_mode = auto``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pointlessql.services.audit._soyuz import fetch_for_run


class _Resp:
    def __init__(self, status_code: int, json_data: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self) -> Any:
        if isinstance(self._json, Exception):
            raise self._json
        return self._json


def _uc(resp: Any = None, raise_exc: Exception | None = None) -> Any:
    async def _get(url: str, params: dict[str, Any] | None = None) -> Any:
        if raise_exc is not None:
            raise raise_exc
        return resp

    http = SimpleNamespace(get=_get)
    client = SimpleNamespace(get_async_httpx_client=lambda: http)
    return SimpleNamespace(_client=client)


async def test_success_returns_list() -> None:
    rows = [{"id": 1, "action": "set_tag"}]
    out = await fetch_for_run(_uc(_Resp(200, rows)), "run-1")
    assert out == rows


async def test_404_is_empty() -> None:
    assert await fetch_for_run(_uc(_Resp(404)), "run-1") == []


async def test_non_200_is_empty() -> None:
    assert await fetch_for_run(_uc(_Resp(500, text="boom")), "run-1") == []


async def test_transport_error_is_empty() -> None:
    assert await fetch_for_run(_uc(raise_exc=RuntimeError("down")), "run-1") == []


async def test_non_json_is_empty() -> None:
    assert await fetch_for_run(_uc(_Resp(200, ValueError("not json"))), "run-1") == []


async def test_non_list_payload_is_empty() -> None:
    assert await fetch_for_run(_uc(_Resp(200, {"not": "a list"})), "run-1") == []
