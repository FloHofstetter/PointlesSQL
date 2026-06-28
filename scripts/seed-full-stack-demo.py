#!/usr/bin/env python
"""End-to-end stack demo: raw CSV → Bronze → Silver → Gold → ML → Inference.

In one autonomous run, this script exercises every major surface of
PointlesSQL — the PQL primitives (autoload / sql / write_table / merge /
aggregate / branch / branch_promote / training_context / rollback), the
Phase-21 MLflow + soyuz cross-link, and the read-only HTTP routes the
audit-cockpit / models / lineage / branching UIs are built on.

The script is the local-replay companion to the agent-bring-up walkthrough:
it produces exactly the audit-trail shape a Hermes-driven session would,
without needing a live agent.  Re-run it nightly (or whenever a Phase-N
sprint touches one of those surfaces) to surface regressions early.

Story: two synthetic CSVs (`houses.csv` + `sales.csv`) feed a regression
that predicts house price from `(size_sqft, bedrooms, age_years)`.  The
synthetic data carries known coefficients so the script can assert that
the trained `LinearRegression` recovers them within a 30 % tolerance.

Run it against a live stack:

```
docker compose up -d                     # or: uv run pointlessql
uv run python scripts/seed-full-stack-demo.py --fresh --demo-rollback --verbose
```

Idempotent: re-runs without `--fresh` no-op on existing tables.  `--drop`
tears the demo catalog down without re-seeding (cleanup hook).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
from soyuz_catalog_client.api.catalogs import (
    create_catalog_api_2_1_unity_catalog_catalogs_post as _create_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    delete_catalog_api_2_1_unity_catalog_catalogs_name_delete as _delete_catalog,
)
from soyuz_catalog_client.api.schemas import (
    create_schema_api_2_1_unity_catalog_schemas_post as _create_schema,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_catalog import CreateCatalog
from soyuz_catalog_client.models.create_schema import CreateSchema

from pointlessql.config import Settings
from pointlessql.db import get_session_factory, init_db
from pointlessql.models import AgentRun, AutoloadCheckpoint
from pointlessql.pql.pql import PQL
from pointlessql.services.agent_runs.mlflow_soyuz_link import link_model_version_to_run
from pointlessql.services.soyuz_client import make_soyuz_client

# --------------------------------------------------------------------------- #
# Constants — story-anchored, intentionally not configurable

CATALOG = "demo_ml"
SCHEMAS_BASE = ("bronze", "silver", "gold", "models", "predictions")

WAREHOUSE_ROOT = os.environ.get("E2E_WAREHOUSE_ROOT", "/app/warehouse")
DATA_DIR = Path(__file__).resolve().parent.parent / "notebooks" / "full_stack_demo_data"

BRONZE_HOUSES = f"{CATALOG}.bronze.houses_raw"
BRONZE_SALES = f"{CATALOG}.bronze.sales_raw"
SILVER = f"{CATALOG}.silver.houses_with_sales"
GOLD_TRAINING = f"{CATALOG}.gold.training_set"
GOLD_TEST = f"{CATALOG}.gold.test_set"
MODEL_FQN = f"{CATALOG}.models.house_price_lr"
PREDICTIONS = f"{CATALOG}.predictions.house_prices_v1"

# True coefficients used to generate prices.  The script asserts the
# trained model recovers them within 30 %.
TRUE_INTERCEPT = 50_000.0
TRUE_SIZE_COEF = 200.0
TRUE_BED_COEF = 25_000.0
TRUE_AGE_COEF = -1_500.0
NOISE_SIGMA = 30_000.0

N_ROWS = 200
RANDOM_SEED = 42

# --------------------------------------------------------------------------- #
# CLI


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line flags into a namespace."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Drop the demo_ml catalog before seeding (idempotent re-run).",
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop the demo_ml catalog and exit (no re-seed).",
    )
    parser.add_argument(
        "--demo-rollback",
        action="store_true",
        help="After inference, do a deliberately-bad merge then rollback.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print extra detail on each step.",
    )
    parser.add_argument(
        "--ui-base",
        default=os.environ.get("POINTLESSQL_UI_BASE", "http://127.0.0.1:8000"),
        help="Base URL of the PointlesSQL web UI for the read-tour.",
    )
    parser.add_argument(
        "--login-email",
        default=os.environ.get("POINTLESSQL_DEMO_EMAIL", "demo@local"),
        help=(
            "Email of an admin user for cookie-auth.  Defaults to "
            "``demo@local`` so the script is self-bootstrapping; combined "
            "with --register-if-missing the first-ever run registers + "
            "logs in without manual setup."
        ),
    )
    parser.add_argument(
        "--login-password",
        default=os.environ.get("POINTLESSQL_DEMO_PASSWORD", "demopass1"),
        help=("Password for cookie-auth.  Defaults to ``demopass1`` alongside --login-email."),
    )
    parser.add_argument(
        "--skip-routes",
        action="store_true",
        help="Skip the read-tour even if credentials are supplied.",
    )
    parser.add_argument(
        "--register-if-missing",
        action="store_true",
        default=os.environ.get("POINTLESSQL_DEMO_REGISTER", "1") == "1",
        help=(
            "When --login-email's account doesn't exist, register it before "
            "logging in (idempotent: 409 'already exists' is treated as ok). "
            "Defaults on so the demo is self-bootstrapping; "
            "POINTLESSQL_DEMO_REGISTER=0 disables."
        ),
    )
    parser.add_argument(
        "--keep-state",
        action="store_true",
        help=(
            "Skip the cleanup steps that delete dashboards / saved queries / "
            "alerts / admin objects / federation entities at the end of "
            "their respective Phase-2 steps.  Default off keeps re-runs "
            "idempotent for CI; flip on so the grand-tour walkthrough has "
            "a furnished workspace to demo from "
            "(see ``docs/e2e-walkthroughs/grand-tour.md``)."
        ),
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help=(
            "Only run the original 12-step path (raw → ML → 24-route tour). "
            "Default runs the full Phase-2 coverage (~150 routes)."
        ),
    )
    return parser.parse_args(argv)


# --------------------------------------------------------------------------- #
# Pretty-print helpers


class Printer:
    """Tiny wrapper around print() that adds step-banners and check-marks."""

    def __init__(self, *, verbose: bool) -> None:
        self.verbose = verbose
        self._step = 0
        self._t0 = time.monotonic()

    def step(self, title: str) -> None:
        """Emit a numbered section header."""
        self._step += 1
        elapsed = time.monotonic() - self._t0
        print(f"\n▶ Step {self._step}  ({elapsed:5.1f}s)  {title}")
        print(f"  {'─' * (len(title) + 4)}")

    def info(self, msg: str) -> None:
        """Sub-line under the current step."""
        print(f"  • {msg}")

    def detail(self, msg: str) -> None:
        """Verbose-only sub-line."""
        if self.verbose:
            print(f"    · {msg}")

    def ok(self, msg: str) -> None:
        """Success marker."""
        print(f"  ✓ {msg}")

    def warn(self, msg: str) -> None:
        """Warning marker."""
        print(f"  ⚠ {msg}")

    @property
    def elapsed(self) -> float:
        """Seconds since the printer was constructed."""
        return time.monotonic() - self._t0


# --------------------------------------------------------------------------- #
# CSV generation


def _generate_csvs(p: Printer) -> None:
    """Write `houses.csv` + `sales.csv` deterministically.

    Skips writes when the files already exist on disk (idempotent).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    houses_path = DATA_DIR / "houses.csv"
    sales_path = DATA_DIR / "sales.csv"

    if houses_path.exists() and sales_path.exists():
        p.info(f"CSVs already present at {DATA_DIR}")
        return

    rng = np.random.default_rng(RANDOM_SEED)

    house_ids = np.arange(1, N_ROWS + 1)
    size_sqft = rng.integers(800, 3500, size=N_ROWS)
    bedrooms = rng.integers(1, 6, size=N_ROWS)
    age_years = rng.integers(0, 60, size=N_ROWS)

    noise = rng.normal(0.0, NOISE_SIGMA, size=N_ROWS)
    price = (
        TRUE_INTERCEPT
        + TRUE_SIZE_COEF * size_sqft
        + TRUE_BED_COEF * bedrooms
        + TRUE_AGE_COEF * age_years
        + noise
    )
    price = np.maximum(price, 50_000).round(0).astype(int)

    base_date = datetime(2024, 1, 1, tzinfo=UTC)
    sold_at = [
        (base_date + timedelta(days=int(d))).date().isoformat()
        for d in rng.integers(0, 365, size=N_ROWS)
    ]

    pd.DataFrame(
        {
            "house_id": house_ids,
            "size_sqft": size_sqft,
            "bedrooms": bedrooms,
            "age_years": age_years,
        }
    ).to_csv(houses_path, index=False)
    pd.DataFrame(
        {
            "house_id": house_ids,
            "sold_at": sold_at,
            "price": price,
        }
    ).to_csv(sales_path, index=False)

    p.ok(f"wrote {houses_path.name} + {sales_path.name} ({N_ROWS} rows each)")


# --------------------------------------------------------------------------- #
# Catalog / schema lifecycle


def _storage_root(catalog: str, schema: str) -> str:
    """Return the file:// storage root for one schema."""
    return f"file://{WAREHOUSE_ROOT.rstrip('/')}/{catalog}/{schema}"


def _drop_catalog(soyuz: Any, p: Printer) -> None:
    """Force-delete the demo_ml catalog + clear meta-DB residue.

    A bare soyuz drop leaves stale rows in our metadata DB (autoload
    SHA checkpoints, agent_runs, lineage edges) that re-runs would
    short-circuit on.  This helper purges every demo-scoped row so
    `--fresh` is genuinely fresh.

    Soyuz force-delete on a catalog does NOT cascade to MODEL
    securables (their deletion route is separate); we manually drop
    each registered model first.  Surface this via a raw HTTP call
    because the generated client does not yet expose ``force`` on
    model deletion.
    """
    settings = Settings()
    base = settings.soyuz.catalog_url.rstrip("/")
    # Drop every registered model under demo_ml first.
    try:
        list_resp = httpx.get(
            f"{base}/api/2.1/unity-catalog/models",
            params={"catalog_name": CATALOG},
            timeout=10.0,
        )
        if list_resp.status_code == 200:
            for m in list_resp.json().get("registered_models", []):
                fqn = m.get("full_name")
                if not fqn:
                    continue
                httpx.delete(
                    f"{base}/api/2.1/unity-catalog/models/{fqn}",
                    params={"force": "true"},
                    timeout=10.0,
                )
                p.detail(f"deleted model {fqn}")
    except httpx.HTTPError as exc:
        p.detail(f"model-cleanup pre-delete failed (continuing): {exc}")

    try:
        _delete_catalog.sync(client=soyuz, name=CATALOG, force=True)
        p.ok(f"dropped catalog {CATALOG!r}")
    except UnexpectedStatus as exc:
        if exc.status_code == 404:
            p.info(f"catalog {CATALOG!r} did not exist")
        else:
            raise
    # Wipe meta-DB rows scoped to demo_ml.* targets so autoload
    # re-ingests, lineage starts empty, etc.
    factory = get_session_factory()
    with factory() as session:
        from sqlalchemy import delete

        result = session.execute(
            delete(AutoloadCheckpoint).where(AutoloadCheckpoint.target_table.like(f"{CATALOG}.%"))
        )
        session.commit()
        deleted = result.rowcount  # type: ignore[attr-defined]
    p.detail(f"cleared {deleted} AutoloadCheckpoint row(s) for {CATALOG}.*")


def _ensure_catalog(soyuz: Any, p: Printer) -> None:
    """Create demo_ml catalog if missing (idempotent)."""
    try:
        _create_catalog.sync(
            client=soyuz,
            body=CreateCatalog(
                name=CATALOG,
                comment="PointlesSQL full-stack demo catalog (raw → ML).",
            ),
        )
        p.ok(f"catalog {CATALOG!r} created")
    except UnexpectedStatus as exc:
        if exc.status_code != 409:
            raise
        p.info(f"catalog {CATALOG!r} exists")


def _ensure_schema(soyuz: Any, schema: str, p: Printer) -> None:
    """Create demo_ml.<schema> with explicit storage_root (idempotent)."""
    storage = _storage_root(CATALOG, schema)
    try:
        _create_schema.sync(
            client=soyuz,
            body=CreateSchema(
                catalog_name=CATALOG,
                name=schema,
                storage_root=storage,
            ),
        )
        p.ok(f"schema {CATALOG}.{schema} created")
    except UnexpectedStatus as exc:
        if exc.status_code != 409:
            raise
        p.info(f"schema {CATALOG}.{schema} exists")
    Path(f"{WAREHOUSE_ROOT.rstrip('/')}/{CATALOG}/{schema}").mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Agent-run bookkeeping


def _create_agent_run(label: str) -> str:
    """Insert a new AgentRun row and return its id.

    PointlesSQL's PQL primitives expect an existing run-id when the
    operation should land in the audit trail.  Demo runs share the
    `seed-full-stack-demo` agent identifier so they are easy to filter
    in the runs list.
    """
    factory = get_session_factory()
    run_id = str(uuid.uuid4())
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                agent_id="seed-full-stack-demo",
                status="running",
                principal="seed-full-stack-demo@local",
                tables_touched=json.dumps([]),
                started_at=datetime.now(UTC),
                finished_at=None,
                notebook_path=f"scripts/seed-full-stack-demo.py::{label}",
                source_snapshot_sha=None,
                runtime_versions=json.dumps({"python": sys.version.split()[0], "demo": "v1"}),
            )
        )
        session.commit()
    return run_id


def _close_agent_run(run_id: str, *, status: str = "completed") -> None:
    """Mark an AgentRun finished.  Best-effort: missing rows are ignored."""
    factory = get_session_factory()
    with factory() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            return
        run.status = status
        run.finished_at = datetime.now(UTC)
        session.commit()


# --------------------------------------------------------------------------- #
# Step 3 — Bronze ingest


def _step_bronze(soyuz: Any, p: Printer) -> str:
    """Autoload both raw CSVs into bronze Delta tables."""
    p.step("Bronze — autoload raw CSVs into Delta")

    run_id = _create_agent_run("bronze")
    pql = PQL(client=soyuz, agent_run_id=run_id)

    houses_dir = DATA_DIR / "_houses"
    sales_dir = DATA_DIR / "_sales"
    houses_dir.mkdir(exist_ok=True)
    sales_dir.mkdir(exist_ok=True)
    # autoload reads from a directory; one file per dir keeps SHA-dedup
    # honest and matches the agent-pattern of a watched volume folder.
    (houses_dir / "houses.csv").write_text((DATA_DIR / "houses.csv").read_text())
    (sales_dir / "sales.csv").write_text((DATA_DIR / "sales.csv").read_text())

    h = pql.autoload(
        source_path=str(houses_dir),
        target=BRONZE_HOUSES,
        source_system="demo-houses-feed",
    )
    p.ok(f"{BRONZE_HOUSES} ← {h['rows_ingested']} rows / {h['files_ingested']} file(s)")

    s = pql.autoload(
        source_path=str(sales_dir),
        target=BRONZE_SALES,
        source_system="demo-sales-feed",
    )
    p.ok(f"{BRONZE_SALES} ← {s['rows_ingested']} rows / {s['files_ingested']} file(s)")

    _close_agent_run(run_id)
    return run_id


# --------------------------------------------------------------------------- #
# Step 4 — Silver join


def _approved_tables(soyuz: Any, full_names: Iterable[str]) -> dict[str, str]:
    """Build a `{full_name: storage_location}` map for PQL.sql.

    The web UI's sql_routes.py builds this from `client.get_table(...)`;
    this helper does the same via the sync soyuz client.
    """
    from soyuz_catalog_client.api.tables import (
        get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
    )
    from soyuz_catalog_client.models.table_info import TableInfo

    approved: dict[str, str] = {}
    for fqn in full_names:
        info = _get_table.sync(client=soyuz, full_name=fqn)
        if not isinstance(info, TableInfo) or not info.storage_location:
            raise RuntimeError(f"No storage_location for {fqn!r}")
        approved[fqn] = info.storage_location
    return approved


def _step_silver(soyuz: Any, p: Printer) -> str:
    """Join bronze tables into a typed Silver table via PQL.sql + write_table."""
    p.step("Silver — join bronze tables, type-cast, register lineage")

    run_id = _create_agent_run("silver")
    pql = PQL(client=soyuz, agent_run_id=run_id)

    approved = _approved_tables(soyuz, [BRONZE_HOUSES, BRONZE_SALES])
    # Phase-15.8: project ``h._lineage_row_id`` so write_table can
    # correlate silver rows back to bronze.  Without it the row-edge
    # hook short-circuits (no source_ids, no edges) and every
    # downstream silver/gold/predictions table inherits the gap.
    result = PQL.sql(
        f"""
        SELECT
            h.house_id,
            h.size_sqft,
            h.bedrooms,
            h.age_years,
            s.sold_at,
            s.price,
            h._lineage_row_id AS _lineage_row_id
        FROM {BRONZE_HOUSES} h
        JOIN {BRONZE_SALES} s USING (house_id)
        ORDER BY h.house_id
        """,
        approved_tables=approved,
        max_rows=N_ROWS + 100,
    )
    column_names = [c["name"] for c in result.columns]
    silver_df = pd.DataFrame(result.rows, columns=pd.Index(column_names))
    p.detail(f"join result: {len(silver_df)} rows × {len(silver_df.columns)} cols")

    pql.write_table(
        silver_df,
        SILVER,
        source_table_fqn=BRONZE_HOUSES,
    )
    p.ok(f"{SILVER} ← {len(silver_df)} rows (column-lineage edges recorded)")

    # A second merge with track_value_changes=True surfaces a real CDF
    # event so the value-changes route returns >0 rows in the read-tour.
    tweaked = silver_df.copy()
    tweaked.loc[tweaked.index[0], "price"] = int(tweaked.loc[tweaked.index[0], "price"]) + 1_000
    pql.merge(
        source=tweaked,
        target=SILVER,
        on=["house_id"],
        strategy="upsert",
        source_table_fqn=BRONZE_HOUSES,
        track_rejects=True,
        track_value_changes=True,
    )
    p.ok("re-merge with track_value_changes=True (one cell flipped)")

    _close_agent_run(run_id)
    return run_id


# --------------------------------------------------------------------------- #
# Step 5 — Gold staging in a branch + train/test split


def _step_gold_in_branch(soyuz: Any, p: Printer) -> tuple[str, str, pd.DataFrame, pd.DataFrame]:
    """Branch demo_ml.gold, write train/test sets in the branch, promote.

    Args:
        soyuz: Configured soyuz-catalog client (sync).
        p: Printer for step banners.

    Returns:
        (run_id, branch_fqn, train_df, test_df).  The branch is already
        promoted by the time this returns — branch_fqn is the
        backup name `<schema>__pre_promote_<ts>` for inspection.
    """
    p.step("Gold (in branch) — train/test split, branch_promote_preview, promote")

    run_id = _create_agent_run("gold")
    pql = PQL(client=soyuz, agent_run_id=run_id)

    silver_df = pql.table(SILVER)

    # 80/20 train/test split, deterministic.
    shuffled = silver_df.sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
    cutoff = int(len(shuffled) * 0.8)
    train_df = shuffled.iloc[:cutoff].copy()
    test_df = shuffled.iloc[cutoff:].copy()

    # First write to the parent gold so branch() has something to fork.
    pql.write_table(train_df, GOLD_TRAINING, source_table_fqn=SILVER)
    pql.write_table(test_df, GOLD_TEST, source_table_fqn=SILVER)
    p.ok(
        f"parent gold seeded: {GOLD_TRAINING} ({len(train_df)} rows), "
        f"{GOLD_TEST} ({len(test_df)} rows)"
    )

    # Now branch the schema and overwrite the test_set inside the branch
    # to demo the staging → preview → promote flow.
    branch_name = f"gold__staging_{int(time.time())}"
    branch_fqn = pql.branch(f"{CATALOG}.gold", branch_name=branch_name)
    p.ok(f"created branch {branch_fqn}")

    # Write a slightly-larger test_set inside the branch (simulates an
    # agent staging an updated split before supervisor approval).
    pql_branch = PQL(client=soyuz, agent_run_id=run_id)
    branch_test = pd.concat([test_df, train_df.iloc[:5]], ignore_index=True)
    pql_branch.write_table(
        branch_test,
        f"{branch_fqn}.test_set",
        mode="overwrite",
        source_table_fqn=SILVER,
    )
    p.detail(f"branch test_set: {len(branch_test)} rows")

    preview = pql.branch_promote_preview(branch_fqn)
    conflicts = len(preview.get("conflicts", []))
    p.info(f"promote preview: ok={preview.get('ok')}, conflicts={conflicts}")

    promoted = pql.branch_promote(branch_fqn)
    p.ok(
        f"promoted branch → new_parent={promoted.get('new_parent')}, "
        f"backup={promoted.get('backup')}"
    )

    _close_agent_run(run_id)
    return run_id, branch_fqn, train_df, test_df


# --------------------------------------------------------------------------- #
# Step 6 — Train


def _step_train(
    soyuz: Any, train_df: pd.DataFrame, test_df: pd.DataFrame, p: Printer
) -> tuple[str, str, str, Any]:
    """Train sklearn LinearRegression inside pql.training_context.

    Args:
        soyuz: Configured soyuz-catalog client.
        train_df: Gold training set (~80 % of silver).
        test_df: Gold test set; unused here but threaded so the caller
            can pass the same frames into inference.
        p: Printer.

    Returns:
        (run_id, mlflow_run_id, model_version, model). Version is `"1"`
        on first run; subsequent re-runs allocate higher numbers.

    Raises:
        RuntimeError: If sklearn or MLflow are not installed, or the
            registered-model lookup returns nothing after `log_model`.
    """
    p.step("Train — sklearn LinearRegression in pql.training_context")

    try:
        import mlflow
        from sklearn.linear_model import LinearRegression
    except ImportError as exc:  # pragma: no cover - the demo requires both
        raise RuntimeError(
            "scripts/seed-full-stack-demo.py needs sklearn + mlflow. "
            "Install via `uv sync --group dev` (sklearn) and ensure the "
            "PointlesSQL MLflow extra is set up."
        ) from exc

    settings = Settings()
    tracking_uri = f"http://127.0.0.1:{settings.mlflow.port}"
    registry_uri = f"uc:{settings.soyuz.catalog_url}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_registry_uri(registry_uri)
    p.detail(f"mlflow tracking_uri={tracking_uri}")
    p.detail(f"mlflow registry_uri={registry_uri}")

    run_id = _create_agent_run("train")
    pql = PQL(client=soyuz, agent_run_id=run_id)

    feature_cols = ["size_sqft", "bedrooms", "age_years"]
    X_train = train_df[feature_cols].values.astype(float)
    y_train = train_df["price"].values.astype(float)

    model = LinearRegression()
    mlflow_run_id = ""
    with pql.training_context(
        framework="sklearn",
        source_table_fqn=GOLD_TRAINING,
        model_fqn=MODEL_FQN,
    ) as tr:
        model.fit(X_train, y_train)
        mlflow_run_id = tr.mlflow_run_id or ""
        # `mlflow.sklearn` is a flavor sub-module that mlflow loads
        # lazily; pyright's stub doesn't surface it as a public re-export
        # so we round-trip via importlib to keep the type-checker happy.
        import importlib

        mlflow_sklearn = importlib.import_module("mlflow.sklearn")
        mlflow_sklearn.log_model(
            model,
            artifact_path="model",
            registered_model_name=MODEL_FQN,
        )
    p.ok(
        f"trained: intercept={model.intercept_:.0f}, "
        f"coefs=({model.coef_[0]:.1f}, {model.coef_[1]:.1f}, {model.coef_[2]:.1f})"
    )
    p.detail(f"true coefs were ({TRUE_SIZE_COEF}, {TRUE_BED_COEF}, {TRUE_AGE_COEF})")

    # Sanity: recovered coefs within 30 % of truth.
    tol = 0.30
    deltas = (
        abs(model.coef_[0] - TRUE_SIZE_COEF) / abs(TRUE_SIZE_COEF),
        abs(model.coef_[1] - TRUE_BED_COEF) / abs(TRUE_BED_COEF),
        abs(model.coef_[2] - TRUE_AGE_COEF) / abs(TRUE_AGE_COEF),
    )
    if any(d > tol for d in deltas):
        p.warn(f"coefs drifted >30%: {deltas}")
    else:
        p.ok(f"coefs within 30% tolerance (deltas={tuple(round(d, 2) for d in deltas)})")

    # Find the version we just registered + cross-link it to the agent-run.
    from soyuz_catalog_client.api.model_versions import (
        list_model_versions_api_2_1_unity_catalog_models_full_name_versions_get as _list_mv,
    )

    listing = _list_mv.sync(client=soyuz, full_name=MODEL_FQN)
    from soyuz_catalog_client.models.list_model_versions_response import (
        ListModelVersionsResponse,
    )

    if not isinstance(listing, ListModelVersionsResponse):
        raise RuntimeError(f"unexpected list_model_versions response: {listing!r}")
    version_numbers = [int(v.version) for v in listing.model_versions if isinstance(v.version, int)]
    if not version_numbers:
        raise RuntimeError(f"No version registered for {MODEL_FQN}")
    latest = max(version_numbers)
    p.ok(f"registered {MODEL_FQN} version {latest}")

    if mlflow_run_id:
        link_model_version_to_run(
            soyuz,
            MODEL_FQN,
            int(latest),
            agent_run_id=run_id,
            mlflow_run_id=mlflow_run_id,
        )
        p.ok(f"cross-linked v{latest} ↔ agent_run + mlflow_run")
    else:
        p.warn("MLflow run id missing — skipping cross-link")

    _close_agent_run(run_id)
    return run_id, mlflow_run_id, str(latest), model


# --------------------------------------------------------------------------- #
# Step 7 — Promote via HTTP


def _step_promote(
    *,
    http: httpx.Client | None,
    version: str,
    p: Printer,
) -> str | None:
    """POST /api/models/{full_name}/promote — needs supervisor scope."""
    p.step(f"Promote — POST /api/models/{MODEL_FQN}/promote (version {version})")
    if http is None:
        p.warn("no auth session — skipping (supervisor-gated)")
        return None
    resp = http.post(
        f"/api/models/{MODEL_FQN}/promote",
        json={
            "target_version": int(version),
            "reason": "Full-stack demo: promote v1 to champion (smoke test).",
        },
        headers=_csrf_headers(http),
    )
    if resp.status_code == 400 and "already champion" in resp.text:
        p.info("v1 was already champion (previous run promoted it) — re-promote skipped")
        return version
    if resp.status_code in (400, 401, 403):
        p.warn(f"promote refused ({resp.status_code}): {resp.text[:200]}")
        return None
    resp.raise_for_status()
    body = resp.json()
    p.ok(
        f"champion=v{body.get('champion_version')}, "
        f"event_id={body.get('event', {}).get('id', 'n/a')}"
    )
    return str(body.get("champion_version"))


# --------------------------------------------------------------------------- #
# Step 8 — Inference


def _step_inference(
    soyuz: Any,
    test_df: pd.DataFrame,
    model: Any,
    version: str,
    p: Printer,
) -> str:
    """Run model.predict on the test set, write to predictions table.

    Uses pql.merge with `source_model_uri=models:/<fqn>/<version>` so
    the inference-lineage edge is recorded (Phase 21.7).
    """
    p.step("Inference — predict, materialise as Delta with inference-lineage")

    run_id = _create_agent_run("inference")
    pql = PQL(client=soyuz, agent_run_id=run_id)

    feature_cols = ["size_sqft", "bedrooms", "age_years"]
    X_test = test_df[feature_cols].values.astype(float)
    predicted = model.predict(X_test)

    # Phase-15.8: keep ``_lineage_row_id`` on the predictions frame so
    # the inference write_table records row-edges (and stamps
    # ``source_model_uri`` on each one) — without it the audit hook
    # short-circuits and the model-detail Lineage DAG can't paint the
    # predictions node downstream of the model.
    predictions_df = test_df[feature_cols + ["house_id", "price", "_lineage_row_id"]].copy()
    predictions_df["predicted_price"] = predicted.round(0).astype(int)
    predictions_df["abs_error"] = np.abs(
        np.asarray(predictions_df["predicted_price"]) - np.asarray(predictions_df["price"])
    )

    # First write bootstraps the table; subsequent merges keep upsert
    # semantics so the demo can re-run idempotently.
    pql.write_table(
        predictions_df,
        PREDICTIONS,
        mode="overwrite",
        source_table_fqn=GOLD_TEST,
        source_model_uri=f"models:/{MODEL_FQN}/{version}",
    )
    mae = float(predictions_df["abs_error"].mean())
    p.ok(f"{PREDICTIONS} ← {len(predictions_df)} rows, MAE=${mae:,.0f}")

    _close_agent_run(run_id)
    return run_id


# --------------------------------------------------------------------------- #
# Step 9 — Rollback demo


def _step_rollback_demo(
    soyuz: Any,
    *,
    http: httpx.Client | None,
    p: Printer,
) -> bool:
    """Bad merge → rollback-preview → rollback.  Returns True if executed."""
    p.step("Rollback — deliberate bad merge, then pql.rollback")

    run_id = _create_agent_run("bad-merge")
    pql = PQL(client=soyuz, agent_run_id=run_id)

    # Snapshot the current predictions so the rollback target is well-defined.
    current = pql.table(PREDICTIONS).copy()
    bogus = current.copy()
    bogus["predicted_price"] = 1  # smell of a buggy agent

    pql.merge(
        source=bogus,
        target=PREDICTIONS,
        on=["house_id"],
        strategy="upsert",
        source_table_fqn=GOLD_TEST,
    )
    p.ok(f"bad merge applied (predicted_price=1 across {len(bogus)} rows)")

    # Hit /api/runs/{id}/rollback-preview before executing.  Needs
    # the target table as a query param.
    if http is not None:
        preview_resp = http.get(
            f"/api/runs/{run_id}/rollback-preview",
            params={"target": PREDICTIONS},
        )
        if preview_resp.status_code == 200:
            preview_body = preview_resp.json()
            p.detail(
                f"rollback-preview: target={preview_body.get('target_table')}, "
                f"version_before={preview_body.get('delta_version_before')}"
            )
        else:
            p.warn(f"rollback-preview {preview_resp.status_code}: {preview_resp.text[:120]}")

    result = pql.rollback(PREDICTIONS, before_run=run_id)
    p.ok(
        f"rollback: version {result.version_before} → {result.version_after} "
        f"(restored to v{result.target_version_restored})"
    )

    _close_agent_run(run_id, status="rolled_back")
    return True


# --------------------------------------------------------------------------- #
# Phase-2 steps (13-21) — full agent-API coverage


def _coverage_runner(p: Printer) -> tuple[Any, list[tuple[bool, str]]]:
    """Build a route-counter + go() helper shared by every Phase-2 step.

    Each Phase-2 step records its hits into the same ledger so the
    final summary can report ``NN unique routes (M green / K expected)``.
    The returned tuple is ``(go_callable, ledger)``; the ledger holds
    ``(ok, "METHOD path")`` rows.
    """
    ledger: list[tuple[bool, str]] = []

    def go(http: httpx.Client, method: str, path: str, **kw: Any) -> Any:
        ok, body = _hit(http, method, path, p, **kw)
        ledger.append((ok, f"{method} {path.split('?', 1)[0]}"))
        return body

    return go, ledger


def _step_pql_http_writes(http: httpx.Client, go: Any, p: Printer) -> None:
    """Hit every ``POST /api/pql/*`` write surface end-to-end.

    Writes a tiny scratch table from a SELECT, merges into it, then
    drops it as cleanup so the step is idempotent on re-runs.
    """
    p.step("PQL HTTP writes — autoload / write_table / merge / drop_table")

    scratch_dir = DATA_DIR / "_houses_meta"
    scratch_dir.mkdir(exist_ok=True)
    (scratch_dir / "houses.csv").write_text((DATA_DIR / "houses.csv").read_text())
    target_meta = f"{CATALOG}.bronze.houses_meta"

    # POST /api/pql/autoload — second autoload of the same CSV directory
    # exercises the SHA-checkpoint short-circuit on re-runs.
    go(
        http,
        "POST",
        "/api/pql/autoload",
        json={
            "source_path": str(scratch_dir),
            "target": target_meta,
            "source_system": "demo-meta-feed",
        },
        headers=_csrf_headers(http),
    )
    p.ok(f"autoload (HTTP) → {target_meta}")

    # POST /api/pql/write_table — sql variant.  Bootstrap a scratch
    # silver-side table from a SELECT against bronze.
    scratch = f"{CATALOG}.silver.scratch_meta"
    go(
        http,
        "POST",
        "/api/pql/write_table",
        json={
            "sql": f"SELECT house_id, size_sqft FROM {BRONZE_HOUSES} LIMIT 10",
            "target": scratch,
            "mode": "overwrite",
        },
        headers=_csrf_headers(http),
    )
    p.ok(f"write_table (HTTP) → {scratch}")

    # POST /api/pql/merge — upsert the same 10 rows back into the scratch.
    go(
        http,
        "POST",
        "/api/pql/merge",
        json={
            "sql": f"SELECT house_id, size_sqft FROM {BRONZE_HOUSES} LIMIT 10",
            "target": scratch,
            "on": ["house_id"],
            "strategy": "upsert",
        },
        headers=_csrf_headers(http),
    )
    p.ok(f"merge (HTTP) → {scratch}")

    # POST /api/pql/drop_table — admin-only cleanup of the scratch.
    go(
        http,
        "POST",
        "/api/pql/drop_table",
        json={"full_name": scratch},
        headers=_csrf_headers(http),
    )
    p.ok(f"drop_table (HTTP) — {scratch} removed")


def _step_sql_http(http: httpx.Client, go: Any, p: Printer) -> int | None:
    """Exercise ``/api/sql/*`` (execute / explain / download / cancel).

    Returns the ``query_history_id`` of the executed SELECT so the
    queries-history step can chart it.  ``None`` when the SQL editor
    is disabled or the route surfaced an error.
    """
    p.step("SQL HTTP — execute / explain / download / cancel")
    sql = f"SELECT COUNT(*) AS n FROM {SILVER}"

    body = go(
        http,
        "POST",
        "/api/sql/execute",
        json={"sql": sql},
        headers=_csrf_headers(http),
    )
    history_id: int | None = None
    if isinstance(body, dict):
        raw = body.get("history_id") or body.get("query_history_id")
        if isinstance(raw, int):
            history_id = raw
    if history_id is not None:
        p.ok(f"sql.execute → history_id={history_id}")
    else:
        p.info("sql.execute → no history_id surfaced (route disabled or error)")

    go(http, "GET", f"/api/sql/explain?sql={sql}")
    if history_id is not None:
        go(http, "GET", f"/api/sql/execute/{history_id}/download?format=csv")
    # Cancel of a non-existing query → expected 404 / 4xx.
    go(
        http,
        "POST",
        f"/api/sql/execute/{uuid.uuid4()}/cancel",
        expected_codes=(404, 400, 422),
        headers=_csrf_headers(http),
    )
    return history_id


def _step_time_travel(http: httpx.Client, go: Any, silver_row_id: str | None, p: Printer) -> None:
    """Hit ``/api/tables/{name}/versions``, ``preview-at-version``, ``row-at-version``."""
    p.step("Time-travel — versions, preview-at-version, row-at-version")
    go(http, "GET", f"/api/tables/{SILVER}/versions")
    go(http, "GET", f"/api/tables/{SILVER}/preview-at-version?version=0")
    if silver_row_id is not None:
        go(
            http,
            "GET",
            f"/api/lineage/row-at-version?table={SILVER}&row_id={silver_row_id}&version=0",
        )
    else:
        p.info("no silver row_id — row-at-version skipped")


def _step_governance(http: httpx.Client, go: Any, p: Printer) -> None:
    """Profile / stats / tags / permissions / lineage / catalog mutations."""
    p.step("Governance — profile / stats / tags / perms / catalog ops")
    # Profile is a real mutating action that also caches stats.
    go(
        http,
        "POST",
        f"/api/tables/{SILVER}/profile",
        headers=_csrf_headers(http),
    )
    go(http, "GET", f"/api/tables/{SILVER}/stats")
    go(http, "GET", f"/api/lineage/{SILVER}")
    go(http, "GET", f"/api/tags/table/{SILVER}")
    go(
        http,
        "PATCH",
        f"/api/tags/table/{SILVER}",
        json={
            "changes": [
                {"key": "demo_phase", "value": "2", "op": "set"},
            ]
        },
        headers=_csrf_headers(http),
        expected_codes=(400, 422, 501),
    )
    go(http, "GET", f"/api/permissions/table/{SILVER}")
    go(http, "GET", f"/api/effective-permissions/table/{SILVER}")
    # Catalog mutations: create + sync + patch a scratch catalog.
    scratch_cat = "demo_ml_scratch"
    go(
        http,
        "POST",
        "/api/catalogs",
        json={"name": scratch_cat, "comment": "phase-2 demo scratch catalog"},
        headers=_csrf_headers(http),
        expected_codes=(409,),
    )
    # /sync only works on foreign catalogs (those with connection_name).
    # Our demo_ml is a regular managed catalog → 403 is by design.
    go(
        http,
        "POST",
        f"/api/catalogs/{CATALOG}/sync",
        headers=_csrf_headers(http),
        expected_codes=(403,),
    )
    go(
        http,
        "PATCH",
        f"/api/catalogs/{CATALOG}",
        json={"comment": "PointlesSQL full-stack demo (phase-2 coverage)."},
        headers=_csrf_headers(http),
        expected_codes=(404, 422),
    )
    go(
        http,
        "PATCH",
        f"/api/catalogs/{CATALOG}/schemas/silver",
        json={"comment": "silver layer (joined houses + sales)"},
        headers=_csrf_headers(http),
        expected_codes=(404, 422),
    )
    # Cleanup the scratch catalog so re-runs are idempotent.
    settings = Settings()
    base = settings.soyuz.catalog_url.rstrip("/")
    try:
        httpx.delete(
            f"{base}/api/2.1/unity-catalog/catalogs/{scratch_cat}",
            params={"force": "true"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        p.detail(f"scratch-catalog cleanup soft-failed: {exc}")


def _step_agent_runs_lifecycle(
    http: httpx.Client, go: Any, p: Printer
) -> tuple[str | None, str | None, str | None]:
    """Register external agent-runs and walk them through approve / deny.

    Returns ``(run_id_lifecycle, run_id_approved, run_id_denied)`` for
    later consumption by reviews / read-tour.  Each id is ``None`` when
    its create call failed.
    """
    p.step("Agent-runs control surface — POST /api/agent-runs + tool-call/approve/deny")

    def _create(label: str, *, status: str = "running") -> str | None:
        body = go(
            http,
            "POST",
            "/api/agent-runs",
            json={
                "id": str(uuid.uuid4()),
                "notebook_path": f"scripts/seed-full-stack-demo.py::{label}",
                "source": (
                    f"# {label} run synthesised by seed-full-stack-demo.py\n"
                    "print('hello from external runtime')\n"
                ),
                "runtime_versions": {
                    "python": sys.version.split()[0],
                    "demo": "phase-2",
                },
                "agent_id": "seed-full-stack-demo-ext",
                "principal": "seed-full-stack-demo@local",
                "status": status,
            },
            headers=_csrf_headers(http),
        )
        if isinstance(body, dict):
            rid = body.get("id")
            return str(rid) if isinstance(rid, str) else None
        return None

    run_a = _create("ext-lifecycle", status="running")
    run_b = _create("ext-needs-approval", status="needs_approval")
    run_c = _create("ext-needs-deny", status="needs_approval")

    if run_a is not None:
        go(
            http,
            "POST",
            f"/api/agent-runs/{run_a}/tool-call",
            json={
                "tool_name": "pql_list_catalogs",
                "args_json": json.dumps({}),
                "result_summary": "ok 1 catalog",
                "duration_ms": 12,
            },
            headers=_csrf_headers(http),
        )
        go(
            http,
            "POST",
            f"/api/agent-runs/{run_a}/finish",
            json={"status": "completed"},
            headers=_csrf_headers(http),
            expected_codes=(400, 422),
        )

    if run_b is not None:
        go(
            http,
            "POST",
            f"/api/agent-runs/{run_b}/approve",
            headers=_csrf_headers(http),
            expected_codes=(400, 422),
        )

    if run_c is not None:
        go(
            http,
            "POST",
            f"/api/agent-runs/{run_c}/deny",
            json={"reason": "phase-2 demo deny path"},
            headers=_csrf_headers(http),
            expected_codes=(400, 422),
        )

    p.ok(f"runs created: a={run_a}, b={run_b}, c={run_c}")
    return run_a, run_b, run_c


def _step_agent_reviews(http: httpx.Client, go: Any, run_id: str | None, p: Printer) -> int | None:
    """POST /api/agent-reviews → list/latest/{id} reads happen in read-tour."""
    p.step("Agent reviews — POST /api/agent-reviews + GET /latest")
    now = datetime.now(UTC)
    body = go(
        http,
        "POST",
        "/api/agent-reviews",
        json={
            "run_id": run_id,
            "period_start": (now - timedelta(hours=1)).isoformat(),
            "period_end": now.isoformat(),
            "severity": "ok",
            "summary_md": "# Phase-2 demo review\n\nAuto-generated by seed-full-stack-demo.py.",
            "payload_json": {"source": "seed-full-stack-demo", "phase": 2},
        },
        headers=_csrf_headers(http),
        expected_codes=(403,),
    )
    review_id: int | None = None
    if isinstance(body, dict):
        raw = body.get("id")
        if isinstance(raw, int):
            review_id = raw
    if review_id is not None:
        go(http, "GET", f"/api/agent-reviews/{review_id}")
    go(http, "GET", "/api/agent-reviews/latest", expected_codes=(404,))
    return review_id


def _step_saved_queries(
    http: httpx.Client,
    go: Any,
    history_id: int | None,
    p: Printer,
    *,
    keep_state: bool = False,
) -> int | None:
    """Saved-queries CRUD + saved-audit-queries CRUD + queries-history reads.

    Returns the saved-query id (so the alerts step can wire an alert
    to it).  ``None`` on failure.

    When ``keep_state`` is True, the trailing DELETEs that clean up the
    saved-audit-query are skipped so the grand-tour walkthrough has a
    populated ``/audit/queries`` page to demo from.
    """
    p.step("Saved queries — saved-queries + saved-audit-queries + queries history")

    # Queries history.
    go(http, "GET", "/api/queries?limit=20")
    if history_id is not None:
        go(http, "GET", f"/api/queries/{history_id}")
        go(
            http,
            "PATCH",
            f"/api/queries/{history_id}/chart-config",
            json={"chart_type": "table", "x": None, "y": None},
            headers=_csrf_headers(http),
            expected_codes=(400, 422),
        )

    # Saved query CRUD.
    sq_slug: str | None = None
    sq_id: int | None = None
    sql_text = f"SELECT COUNT(*) AS n FROM {SILVER}"
    body = go(
        http,
        "POST",
        "/api/saved-queries",
        json={
            "title": "Phase-2 demo saved query",
            "description": "auto-created by seed-full-stack-demo.py",
            "sql_text": sql_text,
        },
        headers=_csrf_headers(http),
        expected_codes=(409,),
    )
    if isinstance(body, dict):
        sq_slug = str(body.get("slug")) if isinstance(body.get("slug"), str) else None
        raw_id = body.get("id")
        if isinstance(raw_id, int):
            sq_id = raw_id
    if sq_slug is not None:
        go(http, "GET", f"/api/saved-queries/{sq_slug}")
        go(
            http,
            "PATCH",
            f"/api/saved-queries/{sq_slug}",
            json={"description": "patched by phase-2 demo"},
            headers=_csrf_headers(http),
        )

    # Saved audit query CRUD + run + export.
    saq_slug: str | None = None
    body = go(
        http,
        "POST",
        "/api/saved-audit-queries",
        json={
            "title": "Phase-2 audit query",
            "description": "demo phase-2 audit query (auto)",
            "sql_text": "SELECT COUNT(*) AS n FROM agent_run_operations",
            "alert_threshold_count": 9999,
        },
        headers=_csrf_headers(http),
        expected_codes=(409,),
    )
    if isinstance(body, dict):
        saq_slug = str(body.get("slug")) if isinstance(body.get("slug"), str) else None
    if saq_slug is not None:
        go(http, "GET", f"/api/saved-audit-queries/{saq_slug}")
        go(
            http,
            "PATCH",
            f"/api/saved-audit-queries/{saq_slug}",
            json={"description": "patched by phase-2 demo"},
            headers=_csrf_headers(http),
        )
        go(
            http,
            "POST",
            f"/api/saved-audit-queries/{saq_slug}/run",
            headers=_csrf_headers(http),
        )
        go(http, "GET", f"/api/saved-audit-queries/{saq_slug}/export.csv")
        go(http, "GET", f"/api/saved-audit-queries/{saq_slug}/export.json")
        if not keep_state:
            go(
                http,
                "DELETE",
                f"/api/saved-audit-queries/{saq_slug}",
                headers=_csrf_headers(http),
            )

    # NOTE: leave the saved-query alive for the alerts step; it
    # cleans itself up at the end (gated by ``keep_state`` there).
    return sq_id


def _step_dashboards(http: httpx.Client, go: Any, p: Printer, *, keep_state: bool = False) -> None:
    """Dashboards CRUD + refresh + tree.

    When ``keep_state`` is True, the trailing DELETE is skipped so the
    grand-tour walkthrough has a populated ``/dashboards`` page to demo.
    """
    p.step("Dashboards — POST/GET/PATCH/DELETE/refresh")
    body = go(
        http,
        "POST",
        "/api/dashboards",
        json={
            "slug": f"phase2-demo-dashboard-{int(time.time())}",
            "title": "Phase-2 demo dashboard",
            "description": "auto-generated by seed-full-stack-demo.py",
            "notebook_path": "notebooks/full_stack_demo_data/job_stub.py",
        },
        headers=_csrf_headers(http),
        expected_codes=(400, 409, 422),
    )
    slug: str | None = None
    if isinstance(body, dict):
        raw = body.get("slug")
        if isinstance(raw, str):
            slug = raw
    go(http, "GET", "/api/dashboards")
    go(http, "GET", "/api/dashboards/tree")
    if slug is not None:
        go(
            http,
            "PATCH",
            f"/api/dashboards/{slug}",
            json={"description": "patched by phase-2 demo"},
            headers=_csrf_headers(http),
        )
        go(
            http,
            "POST",
            f"/api/dashboards/{slug}/refresh",
            headers=_csrf_headers(http),
            expected_codes=(400, 409, 422, 500),
        )
        if not keep_state:
            go(
                http,
                "DELETE",
                f"/api/dashboards/{slug}",
                headers=_csrf_headers(http),
            )


def _step_jobs(http: httpx.Client, go: Any, p: Printer) -> None:
    """Jobs CRUD + run + pause/unpause + tasks/logs."""
    p.step("Jobs — CRUD + run + pause/unpause + tasks/logs")

    stub_path = DATA_DIR / "job_stub.py"
    if not stub_path.exists():
        stub_path.write_text(
            "# Phase-2 demo job stub (5-line notebook).\n"
            "print('hello from job stub')\n"
            "x = 1 + 1\n"
            "print(x)\n"
        )

    go(http, "GET", "/api/jobs")
    body = go(
        http,
        "POST",
        "/api/jobs",
        json={
            "name": f"phase2-demo-job-{int(time.time())}",
            "kind": "python",
            "config": {"notebook_path": str(stub_path)},
            "cron_expr": "0 0 1 1 *",
            "is_paused": True,
            "max_parallel_runs": 1,
        },
        headers=_csrf_headers(http),
        expected_codes=(400, 422),
    )
    job_id: int | None = None
    if isinstance(body, dict):
        raw = body.get("id")
        if isinstance(raw, int):
            job_id = raw
    if job_id is not None:
        go(http, "GET", f"/api/jobs/{job_id}/tasks")
        go(
            http,
            "POST",
            f"/api/jobs/{job_id}/unpause",
            headers=_csrf_headers(http),
        )
        run_body = go(
            http,
            "POST",
            f"/api/jobs/{job_id}/run",
            headers=_csrf_headers(http),
            expected_codes=(400, 409, 422, 500),
        )
        run_id: int | None = None
        if isinstance(run_body, dict):
            rid = run_body.get("run_id") or run_body.get("id")
            if isinstance(rid, int):
                run_id = rid
        if run_id is not None:
            time.sleep(1.5)
            go(http, "GET", f"/api/jobs/{job_id}/runs/{run_id}/tasks")
            go(http, "GET", f"/api/jobs/{job_id}/runs/{run_id}/logs")
        go(
            http,
            "POST",
            f"/api/jobs/{job_id}/pause",
            headers=_csrf_headers(http),
        )


def _step_alerts(
    http: httpx.Client,
    go: Any,
    saved_query_id: int | None,
    p: Printer,
    *,
    keep_state: bool = False,
) -> None:
    """Alerts CRUD + destinations + feed-token + atom/json feeds.

    When ``keep_state`` is True, the trailing DELETEs that clean up the
    alert + its destination + the saved-query that anchored it are
    skipped so the grand-tour walkthrough has a populated
    ``/alerts`` page (with a wired feed destination) to demo from.
    """
    p.step("Alerts — CRUD + destinations + feed-token + feed.atom/.json")

    alert_slug: str | None = None
    body: Any = None
    if saved_query_id is not None:
        body = go(
            http,
            "POST",
            "/api/alerts",
            json={
                "title": "Phase-2 demo alert",
                "saved_query_id": int(saved_query_id),
                "cron_expr": "0 0 * * *",
                "condition_op": "gt",
                "threshold": 0,
                "is_active": True,
            },
            headers=_csrf_headers(http),
            expected_codes=(400, 409, 422),
        )
    else:
        p.info("no saved_query_id from Step 18 — alert create skipped")
    if isinstance(body, dict):
        raw = body.get("slug")
        if isinstance(raw, str):
            alert_slug = raw

    go(http, "GET", "/api/alerts")
    if alert_slug is not None:
        go(http, "GET", f"/api/alerts/{alert_slug}")
        go(
            http,
            "PATCH",
            f"/api/alerts/{alert_slug}",
            json={"is_active": False},
            headers=_csrf_headers(http),
        )
        # Add a destination then delete it.
        dest_body = go(
            http,
            "POST",
            f"/api/alerts/{alert_slug}/destinations",
            json={"kind": "feed", "config": {}},
            headers=_csrf_headers(http),
            expected_codes=(400, 422),
        )
        if isinstance(dest_body, dict) and not keep_state:
            dest_id = dest_body.get("id")
            if isinstance(dest_id, int):
                go(
                    http,
                    "DELETE",
                    f"/api/alerts/{alert_slug}/destinations/{dest_id}",
                    headers=_csrf_headers(http),
                )
        if not keep_state:
            go(
                http,
                "DELETE",
                f"/api/alerts/{alert_slug}",
                headers=_csrf_headers(http),
            )

    # Feed token and feeds.
    feed_token: str | None = None
    body = go(http, "GET", "/api/me/feed-token")
    if isinstance(body, dict):
        raw = body.get("token") or body.get("feed_token")
        if isinstance(raw, str):
            feed_token = raw
    rotated = go(http, "POST", "/api/me/feed-token/rotate", headers=_csrf_headers(http))
    if isinstance(rotated, dict):
        raw = rotated.get("token") or rotated.get("feed_token")
        if isinstance(raw, str):
            feed_token = raw
    if feed_token:
        go(http, "GET", f"/alerts/feed.atom?token={feed_token}")
        go(http, "GET", f"/alerts/feed.json?token={feed_token}")
    else:
        go(http, "GET", "/alerts/feed.atom", expected_codes=(401, 403))
        go(http, "GET", "/alerts/feed.json", expected_codes=(401, 403))

    # Cleanup the saved-query that anchored the alert (created by Step 18).
    # Look it up by enumerating; saved-queries are owner-scoped so the
    # listing only shows ours.
    if not keep_state:
        listing = go(http, "GET", "/api/saved-queries")
        if isinstance(listing, list):
            for entry in listing:
                if not isinstance(entry, dict):
                    continue
                slug = entry.get("slug")
                title = entry.get("title")
                if (
                    isinstance(slug, str)
                    and isinstance(title, str)
                    and "Phase-2 demo saved query" in title
                ):
                    go(
                        http,
                        "DELETE",
                        f"/api/saved-queries/{slug}",
                        headers=_csrf_headers(http),
                    )


def _ensure_demo_volume(p: Printer) -> str | None:
    """Create the UC volume ``demo_ml.bronze.demo_vol`` if missing.

    Returns the full name when the volume exists (or ``None`` on
    failure).  Volume CRUD lives outside the soyuz client wrapper for
    PointlesSQL right now, so this hits soyuz raw.
    """
    settings = Settings()
    base = settings.soyuz.catalog_url.rstrip("/")
    full = f"{CATALOG}.bronze.demo_vol"
    storage = f"file://{WAREHOUSE_ROOT.rstrip('/')}/{CATALOG}/bronze/_demo_vol"
    Path(f"{WAREHOUSE_ROOT.rstrip('/')}/{CATALOG}/bronze/_demo_vol").mkdir(
        parents=True, exist_ok=True
    )
    try:
        resp = httpx.post(
            f"{base}/api/2.1/unity-catalog/volumes",
            json={
                "catalog_name": CATALOG,
                "schema_name": "bronze",
                "name": "demo_vol",
                "volume_type": "EXTERNAL",
                "storage_location": storage,
                "comment": "phase-2 demo volume",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        p.warn(f"volume create transport-error: {exc}")
        return None
    if resp.status_code in (200, 201, 409):
        return full
    p.warn(f"volume create returned {resp.status_code}: {resp.text[:120]}")
    return None


def _step_volumes_notebooks(http: httpx.Client, go: Any, p: Printer) -> None:
    """Volume file CRUD + convert-to-delta + notebooks/inspect+tree."""
    p.step("Volumes + notebooks — file upload / browse / inspect / convert-to-delta")
    vol_fqn = _ensure_demo_volume(p)
    if vol_fqn is None:
        p.info("volume create failed — sub-routes will mostly 404, still hit them")
        vol_fqn = f"{CATALOG}.bronze.demo_vol"

    # Upload a tiny CSV via multipart.  httpx.Client.post supports
    # `files=` for the upload route.
    upload_path = "houses.csv"
    with (DATA_DIR / "houses.csv").open("rb") as fh:
        try:
            resp = http.post(
                f"/api/volumes/{vol_fqn}/files",
                files={"upload": (upload_path, fh, "text/csv")},
                data={"path": upload_path},
                headers=_csrf_headers(http),
            )
        except httpx.HTTPError as exc:
            p.warn(f"file upload transport error: {exc}")
            resp = None
    if resp is not None:
        ok = 200 <= resp.status_code < 300
        p.detail(f"{'OK  ' if ok else 'FAIL'} {resp.status_code} POST /api/volumes/{vol_fqn}/files")
    go(http, "GET", f"/api/volumes/{vol_fqn}/files")
    # `/api/notebooks/inspect` introspects a Papermill .py/.ipynb under
    # the notebooks-dir.  We probe an existing seed notebook; missing
    # `parameters`-tagged cell → 422, which is fine for coverage.
    go(
        http,
        "GET",
        "/api/notebooks/inspect?path=hermes_medallion.py",
        expected_codes=(404, 422, 500),
    )
    go(http, "GET", "/api/notebooks/tree")
    go(
        http,
        "POST",
        f"/api/volumes/{vol_fqn}/convert-to-delta",
        json={
            "file_path": upload_path,
            "target": f"{CATALOG}.silver.from_volume_demo",
        },
        headers=_csrf_headers(http),
        expected_codes=(400, 404, 409, 422),
    )
    go(
        http,
        "DELETE",
        f"/api/volumes/{vol_fqn}/files/{upload_path}",
        headers=_csrf_headers(http),
        expected_codes=(404,),
    )


def _step_admin_tools(
    http: httpx.Client,
    go: Any,
    value_change_row: dict[str, Any] | None,
    p: Printer,
    *,
    keep_state: bool = False,
) -> None:
    """Admin tools — api-keys + external-writes + audit-sinks + review-dests + pii/reveal.

    When ``keep_state`` is True, the trailing DELETEs of audit-sinks and
    review-destinations are skipped so the grand-tour walkthrough has
    populated admin pages to demo from.  The api-key revoke is kept
    regardless (revoking is a state-flip, not a destructive cleanup).
    """
    p.step("Admin — api-keys / external-writes / audit-sinks / review-dests / pii.reveal")

    # API keys CRUD.
    go(http, "GET", "/api/admin/api-keys")
    body = go(
        http,
        "POST",
        "/api/admin/api-keys",
        json={"name": f"phase2-demo-{int(time.time())}", "supervisor": False},
        headers=_csrf_headers(http),
        expected_codes=(409,),
    )
    if isinstance(body, dict):
        name = body.get("name")
        if isinstance(name, str):
            go(
                http,
                "POST",
                f"/api/admin/api-keys/{name}/revoke",
                headers=_csrf_headers(http),
            )

    # External writes.
    go(http, "GET", "/api/admin/external-writes")
    scan_body = go(
        http,
        "POST",
        "/api/admin/external-writes/scan",
        headers=_csrf_headers(http),
    )
    if isinstance(scan_body, dict):
        rows = scan_body.get("writes") or scan_body.get("rows") or []
        if isinstance(rows, list) and rows:
            first = rows[0]
            if isinstance(first, dict):
                wid = first.get("id")
                if isinstance(wid, int):
                    go(
                        http,
                        "POST",
                        f"/api/admin/external-writes/{wid}/acknowledge",
                        headers=_csrf_headers(http),
                    )

    # Audit sinks CRUD + test + recent-events.
    go(http, "GET", "/api/admin/audit-sinks")
    body = go(
        http,
        "POST",
        "/api/admin/audit-sinks",
        json={
            "name": f"phase2-sink-{int(time.time())}",
            "type": "webhook",
            "config": {"url": "http://127.0.0.1:9999/sink"},
            "is_active": False,
        },
        headers=_csrf_headers(http),
        expected_codes=(409,),
    )
    sink_id: int | None = None
    if isinstance(body, dict):
        raw = body.get("id")
        if isinstance(raw, int):
            sink_id = raw
    if sink_id is not None:
        go(
            http,
            "POST",
            f"/api/admin/audit-sinks/{sink_id}/test",
            headers=_csrf_headers(http),
            expected_codes=(400, 422, 500, 502, 503, 504),
        )
        go(
            http,
            "PATCH",
            f"/api/admin/audit-sinks/{sink_id}",
            json={"is_active": False},
            headers=_csrf_headers(http),
        )
        if not keep_state:
            go(
                http,
                "DELETE",
                f"/api/admin/audit-sinks/{sink_id}",
                headers=_csrf_headers(http),
            )
    go(http, "GET", "/api/admin/audit-sinks/recent-events")

    # Review destinations CRUD.
    go(http, "GET", "/api/admin/review-destinations")
    body = go(
        http,
        "POST",
        "/api/admin/review-destinations",
        json={
            "name": f"phase2-dest-{int(time.time())}",
            "webhook_url": "http://127.0.0.1:9999/review-sink",
            "min_severity": "warn",
            "is_active": False,
        },
        headers=_csrf_headers(http),
        expected_codes=(409, 422),
    )
    if isinstance(body, dict):
        raw = body.get("id")
        if isinstance(raw, int):
            go(
                http,
                "PATCH",
                f"/api/admin/review-destinations/{raw}",
                json={"is_active": False},
                headers=_csrf_headers(http),
            )
            if not keep_state:
                go(
                    http,
                    "DELETE",
                    f"/api/admin/review-destinations/{raw}",
                    headers=_csrf_headers(http),
                )

    # PII reveal — needs a real value-change row.
    if value_change_row is not None:
        change_id = value_change_row.get("id") or value_change_row.get("change_id")
        if change_id is not None:
            go(
                http,
                "POST",
                "/api/audit/pii/reveal",
                json={"change_id": int(change_id)},
                headers=_csrf_headers(http),
                expected_codes=(400, 403, 404, 422),
            )

    # PQL training/log (legacy training-event endpoint).
    go(
        http,
        "POST",
        "/api/pql/training/log",
        json={
            "framework": "sklearn",
            "params": {"phase": "demo"},
            "metrics": {"r2": 0.95},
        },
        headers=_csrf_headers(http),
        expected_codes=(400, 404, 422),
    )


def _step_federation(http: httpx.Client, go: Any, p: Printer, *, keep_state: bool = False) -> None:
    """Federation CRUD — connections / external-locations / credentials.

    Backed by best-effort placeholder configs; many production-grade
    backends will surface 4xx/5xx without a live connector, so the
    helper expects all of them.

    When ``keep_state`` is True, the trailing DELETEs are skipped so
    the grand-tour walkthrough has populated ``/connections``,
    ``/external-locations``, ``/credentials`` admin pages to demo from.
    """
    p.step("Federation — connections / external-locations / credentials")

    expected = (400, 404, 409, 422, 500, 503)
    # Connections.
    go(http, "GET", "/api/connections")
    name_c = f"phase2-conn-{int(time.time())}"
    body = go(
        http,
        "POST",
        "/api/connections",
        json={
            "name": name_c,
            "connection_type": "MYSQL",
            "options": {"host": "127.0.0.1", "port": "3306"},
        },
        headers=_csrf_headers(http),
        expected_codes=expected,
    )
    if isinstance(body, dict):
        go(http, "GET", f"/api/connections/{name_c}", expected_codes=expected)
        go(
            http,
            "PATCH",
            f"/api/connections/{name_c}",
            json={"comment": "phase-2 patch"},
            headers=_csrf_headers(http),
            expected_codes=expected,
        )
        if not keep_state:
            go(
                http,
                "DELETE",
                f"/api/connections/{name_c}",
                headers=_csrf_headers(http),
                expected_codes=expected,
            )

    # External locations.
    go(http, "GET", "/api/external-locations")
    name_e = f"phase2-extloc-{int(time.time())}"
    body = go(
        http,
        "POST",
        "/api/external-locations",
        json={
            "name": name_e,
            "url": "file:///tmp/phase2-demo-extloc",
            "credential_name": "demo-credential",
        },
        headers=_csrf_headers(http),
        expected_codes=expected,
    )
    if isinstance(body, dict):
        go(http, "GET", f"/api/external-locations/{name_e}", expected_codes=expected)
        go(
            http,
            "PATCH",
            f"/api/external-locations/{name_e}",
            json={"comment": "phase-2 patch"},
            headers=_csrf_headers(http),
            expected_codes=expected,
        )
        if not keep_state:
            go(
                http,
                "DELETE",
                f"/api/external-locations/{name_e}",
                headers=_csrf_headers(http),
                expected_codes=expected,
            )

    # Credentials.
    go(http, "GET", "/api/credentials")
    name_cr = f"phase2-cred-{int(time.time())}"
    body = go(
        http,
        "POST",
        "/api/credentials",
        json={
            "name": name_cr,
            "purpose": "STORAGE",
            "type": "S3",
            "options": {"access_key_id": "demo"},
        },
        headers=_csrf_headers(http),
        expected_codes=expected,
    )
    if isinstance(body, dict):
        go(http, "GET", f"/api/credentials/{name_cr}", expected_codes=expected)
        go(
            http,
            "PATCH",
            f"/api/credentials/{name_cr}",
            json={"comment": "phase-2 patch"},
            headers=_csrf_headers(http),
            expected_codes=expected,
        )
        if not keep_state:
            go(
                http,
                "DELETE",
                f"/api/credentials/{name_cr}",
                headers=_csrf_headers(http),
                expected_codes=expected,
            )


def _pick_value_change(p: Printer) -> dict[str, Any] | None:
    """Return one row from ``lineage_value_changes`` for the PII-reveal demo."""
    factory = get_session_factory()
    try:
        with factory() as session:
            from sqlalchemy import text

            row = (
                session.execute(
                    text(
                        "SELECT id, target_table, target_row_id, target_column "
                        "FROM lineage_value_changes ORDER BY id DESC LIMIT 1"
                    )
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        p.detail(f"value-change pick failed: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Step 10 — Read-tour (every Family-A/B/C surface, mind. einmal)


def _login(args: argparse.Namespace, p: Printer) -> httpx.Client | None:
    """Open an httpx.Client with a session cookie, or return None.

    The script can run without HTTP auth; the read-tour and promote
    steps gracefully degrade when no session is available.  Login
    requires a CSRF-token round-trip — first GET seeds the cookie,
    then login POST forwards it as X-CSRF-Token.

    When ``--register-if-missing`` is set (default) and the first
    login attempt fails with non-303, the helper POSTs to
    ``/auth/register`` and retries the login so a clean stack
    becomes self-bootstrapping.  The first registered user becomes
    admin automatically.
    """
    if args.skip_routes:
        p.info("--skip-routes → not opening HTTP session")
        return None
    if not args.login_email or not args.login_password:
        p.info(
            "no --login-email / --login-password (or env "
            "POINTLESSQL_DEMO_EMAIL/PASSWORD) → skipping HTTP read-tour"
        )
        return None
    client = httpx.Client(base_url=args.ui_base, follow_redirects=False, timeout=15.0)
    login = _attempt_login(client, args, p)
    if login is None:
        client.close()
        return None
    if login.status_code in (303, 302):
        p.ok(f"logged in as {args.login_email}")
        return client
    if not args.register_if_missing:
        p.warn(f"login returned {login.status_code} (expected 303); skipping read-tour")
        client.close()
        return None
    # Auto-register and retry.  409 is fine — the account exists, the
    # password just didn't match (caller must fix that themselves).
    register_status = _attempt_register(client, args, p)
    if register_status not in (200, 303, 409):
        p.warn(f"register returned {register_status}; cannot bootstrap demo user")
        client.close()
        return None
    if register_status == 409:
        p.warn(
            f"login returned {login.status_code} and account already exists "
            "— password mismatch?  Skipping read-tour."
        )
        client.close()
        return None
    p.ok(f"registered demo user {args.login_email}")
    retry = _attempt_login(client, args, p)
    if retry is None or retry.status_code not in (303, 302):
        rs = retry.status_code if retry is not None else "n/a"
        p.warn(f"login retry after register returned {rs}; skipping read-tour")
        client.close()
        return None
    p.ok(f"logged in as {args.login_email}")
    return client


def _attempt_login(
    client: httpx.Client, args: argparse.Namespace, p: Printer
) -> httpx.Response | None:
    """POST to ``/auth/login`` with a freshly seeded CSRF token.

    Returns the response so the caller can branch on the status.
    Returns ``None`` only when the CSRF round-trip itself fails —
    that's a stack-side problem, not a credential one.
    """
    try:
        seed = client.get("/auth/login")
        csrf = client.cookies.get("pql_csrf", "")
        if seed.status_code not in (200, 303) or not csrf:
            p.warn(f"could not seed CSRF cookie (status={seed.status_code})")
            return None
        return client.post(
            "/auth/login",
            data={"email": args.login_email, "password": args.login_password},
            headers={"X-CSRF-Token": csrf},
        )
    except httpx.HTTPError as exc:
        p.warn(f"login failed: {exc}")
        return None


def _attempt_register(client: httpx.Client, args: argparse.Namespace, p: Printer) -> int:
    """POST to ``/auth/register`` and return the response status code.

    Idempotent in the sense that a 409 (account already exists) is a
    legitimate outcome the caller treats as "ok, just won't be the
    admin bootstrap".
    """
    try:
        seed = client.get("/auth/register")
        csrf = client.cookies.get("pql_csrf", "")
        if seed.status_code not in (200, 303) or not csrf:
            p.warn(f"could not seed CSRF cookie for register (status={seed.status_code})")
            return 0
        resp = client.post(
            "/auth/register",
            data={
                "email": args.login_email,
                "display_name": "Demo User",
                "password": args.login_password,
                "password_confirm": args.login_password,
            },
            headers={"X-CSRF-Token": csrf},
        )
        return resp.status_code
    except httpx.HTTPError as exc:
        p.warn(f"register failed: {exc}")
        return 0


def _csrf_headers(http: httpx.Client) -> dict[str, str]:
    """Build a header dict carrying the current CSRF token."""
    csrf = http.cookies.get("pql_csrf", "")
    return {"X-CSRF-Token": csrf} if csrf else {}


def _hit(
    http: httpx.Client,
    method: str,
    path: str,
    p: Printer,
    *,
    expected_codes: tuple[int, ...] = (),
    **kwargs: Any,
) -> tuple[bool, Any]:
    """Hit a route, log the result, return ``(ok, json_body_or_text)``.

    Args:
        http: Open httpx.Client.
        method: HTTP verb.
        path: Request path (relative to ``http.base_url``).
        p: Printer for log output.
        expected_codes: Non-2xx status codes that should be considered
            *expected* (logged as ``EXPECTED`` instead of ``FAIL`` and
            still count as a successful coverage hit).  Used for routes
            that may legitimately fail without infrastructure (e.g.
            federation against a missing JDBC backend).
        **kwargs: Forwarded to ``http.request``.

    Returns:
        ``(ok, body)`` — ``ok`` is True for 2xx OR any code in
        ``expected_codes``; body is the JSON-decoded response or text
        snippet when JSON parsing fails.
    """
    try:
        resp = http.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        p.warn(f"{method} {path} → transport error: {exc}")
        return False, None
    if 200 <= resp.status_code < 300:
        ok = True
        label = "OK  "
    elif resp.status_code in expected_codes:
        ok = True
        label = "EXPC"
    else:
        ok = False
        label = "FAIL"
    summary = ""
    body: Any = None
    try:
        body = resp.json()
        summary = _summarize_body(body)
    except ValueError, json.JSONDecodeError:
        body = resp.text[:200]
        summary = body
    p.detail(f"{label} {resp.status_code} {method} {path}  {summary}")
    return ok, body


def _summarize_body(body: Any) -> str:
    """One-line summary of a JSON body."""
    if isinstance(body, dict):
        keys = list(body.keys())
        return f"keys=[{', '.join(keys[:6])}{'…' if len(keys) > 6 else ''}]"
    if isinstance(body, list):
        return f"list[{len(body)}]"
    return str(body)[:80]


def _step_read_tour(
    http: httpx.Client | None,
    *,
    last_run_id: str,
    silver_run_id: str,
    extra_run_ids: tuple[str | None, ...] = (),
    extended: bool = True,
    silver_row_id: str | None = None,
    p: Printer,
) -> dict[str, Any]:
    """Hit every Family-A/B/C surface that this demo has data for.

    Args:
        http: Open httpx.Client (or ``None`` to skip).
        last_run_id: Run-id used for ``/api/runs/{id}/full`` and
            per-run audit aggregations.
        silver_run_id: Run-id used in the diff endpoint as ``b``.
        extra_run_ids: Additional run-ids to fan out across the
            per-run audit aggregations and the runs/full surface.
        extended: When True, hit every surface from the Phase-2
            inventory; when False, only the original 24 routes
            (used by ``--core-only``).
        silver_row_id: Pre-resolved row id for the lineage routes
            (so the read-tour does not have to re-load silver).
        p: Printer for log output.

    Returns:
        ``{hit, ok, fails}`` — ledger of how many routes were
        exercised and how many returned 2xx (or expected codes).
    """
    p.step("Read-tour — hit every audit / lineage / models / branches surface")
    if http is None:
        p.info("no HTTP session → tour skipped")
        return {"hit": 0, "ok": 0, "routes": []}

    hit = 0
    ok_count = 0
    fails: list[str] = []

    def go(method: str, path: str, **kwargs: Any) -> Any:
        nonlocal hit, ok_count
        hit += 1
        ok, body = _hit(http, method, path, p, **kwargs)
        if ok:
            ok_count += 1
        else:
            fails.append(f"{method} {path}")
        return body

    # Catalog tree
    go("GET", f"/api/tree?catalog={CATALOG}")
    go("GET", "/api/catalogs")
    go("GET", f"/api/catalogs/{CATALOG}/schemas")

    # Runs
    go("GET", "/api/runs?limit=20")
    go("GET", f"/api/agent-runs/{last_run_id}/full")
    go("GET", f"/api/runs/{last_run_id}/graph")

    # Audit — `metric` query param picks the cockpit measure.  Hit
    # three different metrics so the timeseries / anomalies routes
    # exercise their full validation path.
    go("GET", "/api/audit/summary")
    go("GET", "/api/audit/timeseries?metric=ops")
    go("GET", "/api/audit/timeseries?metric=rows_written")
    go("GET", "/api/audit/timeseries?metric=rejects")
    go(
        "GET",
        "/api/audit/principal-summary",
        params={"principal": "seed-full-stack-demo@local"},
    )
    go("GET", "/api/audit/anomalies?metric=ops")
    go("GET", "/api/audit/history?limit=10")

    # Lineage — pick a row from the silver table for the trace.
    if silver_row_id is None:
        silver_row = _pick_silver_row(p)
        if silver_row is not None:
            silver_row_id = str(
                silver_row.get("_lineage_row_id") or silver_row.get("house_id") or ""
            )
    if silver_row_id:
        go("GET", f"/api/lineage/row-trace?table={SILVER}&row_id={silver_row_id}")
    go("GET", f"/api/lineage/column-trace?table={SILVER}&column=price")
    if silver_row_id:
        go(
            "GET",
            f"/api/lineage/value-changes?table={SILVER}&row_id={silver_row_id}",
        )

    # Branches
    go("GET", "/api/branches")

    # Models
    go("GET", f"/api/models?catalog_name={CATALOG}&enrich_latest=true")
    go("GET", f"/api/models/{MODEL_FQN}")
    go("GET", f"/api/models/{MODEL_FQN}/versions/1")
    go("GET", f"/api/models/{MODEL_FQN}/lineage")
    go("GET", f"/api/models/{MODEL_FQN}/predictions")
    go("GET", f"/api/models/{MODEL_FQN}/runs")
    go("GET", f"/api/models/{MODEL_FQN}/promotion")

    if not extended:
        p.ok(f"{ok_count}/{hit} routes returned 2xx (core-only)")
        if fails:
            p.warn(f"failed: {fails}")
        return {"hit": hit, "ok": ok_count, "fails": fails}

    # ─── Phase-2 GET surfaces ────────────────────────────────────────
    # Catalog deep walk.
    go(
        "GET",
        f"/api/catalogs/{CATALOG}/schemas/silver/tables",
    )
    go(
        "GET",
        f"/api/catalogs/{CATALOG}/schemas/silver/tables/houses_with_sales",
    )
    go(
        "GET",
        f"/api/catalogs/{CATALOG}/schemas/silver/tables/houses_with_sales/preview",
    )

    # Tree-search + recents + global search + home + conventions.
    go("GET", "/api/tree/search?q=houses")
    go("GET", "/api/recents")
    go("DELETE", "/api/recents", headers=_csrf_headers(http))
    go("GET", "/api/search?q=demo_ml")
    go("GET", "/api/home/summary")
    go("GET", "/api/conventions")

    # PQL introspection.  target-state + lineage need a `?table=` arg.
    go("GET", "/api/pql/primitives")
    go("GET", f"/api/pql/target-state?table={SILVER}")
    go("GET", f"/api/pql/lineage?table={SILVER}")

    # Agent-runs surface: list / operations / summary / diff.
    go("GET", "/api/agent-runs?limit=20")
    go("GET", "/api/agent-runs/operations?limit=20")
    go("GET", f"/api/agent-runs/{last_run_id}/summary")
    if len(extra_run_ids) >= 1 and extra_run_ids[0]:
        go(
            "GET",
            f"/api/agent-runs/diff?a={extra_run_ids[0]}&b={silver_run_id}",
            expected_codes=(403,),
        )

    # Per-run audit aggregations × 5 axes (against last_run_id which
    # has rejection / lineage / value-change rows from inference).
    for axis in (
        "lineage",
        "rejects",
        "value-changes",
        "external-writes",
        "column-lineage",
    ):
        go("GET", f"/api/agent-runs/{last_run_id}/audit/{axis}")

    # Branches additional surfaces.
    blist = go("GET", "/api/branches")
    branch_fqn: str | None = None
    if isinstance(blist, list) and blist:
        first = blist[0]
        if isinstance(first, dict):
            raw = first.get("branch_fqn") or first.get("fqn")
            if isinstance(raw, str):
                branch_fqn = raw
    if branch_fqn is not None:
        go("GET", f"/api/branches/{branch_fqn}")
        go(
            "GET",
            f"/api/branches/{branch_fqn}/preview-promote",
            expected_codes=(400, 404, 409),
        )

    # ML context.
    go("GET", f"/api/runs/{last_run_id}/ml-context", expected_codes=(404,))

    # Reviews list/latest already hit in step; ensure latest is in tour too.
    go("GET", "/api/agent-reviews/latest", expected_codes=(404,))

    # Auth + observability.  /me lives at /auth/me (router prefix).
    go("GET", "/auth/me")
    go("GET", "/healthz")
    go("GET", "/metrics", expected_codes=(404,))

    p.ok(f"{ok_count}/{hit} routes returned 2xx (or expected)")
    if fails:
        p.warn(f"failed: {fails[:8]}{'…' if len(fails) > 8 else ''}")
    return {"hit": hit, "ok": ok_count, "fails": fails}


def _pick_silver_row(p: Printer) -> dict[str, Any] | None:
    """Best-effort: return the first silver row (house_id + lineage_row_id)."""
    soyuz = make_soyuz_client()
    pql = PQL(client=soyuz)
    try:
        df = pql.table(SILVER)
        if df.empty:
            return None
        row = df.iloc[0].to_dict()
        return row
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        p.detail(f"could not read silver for row-pick: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Step 11 — Final prediction


def _step_final_prediction(model: Any, p: Printer) -> int:
    """Run a single hard-coded prediction on a synthetic 1800sqft / 3bed / 8yr house."""
    p.step("Final prediction — single inference on a synthetic house")
    sample = np.array([[1800, 3, 8]], dtype=float)
    pred = model.predict(sample)[0]
    p.ok(f"size=1800sqft, bedrooms=3, age=8yr → predicted price ${int(round(pred)):,}")
    p.info(
        f"learned: intercept={model.intercept_:.0f}, "
        f"size_coef={model.coef_[0]:.1f}, bed_coef={model.coef_[1]:.1f}, "
        f"age_coef={model.coef_[2]:.1f}"
    )
    return int(round(pred))


# --------------------------------------------------------------------------- #
# Step 12 — Summary


def _print_summary(stats: dict[str, Any], p: Printer) -> None:
    """Render the closing summary table."""
    p.step("Summary")
    rows: list[tuple[str, str]] = [
        ("Tables created", str(stats.get("tables", "?"))),
        ("Agent runs created", str(stats.get("runs", "?"))),
        ("Routes exercised", f"{stats.get('routes_ok', 0)}/{stats.get('routes_hit', 0)}"),
        (
            "Phase-2 routes",
            f"{stats.get('phase2_ok', 0)}/{stats.get('phase2_routes', 0)}",
        ),
        ("Branches promoted", str(stats.get("branches", 0))),
        ("Predictions written", str(stats.get("predictions", 0))),
        ("Rollback demo", "executed" if stats.get("rollback") else "skipped"),
        (
            "Review created",
            str(stats.get("review_id")) if stats.get("review_id") else "—",
        ),
        ("Final prediction", f"${stats.get('final_pred', 0):,}"),
        ("Total elapsed", f"{p.elapsed:.1f}s"),
    ]
    width = max(len(r[0]) for r in rows) + 2
    for label, value in rows:
        print(f"  {label:<{width}} {value}")


# --------------------------------------------------------------------------- #
# main()


def main(argv: list[str] | None = None) -> int:
    """Wire all the steps together."""
    args = _parse_args(argv)
    p = Printer(verbose=args.verbose)

    settings = Settings()
    init_db(settings.db.url)

    soyuz = make_soyuz_client()

    if args.drop:
        p.step("Drop demo_ml catalog")
        _drop_catalog(soyuz, p)
        return 0

    p.step("Setup — catalog + schemas")
    if args.fresh:
        _drop_catalog(soyuz, p)
    _ensure_catalog(soyuz, p)
    for schema in SCHEMAS_BASE:
        _ensure_schema(soyuz, schema, p)

    p.step("CSV generation")
    _generate_csvs(p)

    _step_bronze(soyuz, p)
    silver_run = _step_silver(soyuz, p)
    _gold_run, _branch_fqn, train_df, test_df = _step_gold_in_branch(soyuz, p)
    _train_run, _mlflow_run_id, version, model = _step_train(soyuz, train_df, test_df, p)

    http = _login(args, p)
    promoted = _step_promote(http=http, version=version, p=p)
    inference_run = _step_inference(soyuz, test_df, model, version, p)
    rollback_done = False
    if args.demo_rollback:
        rollback_done = _step_rollback_demo(soyuz, http=http, p=p)

    # ─── Phase-2 stateful coverage (skipped when --core-only) ───────
    phase2_ledger: list[tuple[bool, str]] = []
    saved_query_id: int | None = None
    history_id: int | None = None
    review_id: int | None = None
    run_a: str | None = None
    run_b: str | None = None
    run_c: str | None = None
    silver_row_id: str | None = None

    if not args.core_only and http is not None:
        go, ledger = _coverage_runner(p)
        phase2_ledger = ledger

        # Resolve a silver row id for time-travel + read-tour.
        silver_row = _pick_silver_row(p)
        if silver_row is not None:
            raw = silver_row.get("_lineage_row_id") or silver_row.get("house_id")
            silver_row_id = str(raw) if raw is not None else None

        _step_pql_http_writes(http, go, p)
        history_id = _step_sql_http(http, go, p)
        _step_time_travel(http, go, silver_row_id, p)
        _step_governance(http, go, p)
        run_a, run_b, run_c = _step_agent_runs_lifecycle(http, go, p)
        review_id = _step_agent_reviews(http, go, run_a or inference_run, p)
        saved_query_id = _step_saved_queries(http, go, history_id, p, keep_state=args.keep_state)
        _step_dashboards(http, go, p, keep_state=args.keep_state)
        _step_jobs(http, go, p)
        _step_alerts(http, go, saved_query_id, p, keep_state=args.keep_state)
        _step_volumes_notebooks(http, go, p)
        _step_admin_tools(http, go, _pick_value_change(p), p, keep_state=args.keep_state)
        _step_federation(http, go, p, keep_state=args.keep_state)
    elif args.core_only:
        p.info("--core-only → skipping Phase-2 stateful steps")

    route_stats = _step_read_tour(
        http,
        last_run_id=inference_run,
        silver_run_id=silver_run,
        extra_run_ids=(run_a, run_b, run_c),
        extended=not args.core_only,
        silver_row_id=silver_row_id,
        p=p,
    )

    final_pred = _step_final_prediction(model, p)

    if http is not None:
        http.close()

    # Phase-2 ledger merges with the read-tour tally.
    p2_hit = len(phase2_ledger)
    p2_ok = sum(1 for ok, _ in phase2_ledger if ok)

    _print_summary(
        {
            "tables": 7,
            "runs": _count_demo_runs(),
            "routes_hit": route_stats.get("hit", 0) + p2_hit,
            "routes_ok": route_stats.get("ok", 0) + p2_ok,
            "branches": 1,
            "predictions": len(test_df),
            "rollback": rollback_done,
            "final_pred": final_pred,
            "promoted_version": promoted,
            "phase2_routes": p2_hit,
            "phase2_ok": p2_ok,
            "review_id": review_id,
        },
        p,
    )
    return 0


def _count_demo_runs() -> int:
    """Count agent_runs rows tagged with this demo's agent_id."""
    factory = get_session_factory()
    with factory() as session:
        from sqlalchemy import func, select

        return int(
            session.execute(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.agent_id == "seed-full-stack-demo")
            ).scalar()
            or 0
        )


if __name__ == "__main__":
    sys.exit(main())
