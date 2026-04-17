"""Tests for centralized logging configuration."""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.logging_config import (
    JSONFormatter,
    RequestIdFilter,
    configure_logging,
    request_id_var,
)
from pointlessql.services.unitycatalog import UnityCatalogClient


def _record(
    level: int = logging.INFO, msg: str = "hello", exc_info: object | None = None
) -> logging.LogRecord:
    return logging.LogRecord(
        name="pointlessql.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=None,
        exc_info=exc_info,  # pyright: ignore[reportArgumentType]
    )


class TestJsonFormatter:
    def test_json_formatter_emits_valid_json(self) -> None:
        record = _record(msg="event-42")
        record.request_id = "req-abc"
        parsed = json.loads(JSONFormatter().format(record))
        assert parsed["message"] == "event-42"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "pointlessql.test"
        assert parsed["request_id"] == "req-abc"
        assert "timestamp" in parsed
        # ISO 8601 UTC offset
        assert parsed["timestamp"].endswith("+00:00")

    def test_json_formatter_includes_exception_info(self) -> None:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys

            exc_info = sys.exc_info()
        record = _record(level=logging.ERROR, msg="failed", exc_info=exc_info)
        record.request_id = "-"
        parsed = json.loads(JSONFormatter().format(record))
        assert "exception" in parsed
        assert "RuntimeError: boom" in parsed["exception"]


class TestRequestIdFilter:
    def test_request_id_filter_injects_contextvar(self) -> None:
        token = request_id_var.set("abc")
        try:
            record = _record()
            assert RequestIdFilter().filter(record) is True
            assert record.request_id == "abc"
        finally:
            request_id_var.reset(token)

    def test_request_id_filter_defaults_to_dash(self) -> None:
        # Contextvar is unset here (each test starts with default None).
        record = _record()
        RequestIdFilter().filter(record)
        assert record.request_id == "-"


class TestConfigureLogging:
    def _our_handlers(self, logger: logging.Logger) -> list[logging.Handler]:
        return [h for h in logger.handlers if getattr(h, "_pointlessql_handler", False)]

    def test_configure_logging_is_idempotent(self) -> None:
        configure_logging("INFO", "text")
        configure_logging("INFO", "text")
        root = logging.getLogger()
        assert len(self._our_handlers(root)) == 1
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
            assert len(self._our_handlers(logging.getLogger(name))) == 1

    @pytest.mark.parametrize(
        ("fmt", "expected_cls"),
        [("text", logging.Formatter), ("json", JSONFormatter)],
    )
    def test_configure_logging_text_vs_json(self, fmt: str, expected_cls: type) -> None:
        configure_logging("INFO", fmt)  # pyright: ignore[reportArgumentType]
        root = logging.getLogger()
        ours = [h for h in root.handlers if getattr(h, "_pointlessql_handler", False)]
        assert len(ours) == 1
        assert isinstance(ours[0].formatter, expected_cls)
        # Reset to text for subsequent tests.
        configure_logging("INFO", "text")


class TestRequestIdPropagation:
    @pytest.fixture(autouse=True)
    def _mock_uc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        app.state.jupyter_process = None
        client = MagicMock(spec=UnityCatalogClient)
        client.list_catalogs = AsyncMock(return_value=[])
        client.get_tree = AsyncMock(side_effect=CatalogUnavailableError("down"))
        app.state.uc_client = client
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: client),  # type: ignore[arg-type]
        )

    async def test_request_id_propagates_to_logs_in_request_scope(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="pointlessql.api.error_handlers")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies=app.state._test_auth_cookie,
        ) as client:
            resp = await client.get("/api/tree", headers={"X-Request-ID": "trace-xyz"})
        assert resp.headers["X-Request-ID"] == "trace-xyz"
        # The error handler logs a warning for CatalogUnavailableError.
        # The LogRecord factory stamps request_id on every record, so
        # caplog sees it without any per-handler hookup.
        matching = [
            r
            for r in caplog.records
            if r.name == "pointlessql.api.error_handlers"
            and getattr(r, "request_id", None) == "trace-xyz"
        ]
        observed = [(r.name, getattr(r, "request_id", None)) for r in caplog.records]
        assert matching, (
            "expected warning record from error_handlers stamped with "
            f"request_id=trace-xyz, got: {observed}"
        )
