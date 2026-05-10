"""Tests for the ``/api/dbt/test`` auto-rollback path.

Auto-rollback is opt-in via the ``auto_rollback`` body flag.  When at
least one dbt test fails with ``severity='error'`` AND the flag is
set, the route walks every ``dbt_model`` op in the run and invokes
``pql.rollback`` for each — collecting per-target outcomes (succeeded
vs. refused) into the response envelope.

We monkeypatch :func:`pointlessql.api.dbt_routes._invoke_pql_rollback`
to control the rollback outcome without spinning up a real Delta
table — the rollback primitive itself is covered by
:mod:`tests.test_pql_rollback`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.dbt import routes as dbt_routes
from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models.audit_sinks import GovernanceEvent
from pointlessql.services.dbt import DBTExecutor, DBTRunResult
from pointlessql.services.governance_events import (
    EVENT_TYPE_DBT_AUTO_ROLLBACK_EXECUTED,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dbt_minimal" / "target"
_MANIFEST = _FIXTURE_DIR / "manifest.json"
_RESULTS = _FIXTURE_DIR / "run_results.json"


@dataclass(frozen=True)
class _FakeRollbackResult:
    """Stand-in for :class:`pointlessql.pql._rollback.RollbackResult`."""

    version_before: int
    version_after: int
    target_version_restored: int
    restored_file_count: int | None


@pytest.fixture
def stub_executor_default(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Patch :meth:`DBTExecutor._run` to return the bundled fixture."""

    async def _stub_run(self: DBTExecutor, *args: str) -> DBTRunResult:  # noqa: ARG001
        return DBTRunResult(
            command=["dbt", "test"],
            exit_code=0,
            stdout="OK",
            stderr="",
            manifest_path=_MANIFEST,
            run_results_path=_RESULTS,
            duration_seconds=0.1,
        )

    monkeypatch.setattr(DBTExecutor, "_run", _stub_run)
    yield


def _stub_executor_with_severity_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Mutate the fixture so the unique-id test is severity='error'.

    Reuses the same approach as
    :mod:`tests.test_dbt_severity_enforcement` so the per-call
    behaviour stays consistent across the two test modules.
    """
    manifest = json.loads(_MANIFEST.read_text())
    manifest["nodes"]["test.pql_test.unique_silver_clean_id.def456"]["config"]["severity"] = "error"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    custom_manifest = target_dir / "manifest.json"
    custom_manifest.write_text(json.dumps(manifest))
    custom_results = target_dir / "run_results.json"
    custom_results.write_text(_RESULTS.read_text())

    async def _stub_run(self: DBTExecutor, *args: str) -> DBTRunResult:  # noqa: ARG001
        return DBTRunResult(
            command=["dbt", "test"],
            exit_code=1,
            stdout="",
            stderr="",
            manifest_path=custom_manifest,
            run_results_path=custom_results,
            duration_seconds=0.1,
        )

    monkeypatch.setattr(DBTExecutor, "_run", _stub_run)


@pytest.mark.asyncio
async def test_auto_rollback_disabled_emits_no_rollback_block(
    auth_cookies: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Without ``auto_rollback=true`` the response carries no rollback block.

    Even with an error-severity failure, the route stays on the
    severity-only path: the run finishes ``failed`` but no rollback
    is attempted and no auto-rollback CloudEvent fires.
    """
    _stub_executor_with_severity_error(monkeypatch, tmp_path)
    rollback_calls: list[str] = []

    def _spy_rollback(*_args: object, **kwargs: object) -> _FakeRollbackResult:
        rollback_calls.append(str(kwargs.get("target")))
        return _FakeRollbackResult(0, 1, 0, None)

    monkeypatch.setattr(dbt_routes, "_invoke_pql_rollback", _spy_rollback)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/test", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["err_failures"] == 1
    assert "auto_rollback" not in body
    assert rollback_calls == []


@pytest.mark.asyncio
async def test_auto_rollback_with_only_warn_failures_no_ops(
    auth_cookies: dict[str, str],
    stub_executor_default: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``auto_rollback=true`` is a no-op when there are no error fails.

    The fixture has one warn-severity failing test by default; with
    no error-severity failures the rollback path skips entirely —
    same shape as the disabled case.
    """
    rollback_calls: list[str] = []

    def _spy_rollback(*_args: object, **kwargs: object) -> _FakeRollbackResult:
        rollback_calls.append(str(kwargs.get("target")))
        return _FakeRollbackResult(0, 1, 0, None)

    monkeypatch.setattr(dbt_routes, "_invoke_pql_rollback", _spy_rollback)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/test", json={"auto_rollback": True})
    body = resp.json()
    # warn-only failure → err_failures == 0 → auto_rollback skipped.
    assert body["summary"]["err_failures"] == 0
    assert body["summary"]["warn_failures"] == 1
    assert "auto_rollback" not in body
    assert rollback_calls == []


@pytest.mark.asyncio
async def test_auto_rollback_with_error_failure_invokes_rollback(
    auth_cookies: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An error-severity fail + flag triggers rollback for every dbt_model op.

    Two dbt_model ops land in the run (bronze_raw + silver_clean).
    Both targets surface in ``auto_rollback.targets_attempted`` and
    both stub-rollbacks succeed, landing in ``auto_rollback.succeeded``.
    The CloudEvent fires once with the aggregate counts.
    """
    _stub_executor_with_severity_error(monkeypatch, tmp_path)

    rollback_calls: list[dict[str, object]] = []

    def _stub_rollback(*_args: object, **kwargs: object) -> _FakeRollbackResult:
        rollback_calls.append(dict(kwargs))
        return _FakeRollbackResult(
            version_before=5,
            version_after=6,
            target_version_restored=4,
            restored_file_count=2,
        )

    monkeypatch.setattr(dbt_routes, "_invoke_pql_rollback", _stub_rollback)

    factory = app.state.session_factory
    with factory() as session:
        before_event_id = (
            session.scalar(select(GovernanceEvent.id).order_by(GovernanceEvent.id.desc())) or 0
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/test", json={"auto_rollback": True})
    body = resp.json()

    assert body["summary"]["err_failures"] == 1
    payload = body["auto_rollback"]
    assert payload["enabled"] is True
    assert sorted(payload["targets_attempted"]) == [
        "main.bronze.bronze_raw",
        "main.silver.silver_clean",
    ]
    assert len(payload["succeeded"]) == 2
    assert all(s["target_version_restored"] == 4 for s in payload["succeeded"])
    assert payload["failed"] == []
    # One rollback call per dbt_model op.
    assert {c["target"] for c in rollback_calls} == {
        "main.bronze.bronze_raw",
        "main.silver.silver_clean",
    }

    # CloudEvent fired once with aggregate counts.
    with factory() as session:
        events = session.scalars(
            select(GovernanceEvent)
            .where(GovernanceEvent.id > before_event_id)
            .where(GovernanceEvent.event_type == EVENT_TYPE_DBT_AUTO_ROLLBACK_EXECUTED),
        ).all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_auto_rollback_collects_refusals_in_failed_list(
    auth_cookies: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A per-target refusal (e.g. RollbackInvalid) lands in ``failed``.

    The other targets keep going — auto-rollback is best-effort by
    design.  Verifies the refusal is reported with the exception
    class name + message so the cockpit can render it next to the
    failing test.
    """
    _stub_executor_with_severity_error(monkeypatch, tmp_path)

    call_count = {"n": 0}

    def _flaky_rollback(*_args: object, **kwargs: object) -> _FakeRollbackResult:
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First target succeeds.
            return _FakeRollbackResult(0, 1, 0, None)
        # Second target refuses — ValidationError as a stand-in for any
        # of the four refusal modes (the route catches Exception and
        # records the class name + message).
        raise ValidationError("delta_version_before is None")

    monkeypatch.setattr(dbt_routes, "_invoke_pql_rollback", _flaky_rollback)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/test", json={"auto_rollback": True})
    body = resp.json()
    payload = body["auto_rollback"]
    assert len(payload["succeeded"]) == 1
    assert len(payload["failed"]) == 1
    assert payload["failed"][0]["reason"] == "ValidationError"
    assert "delta_version_before" in payload["failed"][0]["message"]


@pytest.mark.asyncio
async def test_run_path_does_not_emit_auto_rollback_block(
    auth_cookies: dict[str, str],
    stub_executor_default: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``/api/dbt/run`` ignores the ``auto_rollback`` flag.

    Auto-rollback only fires on the ``test`` path because rollback
    semantics are bound to *test* outcomes, not the build itself.
    """
    rollback_calls: list[str] = []

    def _spy_rollback(*_args: object, **kwargs: object) -> _FakeRollbackResult:
        rollback_calls.append(str(kwargs.get("target")))
        return _FakeRollbackResult(0, 1, 0, None)

    monkeypatch.setattr(dbt_routes, "_invoke_pql_rollback", _spy_rollback)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post(
            "/api/dbt/run",
            json={"auto_rollback": True},
        )
    body = resp.json()
    assert "auto_rollback" not in body
    assert rollback_calls == []
