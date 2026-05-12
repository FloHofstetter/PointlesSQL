r"""Seed a synthetic broken agent run for the Incident-Responder walkthrough.

Sprint 19.4.  Builds the canonical "this run went sideways" shape the
``docs/e2e-walkthroughs/incident-responder.md`` walkthrough exercises:

- One :class:`AgentRun` row, status ``failed``, ``finished_at`` set.
- Three :class:`AgentRunOperation` rows under it: an ``autoload`` that
  succeeded, a ``merge`` that errored mid-way, and a ``write_table``
  that completed but accumulated an outsized batch of rejects.
- ~50 :class:`LineageRowReject` rows pointing at the bad merge.
- Two :class:`UnattributedWrite` rows landing in the same time window
  on the failed run's target table — the walkthrough drills here to
  prove the responder agent can correlate "this run failed" with
  "and somebody else also wrote to the same table while it was
  failing".

Idempotent in shape but NOT in PK: re-running with the same
``--run-id`` errors on duplicate insert.  Re-runs against a fresh
sqlite (``rm pointlessql.db && uv run pointlessql admin
issue-auditor-key --name=…``) are the expected pattern.

Run with::

    POINTLESSQL_DB__URL=sqlite:///./pointlessql.db \
        uv run python scripts/seed-broken-run.py [--run-id <uuid>]

The script prints the run_id (random UUID by default) so the
walkthrough can copy it into a Hermes chat prompt.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import uuid

from pointlessql.models.agent_run_audit import AgentRunOperation
from pointlessql.models.agent_runs import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    AgentRun,
)
from pointlessql.models.external_writes import UnattributedWrite
from pointlessql.settings import Settings

from pointlessql.db import get_session_factory, init_db
from pointlessql.models.lineage import LineageRowReject


def _utc(offset_seconds: int = 0) -> datetime.datetime:
    """Return ``now - offset_seconds`` as a UTC-aware datetime.

    Args:
        offset_seconds: Subtracted from "now"; positive values land
            the timestamp in the past.

    Returns:
        A timezone-aware :class:`datetime.datetime`.
    """
    return datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=offset_seconds)


def main(argv: list[str] | None = None) -> int:
    """Insert the synthetic broken-run rows and print the run_id.

    Args:
        argv: Optional override for ``sys.argv[1:]`` (testing).

    Returns:
        ``0`` on success.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default=uuid.uuid4().hex,
        help="UUID for the AgentRun row (default: fresh uuid4 hex).",
    )
    parser.add_argument(
        "--principal",
        default="incident-responder-fixture",
        help="AgentRun.principal value (default: incident-responder-fixture).",
    )
    parser.add_argument(
        "--reject-count",
        type=int,
        default=50,
        help="Number of LineageRowReject rows to seed for the broken merge.",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    init_db(settings.db.url)
    factory = get_session_factory()

    target_table = "demo.incidents.broken_orders"
    source_table = "demo.incidents.raw_orders"
    started = _utc(offset_seconds=600)
    finished = _utc(offset_seconds=10)

    with factory() as session:
        run = AgentRun(
            id=args.run_id,
            agent_id="audit-incident-fixture",
            status=STATUS_FAILED,
            principal=args.principal,
            tables_touched=json.dumps([target_table]),
            started_at=started,
            finished_at=finished,
            notebook_path="scripts/seed-broken-run.py",
            source_snapshot_sha="sha256:fixture-sha-not-canonical",
            runtime_versions=json.dumps({"python": "3.14.0", "fixture": "19.4"}),
        )
        session.add(run)
        session.flush()

        op1 = AgentRunOperation(
            agent_run_id=args.run_id,
            ordinal=1,
            op_name="autoload",
            params_json=json.dumps({"source": source_table, "checkpoint": "raw"}),
            target_table=source_table,
            input_sha="sha256:fixture-autoload-sha",
            rows_affected=1000,
            delta_version_before=None,
            delta_version_after=0,
            started_at=started,
            finished_at=_utc(offset_seconds=550),
            error_message=None,
        )
        op2 = AgentRunOperation(
            agent_run_id=args.run_id,
            ordinal=2,
            op_name="merge",
            params_json=json.dumps(
                {"source": source_table, "target": target_table, "key": ["order_id"]}
            ),
            target_table=target_table,
            input_sha="sha256:fixture-merge-sha",
            rows_affected=None,
            delta_version_before=0,
            delta_version_after=None,
            started_at=_utc(offset_seconds=500),
            finished_at=_utc(offset_seconds=450),
            error_message=(
                "DeltaError: Schema mismatch on column 'amount': "
                "source DOUBLE, target DECIMAL(10,2)"
            ),
        )
        op3 = AgentRunOperation(
            agent_run_id=args.run_id,
            ordinal=3,
            op_name="write_table",
            params_json=json.dumps({"target": target_table, "mode": "overwrite"}),
            target_table=target_table,
            input_sha="sha256:fixture-write-sha",
            rows_affected=950,
            delta_version_before=0,
            delta_version_after=1,
            started_at=_utc(offset_seconds=400),
            finished_at=_utc(offset_seconds=200),
            error_message=None,
        )
        session.add_all([op1, op2, op3])
        session.flush()

        op2_id = op2.id
        op3_id = op3.id

        # Synthetic rejects on op3 — schema_mismatch + duplicate_in_source mix.
        for i in range(args.reject_count):
            reason = "schema_mismatch" if i % 3 != 0 else "duplicate_in_source"
            session.add(
                LineageRowReject(
                    run_id=args.run_id,
                    op_id=op3_id,
                    source_table=source_table,
                    source_row_id=f"row-{i:04d}",
                    reason=reason,
                    detail=f"order_id={1000 + i}; amount column failed cast"
                    if reason == "schema_mismatch"
                    else f"duplicate of order_id={1000 + (i % 5)}",
                    created_at=_utc(offset_seconds=300 - i),
                )
            )

        # External writes that landed on the same table during the
        # broken run's window — Sprint-14.3 unattributed-writes table.
        commit_info_v2 = json.dumps(
            {
                "operation": "WRITE",
                "userName": "hand-fix:cron-recovery",
                "operationMetrics": {"numFiles": "3", "numOutputRows": "12"},
            }
        )
        commit_info_v3 = json.dumps(
            {
                "operation": "WRITE",
                "userName": "hand-fix:cron-recovery",
                "operationMetrics": {"numFiles": "1", "numOutputRows": "4"},
            }
        )
        session.add(
            UnattributedWrite(
                table_fqn=target_table,
                delta_version=2,
                commit_timestamp=_utc(offset_seconds=160),
                commit_info=commit_info_v2,
                detected_at=_utc(offset_seconds=150),
            )
        )
        session.add(
            UnattributedWrite(
                table_fqn=target_table,
                delta_version=3,
                commit_timestamp=_utc(offset_seconds=110),
                commit_info=commit_info_v3,
                detected_at=_utc(offset_seconds=100),
            )
        )

        # Add one tiny "good" run so principal-summary aggregations
        # have a non-trivial denominator in the walkthrough.
        good_run_id = uuid.uuid4().hex
        good_run = AgentRun(
            id=good_run_id,
            agent_id="audit-incident-fixture",
            status=STATUS_SUCCEEDED,
            principal=args.principal,
            tables_touched=json.dumps([target_table]),
            started_at=_utc(offset_seconds=86400),
            finished_at=_utc(offset_seconds=86200),
            notebook_path="scripts/seed-broken-run.py",
            source_snapshot_sha="sha256:fixture-sha-not-canonical",
            runtime_versions=json.dumps({"python": "3.14.0", "fixture": "19.4"}),
        )
        session.add(good_run)

        session.commit()

    print(f"broken run_id   = {args.run_id}")
    print(f"  principal     = {args.principal}")
    print(f"  target table  = {target_table}")
    print(f"  failing op_id = {op2_id}  (merge, schema_mismatch error)")
    print(f"  rejecting op  = {op3_id}  ({args.reject_count} LineageRowReject rows)")
    print("  external_writes seeded: 2 (delta_version 2 + 3)")
    print("Use this run_id in the Incident-Responder chat prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
