"""Surface-Welle scheduler kinds wired into the default registry."""

from __future__ import annotations

import pytest

from pointlessql.services.scheduler.registry import build_default_registry


@pytest.mark.parametrize(
    "kind",
    [
        "cost_rollup_hourly",
        "contract_test_evaluation",
        "entity_link_discovery",
    ],
)
def test_kind_registered_in_default_registry(kind: str) -> None:
    registry = build_default_registry()
    executor = registry.get(kind)
    assert callable(executor)
