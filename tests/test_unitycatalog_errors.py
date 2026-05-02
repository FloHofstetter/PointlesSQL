"""Tests for the soyuz-error → domain-exception mapping.

Pin the contract that ``wrap_catalog_errors`` extracts the human-
readable ``message`` field from soyuz's JSON envelope so the SQL
editor and other UI surfaces don't show the raw multi-line
``UnexpectedStatus`` dump.
"""

from __future__ import annotations

import json

import pytest
from soyuz_catalog_client.errors import UnexpectedStatus

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.services.unitycatalog._api import (
    _friendly_soyuz_message,
    wrap_catalog_errors,
)


def _make_unexpected(status: int, body: object) -> UnexpectedStatus:
    """Build an ``UnexpectedStatus`` carrying the given body (JSON-encoded if container)."""
    if isinstance(body, dict | list):
        content = json.dumps(body).encode()
    elif isinstance(body, str):
        content = body.encode()
    elif body is None:
        content = b""
    elif isinstance(body, bytes):
        content = body
    else:
        raise TypeError(f"unsupported body type {type(body).__name__}")
    return UnexpectedStatus(status_code=status, content=content)


class TestFriendlySoyuzMessage:
    """``_friendly_soyuz_message`` extracts the ``message`` field."""

    def test_extracts_message_from_soyuz_envelope(self) -> None:
        exc = _make_unexpected(
            404,
            {
                "error_code": "NOT_FOUND",
                "message": "Catalog 'phase157' does not exist",
                "request_id": "abc123",
            },
        )
        assert _friendly_soyuz_message(exc) == "Catalog 'phase157' does not exist"

    def test_falls_back_to_str_when_body_is_not_json(self) -> None:
        exc = _make_unexpected(500, b"<html>Internal Server Error</html>")
        out = _friendly_soyuz_message(exc)
        # Falls back to the raw UnexpectedStatus.__str__ — better verbose
        # than empty.
        assert "Internal Server Error" in out
        assert "Unexpected status code: 500" in out

    def test_falls_back_when_message_field_missing(self) -> None:
        exc = _make_unexpected(404, {"error_code": "NOT_FOUND"})
        out = _friendly_soyuz_message(exc)
        assert "Unexpected status code: 404" in out

    def test_falls_back_when_message_is_empty_string(self) -> None:
        exc = _make_unexpected(404, {"error_code": "NOT_FOUND", "message": "   "})
        out = _friendly_soyuz_message(exc)
        assert "Unexpected status code: 404" in out

    def test_handles_empty_content(self) -> None:
        exc = _make_unexpected(502, None)
        out = _friendly_soyuz_message(exc)
        assert "Unexpected status code: 502" in out

    def test_handles_array_top_level_json(self) -> None:
        # Spec-compliant soyuz always returns a dict, but a stray
        # array shouldn't crash — fall back to the verbose form.
        exc = _make_unexpected(400, [1, 2, 3])
        out = _friendly_soyuz_message(exc)
        assert "Unexpected status code: 400" in out


class TestWrapCatalogErrors:
    """The decorator surfaces the friendly message in the raised exception."""

    @pytest.mark.asyncio
    async def test_404_raises_catalog_not_found_with_friendly_message(self) -> None:
        @wrap_catalog_errors
        async def boom() -> None:
            raise _make_unexpected(
                404,
                {
                    "error_code": "NOT_FOUND",
                    "message": "Catalog 'phase157' does not exist",
                    "request_id": "abc",
                },
            )

        with pytest.raises(CatalogNotFoundError) as info:
            await boom()
        # The exception message is JUST the friendly text — no
        # ``Unexpected status code`` noise, no ``Response content``
        # JSON dump, no request_id.
        assert str(info.value) == "Catalog 'phase157' does not exist"
        assert "Unexpected status code" not in str(info.value)
        assert "request_id" not in str(info.value)

    @pytest.mark.asyncio
    async def test_422_raises_validation_error_with_friendly_message(self) -> None:
        @wrap_catalog_errors
        async def boom() -> None:
            raise _make_unexpected(
                422,
                {"error_code": "VALIDATION", "message": "name is required"},
            )

        with pytest.raises(ValidationError) as info:
            await boom()
        assert str(info.value) == "name is required"

    @pytest.mark.asyncio
    async def test_500_raises_unavailable_with_friendly_message(self) -> None:
        @wrap_catalog_errors
        async def boom() -> None:
            raise _make_unexpected(
                503,
                {"error_code": "UNAVAILABLE", "message": "soyuz database offline"},
            )

        with pytest.raises(CatalogUnavailableError) as info:
            await boom()
        assert "soyuz database offline" in str(info.value)
