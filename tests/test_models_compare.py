"""version compare-view diff helpers + render tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.models_compare import (
    _classify_metric,
    compute_metric_diff,
    params_diff,
    tags_diff,
)

# ---------- pure-function diff helpers ----------


def test_classify_metric_lower_better() -> None:
    assert _classify_metric("loss") == "lower-better"
    assert _classify_metric("val_loss") == "lower-better"
    assert _classify_metric("mse") == "lower-better"
    assert _classify_metric("rmse") == "lower-better"
    assert _classify_metric("mae") == "lower-better"
    assert _classify_metric("MSE") == "lower-better"


def test_classify_metric_higher_better() -> None:
    assert _classify_metric("accuracy") == "higher-better"
    assert _classify_metric("val_accuracy") == "higher-better"
    assert _classify_metric("f1") == "higher-better"
    assert _classify_metric("auc") == "higher-better"
    assert _classify_metric("precision") == "higher-better"


def test_classify_metric_neutral() -> None:
    assert _classify_metric("training_time_seconds") == "neutral"
    assert _classify_metric("epoch_count") == "neutral"
    assert _classify_metric("") == "neutral"


def test_compute_metric_diff_returns_better_when_loss_decreases() -> None:
    rows = compute_metric_diff(
        {"metrics": {"loss": 1.0}},
        {"metrics": {"loss": 0.5}},
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "loss"
    assert row["v1"] == 1.0
    assert row["v2"] == 0.5
    assert row["delta_abs"] == pytest.approx(-0.5)
    assert row["direction"] == "better"


def test_compute_metric_diff_returns_worse_when_accuracy_drops() -> None:
    rows = compute_metric_diff(
        {"metrics": {"accuracy": 0.9}},
        {"metrics": {"accuracy": 0.8}},
    )
    assert rows[0]["direction"] == "worse"


def test_compute_metric_diff_neutral_classification_no_direction() -> None:
    rows = compute_metric_diff(
        {"metrics": {"epoch_count": 10}},
        {"metrics": {"epoch_count": 12}},
    )
    assert rows[0]["direction"] == "neutral"


def test_compute_metric_diff_handles_missing_keys() -> None:
    rows = compute_metric_diff(
        {"metrics": {"loss": 0.5}},
        {"metrics": {"accuracy": 0.9}},
    )
    by_name = {r["name"]: r for r in rows}
    assert by_name["loss"]["v2"] is None
    assert by_name["accuracy"]["v1"] is None
    assert by_name["loss"]["delta_abs"] is None


def test_params_diff_added_removed_changed() -> None:
    diff = params_diff(
        {"lr": "0.01", "epochs": "10"},
        {"lr": "0.02", "batch_size": "32"},
    )
    assert diff["added"] == {"batch_size": "32"}
    assert diff["removed"] == {"epochs": "10"}
    assert diff["changed"] == [{"name": "lr", "v1": "0.01", "v2": "0.02"}]


def test_tags_diff_same_shape_as_params() -> None:
    diff = tags_diff(
        {"author": "alice"},
        {"author": "bob", "stage": "production"},
    )
    assert diff["added"] == {"stage": "production"}
    assert diff["changed"] == [{"name": "author", "v1": "alice", "v2": "bob"}]


# ---------- compare-page route ----------

_LINK_MARKER = json.dumps(
    {
        "_pql_link": {
            "agent_run_id": "run-123",
            "mlflow_run_id": "mlf-abc",
            "linked_at": "2026-04-30T00:00:00+00:00",
        }
    },
    sort_keys=True,
)


@pytest.fixture
def uc_with_versions(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(
        "pointlessql.api.dependencies._principal.effective_principal",
        lambda request: None,
    )

    # Patch _fetch_mlflow_context so we don't depend on a live MLflow.
    def _fake_mlflow_context(run_id):
        if run_id == "mlf-abc":
            return {
                "run_id": "mlf-abc",
                "params": {"lr": "0.01", "epochs": "10"},
                "metrics": {"loss": 1.0, "accuracy": 0.85},
                "tags": {"author": "alice"},
            }
        if run_id == "mlf-def":
            return {
                "run_id": "mlf-def",
                "params": {"lr": "0.02", "epochs": "10", "batch_size": "32"},
                "metrics": {"loss": 0.5, "accuracy": 0.92},
                "tags": {"author": "alice", "stage": "production"},
            }
        return {}

    monkeypatch.setattr(
        "pointlessql.api.models_html_routes.fetch_mlflow_context",
        _fake_mlflow_context,
    )

    mock = AsyncMock()

    async def _get_model_version(full_name, version):
        if full_name != "cat1.sch1.smoke_model":
            return {}
        return {
            1: {
                "version": 1,
                "status": "READY",
                "source": "file:///tmp/v1",
                "run_id": "mlf-abc",
                "comment": _LINK_MARKER,
            },
            2: {
                "version": 2,
                "status": "READY",
                "source": "file:///tmp/v2",
                "run_id": "mlf-def",
                "comment": None,
            },
        }.get(version, {})

    mock.get_model_version.side_effect = _get_model_version

    app.state.uc_client = mock
    return mock


@pytest.mark.asyncio
async def test_compare_anonymous_redirects(
    uc_with_versions: AsyncMock, anonymous_client: httpx.AsyncClient
) -> None:
    resp = await anonymous_client.get("/models/cat1.sch1.smoke_model/compare?v1=1&v2=2")
    assert resp.status_code == 303


@pytest.mark.asyncio
async def test_compare_rejects_same_version(
    uc_with_versions: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    resp = await admin_client.get("/models/cat1.sch1.smoke_model/compare?v1=1&v2=1")
    # ``v1 and v2 must differ`` is a ValidationError (422).
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compare_renders_metric_diff(
    uc_with_versions: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    resp = await admin_client.get("/models/cat1.sch1.smoke_model/compare?v1=1&v2=2")
    assert resp.status_code == 200
    body = resp.text
    # Header rendered
    assert "v1 ↔ v2" in body
    # Metrics table headers
    assert "<th>Metric</th>" in body
    # Both metrics present
    assert ">loss<" in body or "<code>loss</code>" in body
    assert "accuracy" in body
    # Params diff: added "batch_size", changed "lr"
    assert "batch_size" in body
    assert "lr" in body
    # Tags diff: added "stage"
    assert "stage" in body
