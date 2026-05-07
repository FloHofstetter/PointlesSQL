"""Sprint 44.4 — third-party log-level quieting.

Validates that :func:`configure_logging` applies per-library
suppression by default (httpx/urllib3/sqlalchemy.engine →
WARNING, mlflow/dbt/papermill → INFO) so PointlesSQL's own
structured lines don't drown in upstream-protocol noise; that
operator overrides via ``third_party_levels`` lift the gate
selectively; and that ``POINTLESSQL_LOG_LEVEL=DEBUG`` bypasses
the defaults entirely.
"""

from __future__ import annotations

import logging

import pytest

from pointlessql.logging_config import configure_logging


@pytest.fixture
def reset_loggers() -> None:
    """Reset the third-party loggers we touch so each test starts clean."""
    for name in (
        "httpx",
        "httpcore",
        "urllib3",
        "sqlalchemy.engine",
        "mlflow",
        "dbt",
        "papermill",
    ):
        logging.getLogger(name).setLevel(logging.NOTSET)


def test_default_quieting_at_info_lifts_httpx_to_warning(reset_loggers: None) -> None:
    """At ``INFO`` root level the defaults install httpx → WARNING."""
    configure_logging("INFO", "text")
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    assert logging.getLogger("mlflow").level == logging.INFO
    assert logging.getLogger("dbt").level == logging.INFO


def test_global_debug_bypasses_third_party_defaults(reset_loggers: None) -> None:
    """``DEBUG`` root level skips the per-library quieting."""
    configure_logging("DEBUG", "text")
    # Library loggers stay at NOTSET — operator gets every byte.
    assert logging.getLogger("httpx").level == logging.NOTSET
    assert logging.getLogger("sqlalchemy.engine").level == logging.NOTSET


def test_overrides_lift_specific_library_at_info(reset_loggers: None) -> None:
    """Override map lifts one upstream while defaults still apply elsewhere."""
    configure_logging(
        "INFO",
        "text",
        third_party_levels={"httpx": "DEBUG"},
    )
    assert logging.getLogger("httpx").level == logging.DEBUG
    # The non-overridden defaults still applied.
    assert logging.getLogger("urllib3").level == logging.WARNING


def test_unknown_level_name_is_silently_skipped(reset_loggers: None) -> None:
    """Garbage override doesn't crash startup; library stays at NOTSET.

    When the override has a typo'd level name, the entry is skipped
    rather than crashing or silently falling back to the default —
    that way a misconfigured operator notices because httpx now logs
    every line, instead of getting the same WARNING gate they would
    have had without any override (which would mask the typo).
    """
    configure_logging(
        "INFO",
        "text",
        third_party_levels={"httpx": "BANANAS"},
    )
    assert logging.getLogger("httpx").level == logging.NOTSET
