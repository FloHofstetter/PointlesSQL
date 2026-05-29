"""Bitemporal validate+stamp wiring inside pql/_write.py (Phase 134.2)."""

from __future__ import annotations

import datetime
import json
import os

import pandas as pd
import pytest

from pointlessql.api.main import app
from pointlessql.config import reset_settings_cache
from pointlessql.models import DataProduct
from pointlessql.pql._write import _maybe_validate_and_stamp_bitemporal
from pointlessql.services.bitemporal import (
    BitemporalRequirementError,
    set_product_policy,
)


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": [],
    }
    with _factory()() as session:
        row = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


def test_no_product_context_workspace_off_passes() -> None:
    reset_settings_cache()
    df = pd.DataFrame({"a": [1, 2]})
    out = _maybe_validate_and_stamp_bitemporal(df, factory=None, data_product_id=None)
    assert "_processing_time" not in out.columns


def test_no_product_context_workspace_inject_stamps() -> None:
    os.environ["POINTLESSQL_BITEMPORAL_INJECT_PROCESSING_TIME"] = "true"
    reset_settings_cache()
    try:
        out = _maybe_validate_and_stamp_bitemporal(
            pd.DataFrame({"a": [1]}), factory=None, data_product_id=None
        )
        assert "_processing_time" in out.columns
    finally:
        del os.environ["POINTLESSQL_BITEMPORAL_INJECT_PROCESSING_TIME"]
        reset_settings_cache()


def test_product_required_injects_processing_time() -> None:
    reset_settings_cache()
    pid = _seed_dp("bt", "req")
    set_product_policy(_factory(), data_product_id=pid, fields={"enforcement": "required"})
    out = _maybe_validate_and_stamp_bitemporal(
        pd.DataFrame({"a": [1, 2]}),
        factory=_factory(),
        data_product_id=pid,
    )
    assert "_processing_time" in out.columns


def test_product_required_event_time_missing_raises() -> None:
    reset_settings_cache()
    pid = _seed_dp("bt", "rev")
    set_product_policy(
        _factory(),
        data_product_id=pid,
        fields={"enforcement": "required", "require_event_time": True},
    )
    with pytest.raises(BitemporalRequirementError):
        _maybe_validate_and_stamp_bitemporal(
            pd.DataFrame({"a": [1, 2]}),
            factory=_factory(),
            data_product_id=pid,
        )


def test_product_required_event_time_present_passes() -> None:
    reset_settings_cache()
    pid = _seed_dp("bt", "rev_ok")
    set_product_policy(
        _factory(),
        data_product_id=pid,
        fields={"enforcement": "required", "require_event_time": True},
    )
    ts = datetime.datetime(2026, 5, 29, 12, 0, tzinfo=datetime.UTC)
    df = pd.DataFrame({"a": [1], "_event_time": [ts]})
    out = _maybe_validate_and_stamp_bitemporal(
        df, factory=_factory(), data_product_id=pid
    )
    assert "_event_time" in out.columns
    assert "_processing_time" in out.columns


def test_product_event_time_wrong_dtype_raises() -> None:
    reset_settings_cache()
    pid = _seed_dp("bt", "rev_wrong")
    set_product_policy(
        _factory(),
        data_product_id=pid,
        fields={"enforcement": "required", "require_event_time": True},
    )
    df = pd.DataFrame({"a": [1], "_event_time": ["not a date"]})
    with pytest.raises(BitemporalRequirementError):
        _maybe_validate_and_stamp_bitemporal(
            df, factory=_factory(), data_product_id=pid
        )


def test_product_off_overrides_workspace_inject() -> None:
    os.environ["POINTLESSQL_BITEMPORAL_INJECT_PROCESSING_TIME"] = "true"
    reset_settings_cache()
    pid = _seed_dp("bt", "off_ovr")
    set_product_policy(_factory(), data_product_id=pid, fields={"enforcement": "off"})
    try:
        out = _maybe_validate_and_stamp_bitemporal(
            pd.DataFrame({"a": [1]}),
            factory=_factory(),
            data_product_id=pid,
        )
        assert "_processing_time" not in out.columns
    finally:
        del os.environ["POINTLESSQL_BITEMPORAL_INJECT_PROCESSING_TIME"]
        reset_settings_cache()


def test_product_custom_event_time_column() -> None:
    reset_settings_cache()
    pid = _seed_dp("bt", "custom")
    set_product_policy(
        _factory(),
        data_product_id=pid,
        fields={
            "enforcement": "required",
            "require_event_time": True,
            "event_time_column": "occurred_at",
        },
    )
    ts = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    df = pd.DataFrame({"a": [1], "occurred_at": [ts]})
    out = _maybe_validate_and_stamp_bitemporal(
        df, factory=_factory(), data_product_id=pid
    )
    assert "occurred_at" in out.columns
