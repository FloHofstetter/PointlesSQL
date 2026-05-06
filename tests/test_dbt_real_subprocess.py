"""Real-binary integration test for the dbt-duckdb subprocess pipeline.

Sister to :mod:`tests.test_dbt_executor` (which never spawns dbt and
covers argv composition + path resolution) and :mod:`tests.test_dbt_bridge`
(which parses static fixture artefacts).  This module fills the
remaining gap: a real ``dbt`` CLI invocation against the sample
project at ``dbt_project/`` plus assertions on the *bridge-readable*
shape of the resulting ``manifest.json`` + ``run_results.json``.

Skipped when:

- the ``integration`` marker is suppressed (default in
  ``pyproject.toml`` — opt in with ``-m integration``);
- ``dbt-duckdb`` is not importable, e.g. on a clean-machine CI worker
  that has not installed the optional ``[dbt]`` extra, **or** the
  installed dbt-duckdb version is incompatible with the running
  Python interpreter (Python-3.14 + dbt-duckdb-1.9 currently raises
  ``mashumaro.UnserializableField`` during CLI module import).

The duckdb file is written under ``tmp_path`` so concurrent test runs
cannot collide.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# Skip the whole module when the dbt CLI is not importable.  We probe
# ``dbt.cli.main`` (not ``dbt``) because that's the module that
# ``dbt --version`` actually loads: a half-installed extra or a
# Python-version / mashumaro mismatch crashes there even when
# ``import dbt`` succeeds.  ``pytest.importorskip`` only converts
# ``ImportError`` to a skip, so we wrap manually because mashumaro /
# pydantic version skew raises non-ImportError exceptions during
# dbt's CLI module import.
try:
    importlib.import_module("dbt.cli.main")
except Exception as _dbt_import_exc:  # noqa: BLE001 — defensive
    pytest.skip(
        f"dbt CLI not importable: {_dbt_import_exc!r}; "
        "pip install pointlessql[dbt] (Python-version compatible build)",
        allow_module_level=True,
    )

from pointlessql.services.dbt_bridge import (  # noqa: E402 — guarded by skip above
    merge_manifest_and_results,
    parse_manifest,
    parse_run_results,
)
from pointlessql.services.dbt_executor import DBTExecutor  # noqa: E402
from pointlessql.settings import DBTSettings  # noqa: E402

pytestmark = pytest.mark.integration


REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PROJECT = REPO_ROOT / "dbt_project"
SAMPLE_PROFILES = SAMPLE_PROJECT / "profiles"


def _executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DBTExecutor:
    """Build a ``DBTExecutor`` pinned to the sample project + a scratch DB.

    The DuckDB path is steered via the ``POINTLESSQL_DBT_DEMO_DUCKDB``
    env var (see ``dbt_project/profiles/profiles.yml``) so the run
    cannot pollute a developer's shared scratch file.

    Args:
        tmp_path: pytest-managed scratch directory.
        monkeypatch: pytest fixture for env-var injection.

    Returns:
        DBTExecutor: Bound to the absolute paths of the sample project.
    """
    duckdb_path = tmp_path / "demo.duckdb"
    monkeypatch.setenv("POINTLESSQL_DBT_DEMO_DUCKDB", str(duckdb_path))
    settings = DBTSettings(
        enabled=True,
        project_dir=SAMPLE_PROJECT,
        profiles_dir=SAMPLE_PROFILES,
        target="dev",
        timeout_seconds=180,
    )
    return DBTExecutor(settings, cwd=tmp_path)


async def test_compile_writes_manifest_with_three_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``dbt compile`` produces a manifest with the three sample models.

    Compile is the cheapest op in the pipeline — no data writes, no
    duckdb file required — so it doubles as a syntactic smoke test
    for the sample project.  A future dbt-version bump that breaks
    manifest schema v12 would surface here first.
    """
    ex = _executor(tmp_path, monkeypatch)
    result = await ex.compile()
    assert result.exit_code == 0, f"dbt compile failed:\nstderr:\n{result.stderr}"
    assert result.manifest_path.is_file()

    manifest = parse_manifest(result.manifest_path)
    nodes = manifest.get("nodes")
    assert isinstance(nodes, dict)
    model_names: list[str] = []
    for raw in nodes.values():  # type: ignore[reportUnknownVariableType]
        if not isinstance(raw, dict):
            continue
        if raw.get("resource_type") != "model":
            continue
        name = raw.get("name")
        if isinstance(name, str):
            model_names.append(name)
    model_names.sort()
    assert model_names == ["bronze_raw", "gold_summary", "silver_clean"]


async def test_seed_run_test_emits_expected_node_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``dbt seed`` + ``dbt run`` + ``dbt test`` populate run_results.json.

    The full pipeline must:

    1. Materialise the orders seed into the scratch duckdb.
    2. Build all three models (bronze → silver → gold).
    3. Evaluate every test from ``schema.yml`` and record one
       ``run_results.json`` entry per executed node.

    The bridge's :func:`merge_manifest_and_results` then projects
    those entries into :class:`DBTNodeResult`-shaped rows — the same
    structure that ``emit_operations_for_dbt_run`` consumes in
    production.  Every test we ship in the sample project is designed
    to pass against ``orders.csv``; a future seed edit that breaks
    that contract surfaces here.
    """
    ex = _executor(tmp_path, monkeypatch)

    # Seed materialises the CSV as a duckdb table the models ref().
    seed_result = await ex.seed()
    assert seed_result.exit_code == 0, f"dbt seed failed:\nstderr:\n{seed_result.stderr}"

    run_result = await ex.run()
    assert run_result.exit_code == 0, f"dbt run failed:\nstderr:\n{run_result.stderr}"

    test_result = await ex.test()
    assert test_result.exit_code == 0, (
        f"dbt test failed (every sample test should pass):\nstderr:\n{test_result.stderr}"
    )

    # The last run_results.json on disk is from the most recent invocation
    # (dbt test).  Parse it through the production code path.
    manifest = parse_manifest(test_result.manifest_path)
    results = parse_run_results(test_result.run_results_path)
    nodes = merge_manifest_and_results(manifest, results)

    # Every entry must be a recognised resource type and have a status.
    for node in nodes:
        assert node.unique_id
        assert node.status in {"pass", "success", "fail", "error", "warn", "skipped"}
        assert node.resource_type in {"model", "test", "seed"}

    test_nodes = [n for n in nodes if n.resource_type == "test"]
    # Five tests defined in schema.yml: not_null(id), unique(id),
    # not_null(amount), accepted_values(status), relationships.
    assert len(test_nodes) == 5, (
        f"expected 5 dbt tests, got {len(test_nodes)}: {[n.unique_id for n in test_nodes]}"
    )
    assert all(n.status == "pass" for n in test_nodes), (
        "every shipped test passes against the orders.csv seed; "
        f"got {[(n.unique_id, n.status) for n in test_nodes]}"
    )
