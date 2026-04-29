# Delta-Branching walkthrough

Exercises the Phase 16.5 zero-copy branching primitives end-to-end:
create a branch, write to it, prove the parent stays untouched,
preview a promotion, deliberately break it with a competing parent
write, discard the conflicting branch, then re-branch and promote
cleanly.  All on local FS — symlink strategy.

The goal is to prove the **isolation guarantee** ("writes against
the branch never touch the parent") and the **conflict-detection
guarantee** ("a parent that moved during the branch's lifetime
fails the promote, never silently corrupts main").

This walkthrough is **driven from a notebook + a browser** (Phase
16.5.5 Control-Room UI for the visual flips, notebook for the
``pql.*`` calls).  It can also be replayed by Claude Code via
`mcp__playwright__browser_*` against headful Firefox.

## Preconditions

- PointlesSQL is running locally on `http://127.0.0.1:8000`.
  Default config from [`docs/install.md`](../install.md) is fine.
- soyuz-catalog is running on `http://127.0.0.1:8080` and reachable
  from PointlesSQL.
- A test catalog exists with a writeable schema (the seeded
  `playground` catalog from
  [`scripts/seed-e2e.py`](../../scripts/seed-e2e.py) is fine, or
  any catalog you create via the home dashboard).
- `branch.cloud_strategy` is at its default `"error"` (we exercise
  local FS only).
- `branch.auto_cleanup_enabled` is at its default `False` (we
  test cleanup deliberately at the end, opt-in).

## Walkthrough

### 1. Seed a parent schema with one Delta table

- Action: open a new notebook (any path under `/notebooks`).
  Run a cell:
  ```python
  import pandas as pd
  from pointlessql.pql.pql import PQL

  pql = PQL()
  df = pd.DataFrame({"id": [1, 2, 3, 4, 5], "name": ["a", "b", "c", "d", "e"]})
  pql.write_table(df, "playground.bronze.events", mode="overwrite")
  print("wrote", len(pql.table("playground.bronze.events")), "rows")
  ```
- Assert: prints `wrote 5 rows`.  Browser → `/catalogs/playground`
  shows the `bronze` schema with `events` table; clicking through
  shows 5 rows.

### 2. Create a branch from the parent

- Action: in the same notebook, run:
  ```python
  branch_fqn = pql.branch("playground.bronze", "bronze_branch_42")
  print(branch_fqn)
  ```
- Assert: prints `playground.bronze_branch_42`.  Browser →
  `/branches` shows one row:
  - **Branch**: `playground.bronze_branch_42`
  - **Parent**: `playground.bronze`
  - **Status**: `active` (green badge)
  - **Strategy**: `symlink`
  - **Created**: today's timestamp

### 3. Verify the symlink-strategy storage layout

- Action: from a shell:
  ```bash
  ls -la data/playground/bronze/_branches/bronze_branch_42/events/
  ```
- Assert: the parquet file is a symlink (`->` arrow in the
  listing), pointing at the parent's parquet under
  `data/playground/bronze/events/`.  Disk usage of the symlink
  itself is in the tens of bytes, not the parquet size.

### 4. Append to the branch — the parent must stay untouched

- Action: in the notebook:
  ```python
  df_new = pd.DataFrame({"id": [10, 11], "name": ["x", "y"]})
  pql.write_table(df_new, "playground.bronze_branch_42.events", mode="append")
  print("branch:", len(pql.table("playground.bronze_branch_42.events")))
  print("parent:", len(pql.table("playground.bronze.events")))
  ```
- Assert: prints `branch: 7` and `parent: 5`.  This is the core
  isolation guarantee.

### 5. Preview the promote (no conflicts expected)

- Action: browser → `/branches/playground.bronze_branch_42` →
  Danger zone → click **Preview promote**.
- Assert: green alert _"No conflicts detected — promote is safe."_
  appears below the buttons.

### 6. Deliberately break the promote

- Action: in the notebook, append to the **parent**:
  ```python
  df_intruder = pd.DataFrame({"id": [99], "name": ["intruder"]})
  pql.write_table(df_intruder, "playground.bronze.events", mode="append")
  ```
- Action: browser → reload `/branches/playground.bronze_branch_42`
  → click **Preview promote** again.
- Assert: yellow alert _"Promotion conflicts detected"_ with a
  table row:
  - **Table**: `events`
  - **Expected**: `0`
  - **Actual**: `1`
  - **Reason**: `version_drift`

### 7. Discard the conflicting branch

- Action: still on `/branches/playground.bronze_branch_42` →
  Danger zone → click **Discard** → confirm in the browser dialog.
- Assert:
  - Toast _"Branch discarded"_.
  - Page redirects to `/branches`; the row is gone (or shows
    `discarded`).
  - Shell: `ls data/playground/bronze/_branches/` shows no
    `bronze_branch_42` directory.
  - The parent's `events` parquets are still on disk and still
    readable (`pql.table("playground.bronze.events")` returns
    6 rows — the original 5 plus the intruder row).

### 8. Fresh branch, write, clean promote

- Action: in the notebook:
  ```python
  branch_fqn = pql.branch("playground.bronze", "bronze_branch_43")
  df_one = pd.DataFrame({"id": [777], "name": ["promote_me"]})
  pql.write_table(df_one, "playground.bronze_branch_43.events", mode="append")
  ```
- Action: browser → `/branches/playground.bronze_branch_43` →
  Danger zone → **Promote** → confirm.
- Assert:
  - Toast _"Promoted to playground.bronze"_.
  - Browser redirects to `/branches`.  The list now shows
    `playground.bronze_branch_43` with status **promoted** AND a
    new row `playground.bronze_pre_promote_<ts>` with the
    `backup` badge.
  - `pql.table("playground.bronze.events")` returns 7 rows
    (the original 6 plus the new `777` row).

### 9. Audit-log inspection

- Action: browser → `/branches/playground.bronze_branch_43` →
  scroll to the **Audit log** card.
- Assert: at least three rows in reverse-chronological order:
  - `promote` (most recent)
  - `create`
  Audit-log payloads include `strategy`, `parent_versions`, and
  the backup FQN on the promote row.

### 10. CloudEvents in `governance_events`

- Action: from a shell, query the metadata DB:
  ```bash
  uv run python -c "
  from pointlessql.db import init_db, get_session_factory
  from pointlessql.settings import Settings
  from pointlessql.models import GovernanceEvent
  init_db(Settings().db.url)
  with get_session_factory()() as s:
      for r in s.query(GovernanceEvent).order_by(GovernanceEvent.id.desc()).limit(5):
          print(r.event_type, r.outcome)
  "
  ```
- Assert: the latest entries include
  `pointlessql.branch.created.v1`,
  `pointlessql.branch.discarded.v1`, and
  `pointlessql.branch.promoted.v1`.

### 11. Auto-cleanup smoke (optional — opt-in path)

- Action: stop the server.  Set
  `POINTLESSQL_BRANCH_AUTO_CLEANUP_ENABLED=true`,
  `POINTLESSQL_BRANCH_AUTO_CLEANUP_RETENTION_DAYS=0` (everything
  past 0 days is eligible).  Restart the server.
- Action: create a fresh branch
  (`pql.branch("playground.bronze", "bronze_cleanup_test")`),
  then wait for the next cleanup loop tick (24h by default — for
  the smoke test, lower
  `POINTLESSQL_AUDIT_CLEANUP_INTERVAL_SECONDS=60` and wait 60–120s).
- Assert: server log shows `branch_cleanup: {'deleted': 1,
  'skipped': N, 'errored': 0, 'enabled': True}`.  Browser →
  `/branches` no longer lists `bronze_cleanup_test`.

## BUGs surfaced

_None at the time of Sprint 16.5.7 close.  Future regressions land
under `BUG-16.5-NN` markers below._

<!-- BUG-16.5-NN — fix location: <path/to/file.py:LN> -->
