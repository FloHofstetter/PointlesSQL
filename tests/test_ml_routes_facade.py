"""ml_routes uses the UnityCatalogClient facade.

Before 121.3, ``_fetch_linked_model_versions`` synchronously called
``make_soyuz_client()`` + ``_list_rm.sync()`` / ``_list_mv.sync()``
directly, bypassing the principal-forwarding + error-wrapping that
``UnityCatalogClient`` provides for every other API route.  These
tests pin the migration: the facade's ``list_registered_models()`` +
``list_model_versions()`` are the only methods called.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pointlessql.api.ml_routes import _fetch_linked_model_versions

# Mirrors the private constant in mlflow_soyuz_link; pasted here so the
# test pins the wire shape rather than reaching into private state.
_LINK_MARKER_KEY = "_pql_link"


@pytest.mark.asyncio
async def test_fetch_linked_model_versions_uses_facade() -> None:
    """Helper calls the facade methods, never the generated client."""
    uc = AsyncMock()
    uc.list_registered_models.return_value = []
    uc.list_model_versions.return_value = []

    result = await _fetch_linked_model_versions(uc, "run-abc")

    assert result == []
    uc.list_registered_models.assert_awaited_once_with(max_results=1000)
    uc.list_model_versions.assert_not_awaited()  # no models, no versions queried


@pytest.mark.asyncio
async def test_fetch_linked_model_versions_filters_by_marker() -> None:
    """Only versions whose marker matches the run id make it into the result."""
    target_run = "run-target"
    other_run = "run-other"

    uc = AsyncMock()
    uc.list_registered_models.return_value = [
        {"full_name": "cat.sch.model_a"},
        {"full_name": "cat.sch.model_b"},
        {},  # missing full_name — skipped
    ]
    # The marker is a JSON object embedded as one of the
    # double-newline-separated chunks in the comment.
    import json as _json

    match_marker = _json.dumps(
        {
            _LINK_MARKER_KEY: {
                "agent_run_id": target_run,
                "linked_at": "2026-05-24T00:00:00Z",
                "mlflow_run_id": "m1",
            }
        }
    )
    other_marker = _json.dumps(
        {_LINK_MARKER_KEY: {"agent_run_id": other_run}}
    )

    # model_a has two versions: one matching, one not.
    # model_b has zero versions.
    def list_versions_side_effect(full_name: str, max_results: int) -> list[dict]:
        assert max_results == 1000
        if full_name == "cat.sch.model_a":
            return [
                {
                    "version": 1,
                    "status": "READY",
                    "source": "s3://bucket/model_a/1",
                    "comment": f"intro line\n\n{match_marker}",
                },
                {
                    "version": 2,
                    "status": "READY",
                    "source": "s3://bucket/model_a/2",
                    "comment": other_marker,
                },
            ]
        return []

    uc.list_model_versions.side_effect = list_versions_side_effect

    result = await _fetch_linked_model_versions(uc, target_run)

    assert len(result) == 1
    assert result[0]["full_name"] == "cat.sch.model_a"
    assert result[0]["version"] == 1
    assert result[0]["linked_at"] == "2026-05-24T00:00:00Z"
    assert result[0]["mlflow_run_id"] == "m1"


@pytest.mark.asyncio
async def test_fetch_linked_model_versions_degrades_gracefully_on_facade_error() -> None:
    """Facade exception → empty list (best-effort contract preserved)."""
    uc = AsyncMock()
    uc.list_registered_models.side_effect = RuntimeError("soyuz down")

    with patch("pointlessql.api.ml_routes._logger") as mock_logger:
        result = await _fetch_linked_model_versions(uc, "run-xyz")

    assert result == []
    mock_logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_linked_model_versions_skips_versions_without_marker() -> None:
    """Versions whose comment lacks a marker are silently skipped."""
    uc = AsyncMock()
    uc.list_registered_models.return_value = [{"full_name": "cat.sch.m"}]
    uc.list_model_versions.return_value = [
        {"version": 1, "comment": "plain text, no marker"},
        {"version": 2, "comment": None},
        {"version": 3, "comment": ""},
    ]

    result = await _fetch_linked_model_versions(uc, "run-any")

    assert result == []
