"""env-snapshot capture + audit-row stamp tests.

The snapshot is built once at import time + cached.  Tests use
:func:`reset_cache_for_tests` to push a deterministic value before
exercising the fingerprint hooks.
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.services.agent_runs import env_snapshot, operations


def _seed_run(factory, run_id: str) -> None:
    now = _dt.datetime.now(_dt.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="alice",
                notebook_path=f"/tmp/{run_id}.py",
                status="running",
                started_at=now,
            )
        )
        session.commit()


def test_snapshot_python_returns_version_and_cpu() -> None:
    """The Python block has the expected keys."""
    block = env_snapshot._snapshot_python()
    assert "version" in block
    assert "platform" in block
    assert isinstance(block["cpu_count"], int) or block["cpu_count"] is None


def test_snapshot_packages_returns_dict() -> None:
    """Packages snapshot returns a non-empty dict on a real install."""
    pkgs = env_snapshot._snapshot_packages()
    assert isinstance(pkgs, dict)
    # At minimum, sqlalchemy is a hard dep so it must be installed.
    lower = {k.lower() for k in pkgs}
    assert "sqlalchemy" in lower


def test_snapshot_gpu_returns_none_without_torch(monkeypatch) -> None:
    """No torch → GPU block is ``None``."""
    monkeypatch.setattr(
        "importlib.import_module",
        lambda name, *a, **kw: (_ for _ in ()).throw(ImportError(name)),
    )
    assert env_snapshot._snapshot_gpu() is None


def test_build_snapshot_round_trip_through_json() -> None:
    """Built snapshot is valid JSON and below the byte cap."""
    blob = env_snapshot._build_snapshot()
    assert blob is not None
    parsed = json.loads(blob)
    assert "python" in parsed
    assert len(blob) <= env_snapshot._BLOB_BYTE_CAP + 256  # +slack for trailing


def test_cached_env_snapshot_returns_string() -> None:
    """The module-level cache exposes a JSON string."""
    cached = env_snapshot.cached_env_snapshot()
    assert cached is None or isinstance(cached, str)


def test_record_operation_stamps_env_snapshot(monkeypatch) -> None:
    """``record_operation`` writes the cached snapshot when none was supplied."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    env_snapshot.reset_cache_for_tests('{"python":{"version":"3.14.0"}}')

    started = _dt.datetime.now(_dt.UTC)
    op_id = operations.record_operation(
        factory,
        agent_run_id=run_id,
        op_name="sql",
        params={"sql": "SELECT 1"},
        target_table=None,
        input_sha=None,
        rows_affected=None,
        delta_version_before=None,
        delta_version_after=None,
        started_at=started,
        finished_at=started,
        error_message=None,
    )
    with factory() as session:
        op = session.get(AgentRunOperation, op_id)
        assert op is not None
        assert op.env_snapshot is not None
        parsed = json.loads(op.env_snapshot)
        assert parsed["python"]["version"] == "3.14.0"


def test_record_operation_explicit_snapshot_overrides_cache(monkeypatch) -> None:
    """A caller-supplied snapshot beats the cache."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    env_snapshot.reset_cache_for_tests('{"python":{"version":"cache"}}')

    started = _dt.datetime.now(_dt.UTC)
    op_id = operations.record_operation(
        factory,
        agent_run_id=run_id,
        op_name="sql",
        params={},
        target_table=None,
        input_sha=None,
        rows_affected=None,
        delta_version_before=None,
        delta_version_after=None,
        started_at=started,
        finished_at=started,
        error_message=None,
        env_snapshot='{"python":{"version":"explicit"}}',
    )
    with factory() as session:
        op = session.get(AgentRunOperation, op_id)
    assert op is not None and op.env_snapshot is not None
    assert json.loads(op.env_snapshot)["python"]["version"] == "explicit"


def test_record_operation_handles_cache_none(monkeypatch) -> None:
    """When the cache is ``None``, the row gets a ``NULL`` env_snapshot."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    env_snapshot.reset_cache_for_tests("")
    # Empty string is falsy in `if env_snapshot is None` — but we
    # use `is None`, so an empty string would still be written.
    # Reset to true ``None`` instead:
    env_snapshot._cached_snapshot = None  # type: ignore[attr-defined]

    started = _dt.datetime.now(_dt.UTC)
    op_id = operations.record_operation(
        factory,
        agent_run_id=run_id,
        op_name="sql",
        params={},
        target_table=None,
        input_sha=None,
        rows_affected=None,
        delta_version_before=None,
        delta_version_after=None,
        started_at=started,
        finished_at=started,
        error_message=None,
    )
    with factory() as session:
        op = session.get(AgentRunOperation, op_id)
    assert op is not None
    assert op.env_snapshot is None


def test_snapshot_caps_at_4kb(monkeypatch) -> None:
    """Excessively-large package list gets dropped to fit the cap."""
    huge_pkgs = {f"pkg_{i:04d}": "1.0.0" for i in range(2000)}
    monkeypatch.setattr(env_snapshot, "_snapshot_packages", lambda: huge_pkgs)
    monkeypatch.setattr(env_snapshot, "_snapshot_gpu", lambda: None)
    blob = env_snapshot._build_snapshot()
    assert blob is not None
    parsed = json.loads(blob)
    # Either packages_truncated marker present, or python block alone fits.
    assert "packages_truncated" in parsed or len(parsed) == 1
    assert len(blob) <= env_snapshot._BLOB_BYTE_CAP + 256
