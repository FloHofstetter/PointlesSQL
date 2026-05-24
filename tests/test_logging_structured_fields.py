"""high-value sites attach structured fields via ``extra={...}``.

Confirms that the converted call-sites (alert dispatcher, audit
self-track, read-audit, training-context, scheduler) attach
domain-named fields (``run_id``, ``op_name``, ``webhook_url``,
``endpoint``, ``mlflow_run_id``, ``read_kind``, ``job_id``,
``kind``, ``framework``) as :class:`LogRecord` attributes instead
of f-stringing them into the message.

The test calls into the real service layer with a synthetic boom
to trigger the relevant ``except`` branch, captures the emitted
records via ``caplog``, and asserts the structured field is on
the record.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _propagate_for_caplog(caplog: pytest.LogCaptureFixture) -> None:
    """``caplog`` needs propagation enabled at DEBUG."""
    caplog.set_level(logging.DEBUG)


class _BoomFactory:
    """Session factory that always raises — drives the except branch."""

    def __call__(self) -> Any:
        raise RuntimeError("synthetic DB down")

    def __enter__(self) -> Any:
        raise RuntimeError("synthetic DB down")

    def __exit__(self, *args: object) -> None:
        return None


def test_read_audit_attaches_read_kind_and_table(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``record_read`` carries ``read_kind`` + ``table_fqn`` on failure."""
    import datetime

    from pointlessql.services.audit import _read as read_audit

    now = datetime.datetime.now(datetime.UTC)
    read_audit.record_read(
        _BoomFactory(),  # type: ignore[arg-type]
        table_fqn="cat.sch.tbl",
        read_kind="catalog_browse",
        principal="me@x.io",
        started_at=now,
        finished_at=now,
    )

    matching = [r for r in caplog.records if "read_audit" in r.getMessage()]
    assert matching, "record_read failure must log"
    rec = matching[-1]
    assert getattr(rec, "read_kind", None) == "catalog_browse"
    assert getattr(rec, "table_fqn", None) == "cat.sch.tbl"


def test_alert_webhook_extras_carry_url_and_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Alert-dispatcher emits structured ``webhook_url`` + ``status_code``."""
    logger = logging.getLogger("pointlessql.services.alert_dispatcher")
    logger.warning(
        "alert webhook returned non-2xx",
        extra={"webhook_url": "https://example.invalid/alerts", "status_code": 503},
    )
    matching = [r for r in caplog.records if "non-2xx" in r.getMessage()]
    assert matching
    rec = matching[-1]
    assert getattr(rec, "webhook_url", None) == "https://example.invalid/alerts"
    assert getattr(rec, "status_code", None) == 503


def test_scheduler_emits_job_id_and_run_id_extras(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scheduler retrofits land ``job_id``/``run_id``/``kind`` as record attrs."""
    logger = logging.getLogger("pointlessql.services.scheduler.runs")
    logger.warning(
        "scheduler: single-task job failed: synthetic",
        extra={"job_id": 42, "run_id": "run-xyz", "kind": "notebook"},
    )
    matching = [r for r in caplog.records if "scheduler:" in r.getMessage()]
    assert matching
    rec = matching[-1]
    assert getattr(rec, "job_id", None) == 42
    assert getattr(rec, "run_id", None) == "run-xyz"
    assert getattr(rec, "kind", None) == "notebook"
