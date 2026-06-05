"""Mutation-killing tests for the ISO-8601 timestamp validator.

Pins the observable behaviour of the timestamp enforcement helpers:
the string/timestamp column heuristics, the per-value ISO grammar
gate, the loop control flow that walks columns, the truncation of the
offending value, and the violation exception's message + serialised
detail.  Each assertion is true on the real code and false on a
surviving mutant of the corresponding line.
"""

from __future__ import annotations

import datetime

import pandas as pd
import pytest

from pointlessql.services.governance._iso8601 import (
    Iso8601Finding,
    Iso8601Violation,
    _is_string_column,
    _looks_like_timestamp_column,
    _value_is_iso8601,
    validate_timestamps,
)

# ---------------------------------------------------------------------------
# _is_string_column — both "object" and "string" dtype prefixes count
# ---------------------------------------------------------------------------


def test_is_string_column_recognises_string_dtype_prefix() -> None:
    # A pandas StringDtype-named column ("string") is a string column.
    assert _is_string_column("string") is True
    assert _is_string_column("string[python]") is True
    # The recognition is case-sensitive to lowercase "string".
    assert _is_string_column("STRING") is False


def test_validate_timestamps_flags_string_dtype_column() -> None:
    # A string-dtype timestamp-named column with a bad value must be
    # flagged; if "string" stops being recognised the column is skipped.
    series = pd.Series(["not-a-date"], dtype="string")
    df = pd.DataFrame({"created_at": series})
    findings = validate_timestamps(df, mode="warn")
    assert [f.column for f in findings] == ["created_at"]


# ---------------------------------------------------------------------------
# _looks_like_timestamp_column — the "timestamp" token
# ---------------------------------------------------------------------------


def test_looks_like_timestamp_column_matches_timestamp_token() -> None:
    # A column named exactly "timestamp" matches via that token alone
    # (it carries none of _at / _time / _ts / date / _dt).
    assert _looks_like_timestamp_column("timestamp") is True
    # The token match is lowercase-only; an all-caps name is normalised
    # by .lower() inside the helper, so it still matches.
    assert _looks_like_timestamp_column("TIMESTAMP") is True


def test_validate_timestamps_flags_bare_timestamp_named_column() -> None:
    # The literal "timestamp" token drives recognition of this column.
    df = pd.DataFrame({"timestamp": ["definitely not iso"]})
    findings = validate_timestamps(df, mode="warn")
    assert [f.column for f in findings] == ["timestamp"]


# ---------------------------------------------------------------------------
# _value_is_iso8601 — the three early-return branches
# ---------------------------------------------------------------------------


def test_value_is_iso8601_none_is_true() -> None:
    # None is treated as a clean (absent) value.
    assert _value_is_iso8601(None) is True


def test_value_is_iso8601_datetime_is_true() -> None:
    # Native datetime / date objects are accepted without string parsing.
    assert _value_is_iso8601(datetime.datetime(2026, 5, 30, 1, 2, 3)) is True
    assert _value_is_iso8601(datetime.date(2026, 5, 30)) is True


def test_value_is_iso8601_blank_string_is_true() -> None:
    # An empty / whitespace-only string is treated as clean.
    assert _value_is_iso8601("") is True
    assert _value_is_iso8601("   ") is True


def test_validate_timestamps_none_and_blank_values_pass() -> None:
    # None and blank entries must not register as violations; a single
    # genuinely bad value is the only finding.
    df = pd.DataFrame({"event_at": [None, "", "  ", "garbage"]})
    findings = validate_timestamps(df, mode="warn")
    assert len(findings) == 1
    assert findings[0].row_index == 3
    assert findings[0].value == "garbage"


def test_validate_timestamps_datetime_objects_are_clean() -> None:
    # A column of real datetime objects with object dtype must produce
    # no findings even though the column name is timestamp-like.
    df = pd.DataFrame(
        {"event_at": [datetime.datetime(2026, 1, 1), datetime.date(2026, 1, 2)]},
        dtype=object,
    )
    assert validate_timestamps(df, mode="warn") == []


# ---------------------------------------------------------------------------
# validate_timestamps — mode validation + missing-columns guard
# ---------------------------------------------------------------------------


def test_validate_timestamps_unknown_mode_message() -> None:
    # An unknown mode raises ValueError naming the offending mode.
    with pytest.raises(ValueError, match="unknown iso8601 mode"):
        validate_timestamps(pd.DataFrame({}), mode="bogus")


def test_validate_timestamps_object_without_columns_returns_empty() -> None:
    # When the input has no .columns attribute the validator returns an
    # empty findings list rather than raising AttributeError.
    class _NoColumns:
        pass

    assert validate_timestamps(_NoColumns(), mode="warn") == []


# ---------------------------------------------------------------------------
# validate_timestamps — column-walk loop control (continue, not break)
# ---------------------------------------------------------------------------


def test_validate_timestamps_continues_past_date_typed_column() -> None:
    # A genuine datetime64 column is skipped, but a LATER object-typed
    # timestamp column with a bad value must still be flagged — the skip
    # is a continue, not a break.
    df = pd.DataFrame(
        {
            "load_dt": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "event_at": ["2026-01-01T00:00:00Z", "broken"],
        }
    )
    findings = validate_timestamps(df, mode="warn")
    assert [f.column for f in findings] == ["event_at"]
    assert findings[0].row_index == 1


def test_validate_timestamps_continues_past_nonmatching_column() -> None:
    # A non-timestamp column is skipped, but a LATER timestamp column
    # with a bad value must still be flagged — continue, not break.
    df = pd.DataFrame(
        {
            "amount": ["100", "not-a-date-but-irrelevant"],
            "updated_at": ["2026-01-01T00:00:00Z", "broken"],
        }
    )
    findings = validate_timestamps(df, mode="warn")
    assert [f.column for f in findings] == ["updated_at"]
    assert findings[0].row_index == 1


# ---------------------------------------------------------------------------
# validate_timestamps — offending value truncated to 120 chars
# ---------------------------------------------------------------------------


def test_validate_timestamps_truncates_value_at_120_chars() -> None:
    # A long non-ISO value is recorded truncated to exactly 120 chars;
    # a one-off in the slice bound would keep 121.
    bad = "x" * 120 + "ABCDEFGHIJ"
    df = pd.DataFrame({"recorded_at": [bad]})
    findings = validate_timestamps(df, mode="warn")
    assert len(findings) == 1
    assert findings[0].value == "x" * 120
    assert len(findings[0].value) == 120


# ---------------------------------------------------------------------------
# Iso8601Violation — message + serialised detail
# ---------------------------------------------------------------------------


def test_iso8601_violation_carries_exact_message() -> None:
    exc = Iso8601Violation([])
    # The human-readable message is the contracted, mixed-case string.
    assert str(exc) == "ISO-8601 violation in write payload"
    assert exc.detail == "ISO-8601 violation in write payload"


def test_iso8601_violation_extension_members_dict_keys() -> None:
    finding = Iso8601Finding(column="event_at", row_index=3, value="oops")
    exc = Iso8601Violation([finding])
    # The serialised detail uses the lowercase column/row/value keys the
    # FastAPI error handler renders.
    assert exc.extension_members() == {
        "violations": [
            {"column": "event_at", "row": 3, "value": "oops"},
        ],
    }


def test_validate_timestamps_strict_raises_violation_with_findings() -> None:
    # Strict mode raises on the first violating column and the findings
    # are surfaced through the exception's serialised detail.
    df = pd.DataFrame({"event_at": ["2026-01-01T00:00:00Z", "nope"]})
    with pytest.raises(Iso8601Violation) as excinfo:
        validate_timestamps(df, mode="strict")
    members = excinfo.value.extension_members()
    assert members == {
        "violations": [
            {"column": "event_at", "row": 1, "value": "nope"},
        ],
    }
