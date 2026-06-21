"""Cockpit data builders shared by the HTML page and its JSON siblings.

The command center reframes the flat ``/runs`` list around two
questions a reviewer actually asks when several agents work at once:
*what is in flight right now* and *which of these competing attempts
should I keep*.  The first is answered by filtering to the non-terminal
runs (the "live threads"); the second by grouping runs that share a
``notebook_path`` into candidate sets and surfacing a recommended pick.

Everything is derived from the existing agent-run metadata via the
``runs_routes`` loaders, so the cockpit never opens a second source of
truth — it only re-shapes what ``/runs`` already exposes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Request

from pointlessql.api.runs_routes._loaders import load_operations_for_run, load_runs
from pointlessql.api.runs_routes._shared import load_run
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models.agent._runs import (
    STATUS_NEEDS_APPROVAL,
    STATUS_SUCCEEDED,
    TERMINAL_STATUSES,
    VALID_STATUSES,
)

# A run is a "live thread" until it reaches a terminal state.  Derived
# from the canonical sets so a future status lands on the right side
# automatically.
IN_FLIGHT_STATUSES: frozenset[str] = VALID_STATUSES - TERMINAL_STATUSES

# Hard cap on how many runs one comparison can fan across, so a crafted
# query string cannot turn the compare endpoint into an N-session fetch.
MAX_COMPARE_RUNS = 6


def _duration_ms(started_at: str | None, finished_at: str | None) -> int | None:
    """Return the wall-clock duration between two ISO timestamps in ms.

    Both ends must be present and parseable; a still-running or
    malformed run yields ``None`` so the template renders a dash rather
    than a misleading zero.

    Args:
        started_at: ISO-8601 start timestamp, or ``None``.
        finished_at: ISO-8601 finish timestamp, or ``None``.

    Returns:
        Whole milliseconds, or ``None`` when either end is missing or
        unparseable.
    """
    if not started_at or not finished_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        finish = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    return int((finish - start).total_seconds() * 1000)


def _best_candidate(runs: list[dict[str, Any]]) -> str | None:
    """Pick the run a reviewer should keep from a candidate set.

    The heuristic favours a *succeeded* attempt and, among those, the
    cheapest one (a known ``cost_est`` outranks an unknown), because the
    point of running several attempts is to keep the one that worked for
    the least spend.  When nothing has succeeded yet there is no
    recommendation.

    Args:
        runs: Serialized runs that share a ``notebook_path``.

    Returns:
        The id of the recommended run, or ``None`` when none succeeded.
    """
    succeeded = [r for r in runs if r["status"] == STATUS_SUCCEEDED]
    if not succeeded:
        return None

    def _cost_key(run: dict[str, Any]) -> tuple[bool, float]:
        cost = run["cost_est"]
        return (cost is None, float(cost) if cost is not None else 0.0)

    succeeded.sort(key=_cost_key)
    return str(succeeded[0]["id"])


def build_command_center(request: Request, *, limit: int = 200) -> dict[str, Any]:
    """Assemble the cockpit payload — live threads plus candidate sets.

    Loads one page of the workspace's runs (newest-first, already
    serialized) and splits it two ways: the non-terminal runs become the
    live-thread board, and any ``notebook_path`` with two or more runs
    becomes a candidate set with a recommended pick.  Candidate sets are
    ordered by size then recency so the busiest contest sits on top.

    Args:
        request: Incoming FastAPI request (carries the workspace scope).
        limit: Max runs to scan when forming the board and the groups.

    Returns:
        ``{"live", "candidate_groups", "counts"}`` where ``counts``
        summarizes the board for the header chips.
    """
    runs, total = load_runs(request, offset=0, limit=limit)
    live = [run for run in runs if run["status"] in IN_FLIGHT_STATUSES]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        # Path-less runs (ad-hoc / SQL-only) share no notebook, so they
        # are never rivals — skip them rather than collapsing every one
        # into a single bogus ``None`` candidate set.
        notebook_path = run["notebook_path"]
        if not notebook_path:
            continue
        grouped.setdefault(notebook_path, []).append(run)

    candidate_groups: list[dict[str, Any]] = []
    for notebook_path, group_runs in grouped.items():
        if len(group_runs) < 2:
            continue
        candidate_groups.append(
            {
                "notebook_path": notebook_path,
                "runs": group_runs,
                "size": len(group_runs),
                "best_pick": _best_candidate(group_runs),
            }
        )
    # Busiest contest first; within a tie the most recently touched set
    # wins (group_runs is newest-first, so [0] is the latest start).
    candidate_groups.sort(
        key=lambda group: (group["size"], group["runs"][0]["started_at"] or ""),
        reverse=True,
    )

    counts = {
        "total": total,
        "live": len(live),
        "needs_approval": sum(1 for run in live if run["status"] == STATUS_NEEDS_APPROVAL),
        "candidate_groups": len(candidate_groups),
    }
    return {"live": live, "candidate_groups": candidate_groups, "counts": counts}


def compare_runs(request: Request, run_ids: list[str]) -> dict[str, Any]:
    """Build a side-by-side comparison matrix for the selected runs.

    Each requested run contributes one column of normalized metrics
    (status, cost, op counts, duration, anomaly, MLflow link).  Unknown
    ids — and ids belonging to another workspace — are skipped rather
    than raising, so a stale or crafted selection degrades to a partial
    comparison instead of leaking a foreign run.  Duplicate ids collapse
    and the column count is capped at :data:`MAX_COMPARE_RUNS`.

    Args:
        request: Incoming FastAPI request.
        run_ids: Run ids to compare, in the order they should appear.

    Returns:
        ``{"runs": [...]}`` — one normalized dict per resolvable run.
    """
    # The cockpit is a per-workspace surface (its board uses the
    # workspace-scoped ``load_runs``); scope the by-id compare the same
    # way so a guessed id from another workspace cannot be pulled in.
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    seen: set[str] = set()
    columns: list[dict[str, Any]] = []
    for raw in run_ids:
        run_id = raw.strip()
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        if len(columns) >= MAX_COMPARE_RUNS:
            break
        try:
            row = load_run(request, run_id)
        except CatalogNotFoundError:
            continue
        if int(row.workspace_id) != workspace_id:
            continue
        from pointlessql.api.agent_runs_routes import serialize_agent_run

        base = serialize_agent_run(row)
        ops = load_operations_for_run(request, run_id)
        columns.append(
            {
                "id": base["id"],
                "status": base["status"],
                "principal": base["principal"],
                "notebook_path": base["notebook_path"],
                "cost_est": base["cost_est"],
                "op_count": len(ops),
                "errored_ops": sum(1 for op in ops if op["status"] == "error"),
                "tables_touched": base["tables_touched"],
                "started_at": base["started_at"],
                "finished_at": base["finished_at"],
                "duration_ms": _duration_ms(base["started_at"], base["finished_at"]),
                "anomaly_severity": base["anomaly_severity"],
                "mlflow_run_id": base["mlflow_run_id"],
            }
        )
    return {"runs": columns}
