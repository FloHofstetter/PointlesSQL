"""Unit tests for the business-time (`as_of_event_time`) PQL read.

Unlike the Delta time-travel reads, ``table_as_of_event_time`` reads the
current frame and filters rows by a declared event-time column. The logic
(column resolution from settings, the missing-column guard, the ``<=``
filter) is covered with a stub that overrides ``table`` to return a fixed
pandas frame — no catalog or engine needed.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import pandas as pd
import pytest

from pointlessql.config import get_settings
from pointlessql.exceptions import ValidationError
from pointlessql.pql._pql_read import _ReadMixin

_DEFAULT_COL = get_settings().bitemporal.event_time_column


class _Stub(_ReadMixin):
    """Read mixin with ``table`` short-circuited to a fixed frame."""

    def __init__(self, frame: Any) -> None:
        self._frame = frame

    def table(self, full_name: str) -> Any:  # type: ignore[override]
        return self._frame


def test_filters_rows_at_or_before_when() -> None:
    frame = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "ts": [
                _dt.datetime(2026, 1, 1),
                _dt.datetime(2026, 6, 1),
                _dt.datetime(2026, 12, 1),
            ],
        }
    )
    out = _Stub(frame).table_as_of_event_time(
        "c.s.t", when=_dt.datetime(2026, 6, 1), event_column="ts"
    )
    assert list(out["id"]) == [1, 2]


def test_missing_event_column_raises() -> None:
    frame = pd.DataFrame({"id": [1], "other": [2]})
    with pytest.raises(ValidationError, match="event-time column"):
        _Stub(frame).table_as_of_event_time("c.s.t", when=_dt.datetime(2026, 1, 1), event_column="ts")


def test_non_frame_result_raises() -> None:
    with pytest.raises(ValidationError):
        _Stub(object()).table_as_of_event_time(
            "c.s.t", when=_dt.datetime(2026, 1, 1), event_column="ts"
        )


def test_default_event_column_from_settings() -> None:
    frame = pd.DataFrame({"id": [1, 2], _DEFAULT_COL: [_dt.datetime(2026, 1, 1), _dt.datetime(2026, 9, 1)]})
    out = _Stub(frame).table_as_of_event_time("c.s.t", when=_dt.datetime(2026, 6, 1))
    assert list(out["id"]) == [1]
