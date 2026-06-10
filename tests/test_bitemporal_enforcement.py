"""Phase 131 — bitemporal policy inheritance + stamp/validate enforcement."""

from __future__ import annotations

import datetime
import json

import pandas as pd
import pytest

from pointlessql.api.main import app
from pointlessql.config import BitemporalSettings
from pointlessql.models import DataProduct
from pointlessql.services import bitemporal as bitemporal_service
from pointlessql.services.bitemporal import (
    BitemporalRequirementError,
    validate_event_time_column,
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


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------


def test_settings_defaults_unchanged() -> None:
    settings = BitemporalSettings()
    assert settings.enforcement == "opt_in"
    assert settings.require_event_time is False
    assert settings.inject_processing_time is False


# ---------------------------------------------------------------------------
# effective policy
# ---------------------------------------------------------------------------


def test_effective_inherits_workspace_when_no_override() -> None:
    dp_id = _seed_dp("bt1", "s1")
    settings = BitemporalSettings(inject_processing_time=True)
    eff = bitemporal_service.effective_policy(_factory(), settings=settings, data_product_id=dp_id)
    assert eff.enforcement == "opt_in"
    assert eff.inject_processing_time is True
    assert eff.enforcement_source == "workspace"


def test_effective_uses_product_override() -> None:
    dp_id = _seed_dp("bt2", "s2")
    bitemporal_service.set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={"enforcement": "required"},
    )
    settings = BitemporalSettings(inject_processing_time=False)
    eff = bitemporal_service.effective_policy(_factory(), settings=settings, data_product_id=dp_id)
    assert eff.enforcement == "required"
    assert eff.inject_processing_time is True  # 'required' forces inject
    assert eff.enforcement_source == "product"


def test_off_mode_disables_inject_regardless_of_settings() -> None:
    dp_id = _seed_dp("bt3", "s3")
    bitemporal_service.set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={"enforcement": "off"},
    )
    settings = BitemporalSettings(inject_processing_time=True)
    eff = bitemporal_service.effective_policy(_factory(), settings=settings, data_product_id=dp_id)
    assert eff.inject_processing_time is False


def test_column_name_override_takes_effect() -> None:
    dp_id = _seed_dp("bt4", "s4")
    bitemporal_service.set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={
            "processing_time_column": "_proc_ts",
            "event_time_column": "_evt_ts",
        },
    )
    settings = BitemporalSettings()
    eff = bitemporal_service.effective_policy(_factory(), settings=settings, data_product_id=dp_id)
    assert eff.processing_time_column == "_proc_ts"
    assert eff.event_time_column == "_evt_ts"


def test_invalid_enforcement_rejected() -> None:
    dp_id = _seed_dp("bt5", "s5")
    with pytest.raises(ValueError):
        bitemporal_service.set_product_policy(
            _factory(),
            data_product_id=dp_id,
            fields={"enforcement": "weird"},
        )


def test_no_product_id_returns_workspace_view() -> None:
    settings = BitemporalSettings(enforcement="required")
    eff = bitemporal_service.effective_policy(_factory(), settings=settings, data_product_id=None)
    assert eff.enforcement == "required"
    assert eff.enforcement_source == "workspace"


# ---------------------------------------------------------------------------
# event-time validation
# ---------------------------------------------------------------------------


def test_validate_passes_when_require_false() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    validate_event_time_column(df, column="_event_time", require=False)


def test_validate_raises_when_required_and_missing() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(BitemporalRequirementError):
        validate_event_time_column(df, column="_event_time", require=True)


def test_validate_passes_when_column_present_temporal() -> None:
    df = pd.DataFrame(
        {
            "a": [1, 2],
            "_event_time": pd.to_datetime(["2026-05-29", "2026-05-30"]),
        }
    )
    validate_event_time_column(df, column="_event_time", require=True)


def test_validate_raises_when_column_present_non_temporal() -> None:
    df = pd.DataFrame({"_event_time": ["2026-05-29", "2026-05-30"]})
    with pytest.raises(BitemporalRequirementError):
        validate_event_time_column(df, column="_event_time", require=True)


def test_validate_passes_silently_for_unknown_frame() -> None:
    validate_event_time_column("not a dataframe", column="_event_time", require=True)


# ---------------------------------------------------------------------------
# stamping still works (smoke; carries over from existing tests)
# ---------------------------------------------------------------------------


def test_inject_adds_processing_time_column() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    stamped = bitemporal_service.inject_processing_time(df, column="_pt")
    assert "_pt" in stamped.columns
    assert len(stamped["_pt"].unique()) == 1


def test_inject_does_not_mutate_input() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    bitemporal_service.inject_processing_time(df, column="_pt")
    assert "_pt" not in df.columns
