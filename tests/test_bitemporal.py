"""Bitemporality — processing-time injection convention.

Covers the data-mesh δ bitemporal half: the duck-typed processing-time
stamp (the enforceable clock), its best-effort passthrough on
unrecognised frames, and the settings-gated write-path hook (default off
so it never silently evolves a Delta schema).
"""

from __future__ import annotations

import datetime
import os

import pandas as pd
import pyarrow as pa

from pointlessql.config import reset_settings_cache
from pointlessql.pql._write import _maybe_validate_and_stamp_bitemporal
from pointlessql.services.bitemporal import inject_processing_time

_TS = datetime.datetime(2026, 5, 29, 12, 0, tzinfo=datetime.UTC)


def test_inject_processing_time_pandas() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    out = inject_processing_time(df, column="_processing_time", now=_TS)
    assert "_processing_time" in out.columns
    assert (out["_processing_time"] == _TS).all()
    # original is untouched (copy semantics).
    assert "_processing_time" not in df.columns


def test_inject_processing_time_pyarrow() -> None:
    table = pa.table({"a": [1, 2]})
    out = inject_processing_time(table, column="_processing_time", now=_TS)
    assert "_processing_time" in out.schema.names
    assert out.num_rows == 2


def test_inject_processing_time_passthrough_unknown_frame() -> None:
    payload = [1, 2, 3]
    assert inject_processing_time(payload, column="_processing_time", now=_TS) is payload


def test_write_hook_off_by_default_returns_frame_unchanged() -> None:
    reset_settings_cache()
    df = pd.DataFrame({"a": [1]})
    out = _maybe_validate_and_stamp_bitemporal(df)
    assert "_processing_time" not in out.columns


def test_write_hook_stamps_when_enabled() -> None:
    os.environ["POINTLESSQL_BITEMPORAL_INJECT_PROCESSING_TIME"] = "true"
    reset_settings_cache()
    try:
        df = pd.DataFrame({"a": [1, 2]})
        out = _maybe_validate_and_stamp_bitemporal(df)
        assert "_processing_time" in out.columns
    finally:
        del os.environ["POINTLESSQL_BITEMPORAL_INJECT_PROCESSING_TIME"]
        reset_settings_cache()


def test_write_hook_respects_custom_column_name() -> None:
    os.environ["POINTLESSQL_BITEMPORAL_INJECT_PROCESSING_TIME"] = "true"
    os.environ["POINTLESSQL_BITEMPORAL_PROCESSING_TIME_COLUMN"] = "_ingested_at"
    reset_settings_cache()
    try:
        out = _maybe_validate_and_stamp_bitemporal(pd.DataFrame({"a": [1]}))
        assert "_ingested_at" in out.columns
    finally:
        del os.environ["POINTLESSQL_BITEMPORAL_INJECT_PROCESSING_TIME"]
        del os.environ["POINTLESSQL_BITEMPORAL_PROCESSING_TIME_COLUMN"]
        reset_settings_cache()
