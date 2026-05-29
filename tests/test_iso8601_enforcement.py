"""ISO-8601 timestamp enforcement (F5)."""

from __future__ import annotations

import datetime

import pandas as pd
import pytest

from pointlessql.services.governance._iso8601 import (
    Iso8601Violation,
    validate_timestamps,
)


def test_off_mode_returns_empty_even_on_garbage() -> None:
    df = pd.DataFrame({"created_at": ["not an ISO date"]})
    assert validate_timestamps(df, mode="off") == []


def test_warn_mode_collects_violations_without_raising() -> None:
    df = pd.DataFrame({"event_time": ["2026-05-30T12:00:00Z", "garbage", "also garbage"]})
    findings = validate_timestamps(df, mode="warn")
    assert len(findings) == 2
    assert findings[0].column == "event_time"


def test_warn_mode_accepts_iso8601_variants() -> None:
    df = pd.DataFrame({
        "created_at": [
            "2026-05-30",
            "2026-05-30T12:00:00",
            "2026-05-30T12:00:00Z",
            "2026-05-30T12:00:00.123456",
            "2026-05-30T12:00:00+02:00",
            "2026-05-30 12:00:00",
        ]
    })
    assert validate_timestamps(df, mode="warn") == []


def test_strict_mode_raises_on_first_violation() -> None:
    df = pd.DataFrame({"observed_at": ["2026-05-30", "garbage"]})
    with pytest.raises(Iso8601Violation) as exc:
        validate_timestamps(df, mode="strict")
    assert len(exc.value.findings) == 1


def test_unknown_mode_raises() -> None:
    df = pd.DataFrame({})
    with pytest.raises(ValueError):
        validate_timestamps(df, mode="bogus")


def test_non_timestamp_columns_are_skipped() -> None:
    df = pd.DataFrame({"name": ["alice", "bob"], "age": [30, 31]})
    assert validate_timestamps(df, mode="strict") == []


def test_datetime_typed_columns_are_accepted() -> None:
    df = pd.DataFrame({
        "created_at": pd.to_datetime(["2026-05-30", "2026-05-31"]),
    })
    assert validate_timestamps(df, mode="strict") == []


def test_extension_members_carries_findings() -> None:
    findings_df = pd.DataFrame({"created_at": ["garbage"]})
    findings = validate_timestamps(findings_df, mode="warn")
    err = Iso8601Violation(findings)
    members = err.extension_members()
    assert "violations" in members
    assert members["violations"][0]["column"] == "created_at"
