"""Asset bundles: spec parsing, plan diffs, idempotent apply, export round-trip."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.models import (
    Base,
    BiDashboard,
    BiDashboardWidget,
    Job,
    JobTask,
    Pipeline,
    User,
)
from pointlessql.services.asset_bundles import (
    apply_bundle,
    bundle_to_yaml,
    export_bundle,
    parse_bundle,
    plan_bundle,
)

_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)


@pytest.fixture
def factory() -> Any:
    """In-memory session factory seeded with one runner user."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            User(
                email="runner@test.com",
                display_name="Runner",
                password_hash="x",
                is_admin=True,
                created_at=_NOW,
            )
        )
        session.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _actor_id(factory: Any) -> int:
    with factory() as session:
        user_id = session.scalar(select(User.id).where(User.email == "runner@test.com"))
        assert user_id is not None
        return int(user_id)


def _apply(factory: Any, yaml_text: str, *, dry_run: bool = False) -> Any:
    return apply_bundle(
        factory,
        spec=parse_bundle(yaml_text),
        workspace_id=1,
        actor_user_id=_actor_id(factory),
        actor_email="runner@test.com",
        dry_run=dry_run,
    )


_BUNDLE = """
bundle:
  name: demo-stack
  description: Demo bundle.
jobs:
  - name: nightly-etl
    cron: "0 2 * * *"
    run_as: runner@test.com
    notify_on: [failure]
    max_parallel_runs: 2
    tasks:
      - name: extract
        kind: python
        config: {script: extract.py}
      - name: load
        kind: python
        depends_on: [extract]
        max_retries: 2
        retry_backoff_seconds: 5
      - name: cleanup
        kind: python
        depends_on: [load]
        run_if: all_done
        for_each: [a, b]
  - name: watcher
    kind: python
    config: {script: watch.py}
    paused: true
    trigger:
      kind: file_arrival
      path: /tmp/in/*.csv
pipelines:
  - slug: orders-pipeline
    title: Orders pipeline
    datasets:
      - name: main.demo.orders_clean
        kind: materialized_view
        sql: SELECT id FROM main.demo.raw_orders
        expectations:
          - name: id_not_null
            constraint: id IS NOT NULL
            action: warn
dashboards:
  - slug: sales-kpis
    title: Sales KPIs
    params:
      - name: region
        type: string
        default: emea
    widgets:
      - kind: counter
        title: Orders
        sql: SELECT COUNT(*) AS n FROM main.demo.orders_clean
      - kind: markdown
        title: Notes
        markdown: Bundle-managed dashboard.
"""


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def test_parse_bundle_happy_path() -> None:
    spec = parse_bundle(_BUNDLE)
    assert spec.bundle.name == "demo-stack"
    assert [j.name for j in spec.jobs] == ["nightly-etl", "watcher"]
    assert spec.jobs[1].effective_cron() == "@event"
    assert spec.jobs[1].trigger_config() == {"path": "/tmp/in/*.csv"}
    assert spec.pipelines[0].identity() == "orders-pipeline"
    assert spec.dashboards[0].widgets[0].matching_key() == ("counter", "Orders")


def test_parse_bundle_rejects_unknown_fields() -> None:
    yaml_text = (
        "bundle: {name: x}\n"
        "jobs:\n"
        "  - name: j\n"
        "    kind: python\n"
        "    cron: '* * * * *'\n"
        "    surprise: 1\n"
    )
    with pytest.raises(ValueError, match="extra_forbidden|surprise"):
        parse_bundle(yaml_text)


def test_parse_bundle_rejects_non_mapping() -> None:
    with pytest.raises(ValueError, match="mapping"):
        parse_bundle("- just\n- a\n- list\n")


def test_parse_bundle_requires_cron_for_cron_jobs() -> None:
    with pytest.raises(ValueError, match="cron is required"):
        parse_bundle("bundle: {name: x}\njobs:\n  - name: j\n    kind: python\n")


def test_parse_bundle_rejects_bad_cron() -> None:
    with pytest.raises(ValueError, match="invalid cron"):
        parse_bundle("bundle: {name: x}\njobs:\n  - name: j\n    kind: python\n    cron: nope\n")


def test_parse_bundle_rejects_unknown_dependency() -> None:
    yaml_text = (
        "bundle: {name: x}\n"
        "jobs:\n"
        "  - name: j\n"
        "    cron: '* * * * *'\n"
        "    tasks:\n"
        "      - {name: a, kind: python, depends_on: [ghost]}\n"
    )
    with pytest.raises(ValueError, match="unknown task"):
        parse_bundle(yaml_text)


def test_parse_bundle_rejects_duplicate_widget_keys() -> None:
    yaml_text = (
        "bundle: {name: x}\n"
        "dashboards:\n"
        "  - slug: d\n"
        "    title: D\n"
        "    widgets:\n"
        "      - {kind: counter, title: T, sql: SELECT 1}\n"
        "      - {kind: counter, title: T, sql: SELECT 2}\n"
    )
    with pytest.raises(ValueError, match="duplicate widget"):
        parse_bundle(yaml_text)


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


def test_plan_on_empty_db_is_all_creates(factory: Any) -> None:
    plan = plan_bundle(factory, spec=parse_bundle(_BUNDLE), workspace_id=1)
    assert [(e.resource_type, e.action) for e in plan.entries] == [
        ("job", "create"),
        ("job", "create"),
        ("pipeline", "create"),
        ("dashboard", "create"),
    ]
    assert plan.orphans == []
    assert not plan.is_noop()


def test_plan_reports_field_changes_and_orphans(factory: Any) -> None:
    _apply(factory, _BUNDLE)
    changed = _BUNDLE.replace('cron: "0 2 * * *"', 'cron: "0 3 * * *"')
    changed = changed.replace("jobs:\n  - name: nightly-etl", "jobs:\n  - name: nightly-etl2")
    plan = plan_bundle(factory, spec=parse_bundle(changed), workspace_id=1)
    by_identity = {entry.identity: entry for entry in plan.entries}
    assert by_identity["nightly-etl2"].action == "create"
    assert by_identity["watcher"].action == "unchanged"
    assert [o.identity for o in plan.orphans if o.resource_type == "job"] == ["nightly-etl"]


def test_plan_cron_change_is_an_update(factory: Any) -> None:
    _apply(factory, _BUNDLE)
    changed = _BUNDLE.replace('cron: "0 2 * * *"', 'cron: "0 3 * * *"')
    plan = plan_bundle(factory, spec=parse_bundle(changed), workspace_id=1)
    entry = next(e for e in plan.entries if e.identity == "nightly-etl")
    assert entry.action == "update"
    assert any(change.startswith("cron_expr") for change in entry.changes)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def test_apply_then_reapply_is_unchanged(factory: Any) -> None:
    first = _apply(factory, _BUNDLE)
    assert [r.action for r in first.results] == ["created", "created", "created", "created"]
    assert not first.has_errors()
    second = _apply(factory, _BUNDLE)
    assert [r.action for r in second.results] == ["unchanged"] * 4
    plan = plan_bundle(factory, spec=parse_bundle(_BUNDLE), workspace_id=1)
    assert plan.is_noop()


def test_apply_dry_run_writes_nothing(factory: Any) -> None:
    outcome = _apply(factory, _BUNDLE, dry_run=True)
    assert outcome.dry_run is True
    assert [r.action for r in outcome.results] == ["created"] * 4
    with factory() as session:
        assert session.scalar(select(Job)) is None
        assert session.scalar(select(Pipeline)) is None
        assert session.scalar(select(BiDashboard)) is None


def test_apply_writes_trigger_and_notify_fields(factory: Any) -> None:
    _apply(factory, _BUNDLE)
    with factory() as session:
        watcher = session.scalar(select(Job).where(Job.name == "watcher"))
        assert watcher is not None
        assert watcher.cron_expr == "@event"
        assert watcher.trigger_kind == "file_arrival"
        assert json.loads(watcher.trigger_config) == {"path": "/tmp/in/*.csv"}
        assert watcher.is_paused is True
        etl = session.scalar(select(Job).where(Job.name == "nightly-etl"))
        assert etl is not None
        assert json.loads(etl.notify_on) == ["failure"]
        assert etl.max_parallel_runs == 2
        tasks = {
            t.name: t for t in session.scalars(select(JobTask).where(JobTask.job_id == etl.id))
        }
        assert set(tasks) == {"extract", "load", "cleanup"}
        assert tasks["load"].max_retries == 2
        assert tasks["cleanup"].run_if == "all_done"
        assert json.loads(tasks["cleanup"].for_each_json or "[]") == ["a", "b"]
        assert json.loads(tasks["load"].depends_on) == [tasks["extract"].id]


def test_apply_reconciles_tasks_including_deletion(factory: Any) -> None:
    _apply(factory, _BUNDLE)
    changed = (
        "bundle: {name: demo-stack}\n"
        "jobs:\n"
        "  - name: nightly-etl\n"
        "    cron: '0 2 * * *'\n"
        "    run_as: runner@test.com\n"
        "    notify_on: [failure]\n"
        "    max_parallel_runs: 2\n"
        "    tasks:\n"
        "      - {name: extract, kind: python, config: {script: extract_v2.py}}\n"
        "      - {name: publish, kind: python, depends_on: [extract]}\n"
    )
    outcome = _apply(factory, changed)
    result = next(r for r in outcome.results if r.identity == "nightly-etl")
    assert result.action == "updated"
    with factory() as session:
        etl = session.scalar(select(Job).where(Job.name == "nightly-etl"))
        assert etl is not None
        tasks = {
            t.name: t for t in session.scalars(select(JobTask).where(JobTask.job_id == etl.id))
        }
        assert set(tasks) == {"extract", "publish"}
        assert json.loads(tasks["extract"].config) == {"script": "extract_v2.py"}
        assert json.loads(tasks["publish"].depends_on) == [tasks["extract"].id]
    # the reconcile is itself idempotent
    assert [r.action for r in _apply(factory, changed).results] == ["unchanged"]


def test_apply_updates_pipeline_and_deletes_surplus_widgets(factory: Any) -> None:
    _apply(factory, _BUNDLE)
    changed = _BUNDLE.replace(
        "sql: SELECT id FROM main.demo.raw_orders",
        "sql: SELECT id, amount FROM main.demo.raw_orders",
    )
    # drop the markdown widget: the dashboard's widgets belong to the bundle
    markdown_block = (
        "      - kind: markdown\n"
        "        title: Notes\n"
        "        markdown: Bundle-managed dashboard.\n"
    )
    changed = changed.replace(markdown_block, "")
    outcome = _apply(factory, changed)
    actions = {r.identity: r.action for r in outcome.results}
    assert actions["orders-pipeline"] == "updated"
    assert actions["sales-kpis"] == "updated"
    with factory() as session:
        pipeline = session.scalar(select(Pipeline).where(Pipeline.slug == "orders-pipeline"))
        assert pipeline is not None
        datasets = json.loads(pipeline.datasets)
        assert datasets[0]["sql"] == "SELECT id, amount FROM main.demo.raw_orders"
        dashboard = session.scalar(select(BiDashboard).where(BiDashboard.slug == "sales-kpis"))
        assert dashboard is not None
        widgets = list(
            session.scalars(
                select(BiDashboardWidget).where(BiDashboardWidget.dashboard_id == dashboard.id)
            )
        )
        assert [(w.kind, w.title) for w in widgets] == [("counter", "Orders")]


def test_apply_unknown_run_as_errors_only_that_job(factory: Any) -> None:
    yaml_text = (
        "bundle: {name: x}\n"
        "jobs:\n"
        "  - name: ghost-job\n"
        "    kind: python\n"
        "    cron: '* * * * *'\n"
        "    run_as: ghost@test.com\n"
        "pipelines:\n"
        "  - slug: p1\n"
        "    title: P1\n"
        "    datasets:\n"
        "      - {name: main.demo.t1, kind: materialized_view, sql: SELECT id FROM main.demo.src}\n"
    )
    outcome = _apply(factory, yaml_text)
    by_identity = {r.identity: r for r in outcome.results}
    assert by_identity["ghost-job"].action == "error"
    assert "ghost@test.com" in str(by_identity["ghost-job"].error)
    assert by_identity["p1"].action == "created"
    with factory() as session:
        assert session.scalar(select(Job).where(Job.name == "ghost-job")) is None
        assert session.scalar(select(Pipeline).where(Pipeline.slug == "p1")) is not None


def test_apply_ambiguous_widget_match_errors_that_dashboard(factory: Any) -> None:
    _apply(factory, _BUNDLE)
    with factory() as session:
        dashboard = session.scalar(select(BiDashboard).where(BiDashboard.slug == "sales-kpis"))
        assert dashboard is not None
        session.add(
            BiDashboardWidget(
                dashboard_id=dashboard.id,
                kind="counter",
                title="Orders",
                sql_text="SELECT 1",
                chart_spec="{}",
                position="{}",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        session.commit()
    outcome = _apply(factory, _BUNDLE)
    result = next(r for r in outcome.results if r.identity == "sales-kpis")
    assert result.action == "error"
    assert "ambiguous" in str(result.error)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_export_roundtrip_plans_unchanged(factory: Any) -> None:
    _apply(factory, _BUNDLE)
    exported = export_bundle(factory, workspace_id=1)
    yaml_text = bundle_to_yaml(exported)
    reparsed = parse_bundle(yaml_text)
    plan = plan_bundle(factory, spec=reparsed, workspace_id=1)
    assert [(e.identity, e.action) for e in plan.entries] == [
        ("nightly-etl", "unchanged"),
        ("watcher", "unchanged"),
        ("orders-pipeline", "unchanged"),
        ("sales-kpis", "unchanged"),
    ]
    assert plan.orphans == []


def test_export_selectors_none_all_empty_none(factory: Any) -> None:
    _apply(factory, _BUNDLE)
    everything = export_bundle(factory, workspace_id=1)
    assert [j.name for j in everything.jobs] == ["nightly-etl", "watcher"]
    nothing = export_bundle(factory, workspace_id=1, jobs=[], pipelines=[], dashboards=[])
    assert nothing.jobs == []
    assert nothing.pipelines == []
    assert nothing.dashboards == []
    selected = export_bundle(
        factory, workspace_id=1, jobs=["watcher"], pipelines=[], dashboards=["sales-kpis"]
    )
    assert [j.name for j in selected.jobs] == ["watcher"]
    assert selected.jobs[0].trigger is not None
    assert selected.jobs[0].trigger.path == "/tmp/in/*.csv"
    assert selected.jobs[0].cron is None
    assert [d.slug for d in selected.dashboards] == ["sales-kpis"]
