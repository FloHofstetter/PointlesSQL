"""Mutation-kill tests for ``_GovernanceMixin.training_context`` forwarding.

The mixin method threads its arguments into the
``services.agent_runs.training_context`` recorder; pin every forwarded
kwarg so a dropped or None'd argument is caught.
"""

from __future__ import annotations

from typing import Any

from pointlessql.pql._pql_governance import _GovernanceMixin
from pointlessql.types import OpName


def test_training_context_forwards_all_arguments(monkeypatch: Any) -> None:
    """Every training_context argument reaches the recorder unchanged."""
    # kills params=None, source_table_fqn=None, model_fqn=None, the dropped
    # framework=/op_name=/params=/source_table_fqn=/model_fqn= kwargs, and dict(None)
    captured: dict[str, Any] = {}

    def fake_recorder(factory: Any, **kwargs: Any) -> str:
        captured.update(kwargs)
        captured["factory"] = factory
        return "CONTEXT_MANAGER"

    monkeypatch.setattr(
        "pointlessql.services.agent_runs.training_context.training_context",
        fake_recorder,
    )
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: "FACTORY")

    # Real instance (via __new__) so the mutmut trampoline dispatch resolves.
    obj = _GovernanceMixin.__new__(_GovernanceMixin)
    obj._current_run_id = "run-1"  # type: ignore[misc]
    result = obj.training_context(
        framework="sklearn",
        params={"alpha": 1},
        source_table_fqn="c.s.gold",
        model_fqn="c.s.model",
    )
    assert result == "CONTEXT_MANAGER"
    assert captured["agent_run_id"] == "run-1"
    assert captured["framework"] == "sklearn"
    assert captured["op_name"] == OpName.TRAIN_MODEL
    assert captured["params"] == {"alpha": 1}
    assert captured["source_table_fqn"] == "c.s.gold"
    assert captured["model_fqn"] == "c.s.model"
