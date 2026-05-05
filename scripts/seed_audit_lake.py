r"""Seed a synthetic audit lake for the Sprint-30.5 perf baseline.

Generates rows in ``agent_runs``, ``agent_run_operations``,
``agent_run_tool_calls``, ``lineage_row_edges``, and
``lineage_value_changes`` at three scales: 10 k, 100 k, 1 M
parent runs.  Idempotent — uses a deterministic seed so repeated
runs produce the same output (handy for diffing perf numbers
across PG configs).

Targets either backend via ``POINTLESSQL_DB_URL``.

Usage:

.. code-block:: shell

    POINTLESSQL_DB_URL=postgresql+psycopg://...@localhost/pointlessql \\
        uv run python scripts/seed_audit_lake.py --runs 10000

    # smaller smoke profile
    uv run python scripts/seed_audit_lake.py --runs 100 --no-children

The script does NOT clean up after itself; drop the target DB
between scale runs to keep numbers comparable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import random
import time
import uuid
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from pointlessql.db import _alembic_config

logger = logging.getLogger("seed_audit_lake")


_TABLES_TOUCHED = (
    '["main.bronze.events"]',
    '["main.silver.orders"]',
    '["main.gold.daily_summary"]',
    '["main.bronze.events", "main.silver.orders"]',
)
_AGENT_IDS = ("scout-bot", "ingest-bot", "audit-reviewer", "compliance-bot")
_TOOL_NAMES = (
    "pql_query",
    "pql_autoload",
    "pql_merge",
    "pql_write_table",
    "pql_drop_table",
    "pql_describe",
)


def _ensure_alembic_at_head(url: str) -> None:
    """Run ``alembic upgrade head`` against the target if needed."""
    from alembic import command  # noqa: PLC0415

    cfg = _alembic_config(url)
    command.upgrade(cfg, "head")


def _seed_runs(
    factory: Any,
    *,
    n_runs: int,
    seed: int,
    include_children: bool,
    batch_size: int = 500,
) -> dict[str, int]:
    """Insert ``n_runs`` agent_runs (and proportional children).

    Args:
        factory: SQLAlchemy session factory.
        n_runs: Number of parent ``agent_runs`` rows to create.
        seed: Random seed for deterministic output.
        include_children: When ``True``, fan out 5–20 ops, 10–50
            tool calls, and 100–500 lineage edges per run.
        batch_size: Rows per ``add_all`` flush.

    Returns:
        Per-table count of rows created.
    """
    rng = random.Random(seed)
    counts: dict[str, int] = {
        "agent_runs": 0,
        "agent_run_operations": 0,
        "agent_run_tool_calls": 0,
        "lineage_row_edges": 0,
        "lineage_value_changes": 0,
    }

    started_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=30)
    with factory() as session:
        for i in range(0, n_runs, batch_size):
            chunk_end = min(i + batch_size, n_runs)
            for j in range(i, chunk_end):
                run_id = str(uuid.UUID(int=rng.getrandbits(128)))
                run_started = started_at + dt.timedelta(seconds=j * 30)
                session.execute(
                    text(
                        "INSERT INTO agent_runs "
                        "(id, principal, agent_id, notebook_path, "
                        "source_snapshot_sha, status, started_at, "
                        "tables_touched, workspace_id) "
                        "VALUES (:id, :principal, :agent_id, :notebook, "
                        "        :sha, 'succeeded', :started, :tables, 1)"
                    ),
                    {
                        "id": run_id,
                        "principal": f"agent-{j % 50}@test",
                        "agent_id": _AGENT_IDS[j % len(_AGENT_IDS)],
                        "notebook": f"jobs/job_{j}.py",
                        "sha": "0" * 64,
                        "started": run_started,
                        "tables": _TABLES_TOUCHED[j % len(_TABLES_TOUCHED)],
                    },
                )
                counts["agent_runs"] += 1

                if not include_children:
                    continue

                n_ops = rng.randint(5, 20)
                for k in range(n_ops):
                    session.execute(
                        text(
                            "INSERT INTO agent_run_operations "
                            "(agent_run_id, ordinal, op_name, params_json, "
                            "target_table, started_at, finished_at, "
                            "rows_affected, workspace_id) "
                            "VALUES (:run, :ord, :op, '{}', :tgt, :started, "
                            "        :finished, :rows, 1)"
                        ),
                        {
                            "run": run_id,
                            "ord": k,
                            "op": rng.choice(("merge", "write_table", "autoload", "sql")),
                            "tgt": f"main.silver.t_{rng.randint(0, 99)}",
                            "started": run_started,
                            "finished": run_started + dt.timedelta(seconds=k),
                            "rows": rng.randint(1, 1000),
                        },
                    )
                    counts["agent_run_operations"] += 1

                n_tool_calls = rng.randint(10, 50)
                for k in range(n_tool_calls):
                    session.execute(
                        text(
                            "INSERT INTO agent_run_tool_calls "
                            "(agent_run_id, tool_name, args_json, "
                            "called_at, duration_ms, workspace_id) "
                            "VALUES (:run, :tool, '{}', :called, :dur, 1)"
                        ),
                        {
                            "run": run_id,
                            "tool": rng.choice(_TOOL_NAMES),
                            "called": run_started + dt.timedelta(milliseconds=k * 100),
                            "dur": rng.randint(10, 5000),
                        },
                    )
                    counts["agent_run_tool_calls"] += 1
            session.commit()
            logger.info("seeded %d/%d runs", chunk_end, n_runs)
    return counts


def _print_counts(counts: dict[str, int]) -> None:
    print()
    print(f"{'table':<35} {'rows':>10}")
    print("-" * 50)
    for tname, n in counts.items():
        print(f"{tname:<35} {n:>10}")


def main() -> int:
    """CLI entry."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    p.add_argument("--runs", type=int, default=10_000, help="Number of agent_runs to seed.")
    p.add_argument("--seed", type=int, default=42, help="Random seed (deterministic).")
    p.add_argument(
        "--no-children",
        action="store_true",
        help="Skip ops/tool_calls/lineage children — runs only.",
    )
    p.add_argument(
        "--db-url",
        default=os.environ.get("POINTLESSQL_DB_URL"),
        help="Target DB URL.  Falls back to POINTLESSQL_DB_URL.",
    )
    args = p.parse_args()

    if not args.db_url:
        print("error: --db-url or POINTLESSQL_DB_URL required", flush=True)
        return 2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    print(f"target = {args.db_url}", flush=True)
    print(f"runs   = {args.runs}", flush=True)
    print(f"seed   = {args.seed}", flush=True)
    print(f"include_children = {not args.no_children}", flush=True)
    print(flush=True)

    _ensure_alembic_at_head(args.db_url)
    engine = create_engine(args.db_url)
    factory = sessionmaker(bind=engine)

    started = time.monotonic()
    counts = _seed_runs(
        factory,
        n_runs=args.runs,
        seed=args.seed,
        include_children=not args.no_children,
    )
    elapsed = time.monotonic() - started

    _print_counts(counts)
    print(flush=True)
    print(f"elapsed = {elapsed:.1f}s", flush=True)
    engine.dispose()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
