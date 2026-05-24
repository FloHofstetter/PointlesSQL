"""ingest_pull is bound to the default scheduler registry."""

from __future__ import annotations

from pointlessql.services.scheduler.registry import build_default_registry


def test_ingest_pull_executor_registered() -> None:
    """``"ingest_pull"`` resolves to the ingest service executor."""
    registry = build_default_registry()
    executor = registry.get("ingest_pull")
    # The registered callable lives in the ingest service module.
    assert executor.__module__ == "pointlessql.services.ingest.executor"
    assert executor.__name__ == "ingest_pull_executor"
