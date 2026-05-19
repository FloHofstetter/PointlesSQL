# Agent memory — Delta-first persistent memory for AI agents

PointlesSQL frames its existing audit + branching infrastructure
as **the agent's persistent memory**: a Delta-backed append-only
log of every operation the agent ran, plus a branch-tree that
isolates per-run state for replay.  This page is the conceptual
counter-pitch to Databricks' Lakebase positioning ("persistent
memory for AI agents on Postgres OLTP") — both targets are
valid; the cost surface differs by an order of magnitude on the
write-pattern that dominates agent activity.

## What "agent memory" means here

Three primitives, one log:

| Primitive | What it stores | Backed by |
| --- | --- | --- |
| `pql.memory.record(op)` | One operation row per primitive call | `agent_run_operations` table |
| `pql.memory.recall(filter=…)` | Filtered read of the operation log | SQL SELECT on the same table |
| `pql.memory.branch(from_run_id)` | Delta branch off the run's schema state | `branch_audit_log` + the schema-clone primitive |
| `pql.memory.replay(branch, source_run)` | Re-record the source run's ops onto the branch | New `agent_runs` row + dispatcher |
| `pql.memory.fork(from_run_id)` | Same as `branch`, labelled "fork" in payload | same |

The full surface lives at
[`pointlessql/pql/memory.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/pql/memory.py).
The `/memory/<agent-id>` page in the UI is the visual
counterpart — same data, different lens (browse instead of
program).

## Why Delta and not Postgres?

Lakebase's pitch leans on Postgres for one specific affordance:
fast point reads + transactional updates of per-agent state
("the agent stores last_seen, current_task, cached_user_prefs,
update them once a turn").  That workload is real but narrow.
The volume-dominant write pattern in agent-supervised
PointlesSQL is the opposite:

* Append-only operation logs (`agent_run_operations`) —
  every primitive call writes one row, never updates.
* Append-only audit events (`agent_run_events`,
  `governance_events`) — lifecycle transitions, approvals,
  CloudEvents.
* Append-only branch ledger (`branch_audit_log`) — create
  / promote / discard, each a new row.

For append-only data, Delta beats Postgres on every axis that
matters at agent scale:

| Property | Delta | Postgres (Lakebase) |
| --- | --- | --- |
| Append-only write throughput | 100k+ rows/s on a single writer | ~10k rows/s before WAL pressure |
| Time-travel cost | Free (Delta protocol stores versions) | Logical replication + history table required |
| Schema-less params | `params_json` Text column accepts anything | Needs JSONB columns + GIN indices |
| Branch-of-state cost | One symlink dir (local) / deep-copy (cloud) | Logical-replication slot + clone |
| OSS posture | Apache 2.0 Delta protocol + deltalake Rust | Lakebase = managed Postgres (paid) |

The trade-off: Delta is bad at small, hot point-reads — a
single-row lookup goes through DuckDB or the Delta scan API,
neither of which competes with a Postgres B-tree.  When the
agent actually needs that pattern (per-user session state, hot
config keys), nothing stops you from also running Postgres
alongside.  The Phase-90 claim is just that the *memory log*
itself — the dominant volume — belongs on Delta.

## How replay works

Replay re-invokes a source run's operations against a Delta
branch.  Ops are bucketed into three outcomes:

* **Replayable** — `sql`, `sql_explain`, `autoload`.  The
  params carry everything needed to re-record the action; the
  dispatcher rewrites schema references in the SQL and stamps
  `_replay_of: <orig_op_id>` into the new params.
* **Data unavailable** — `merge`, `write_table`, `aggregate`.
  Original primitive consumed an in-memory DataFrame that's
  long gone; replay records the skip with reason
  `"data_unavailable"` so the audit trail makes the gap
  explicit.
* **Unsafe** — `branch_*`, `dbt_*`, `train_model`, `update`,
  `delete`, `rollback`, `drop_table`, schema DDL.  Blind
  replay would either fail loudly (re-creating an existing
  branch) or change external state non-deterministically
  (re-training a model with stale data).  `policy=STRICT`
  raises; `policy=SKIP_UNSAFE` (default) records the skip.

**Phase 90 scope note**: replayable ops are *recorded* against
the replay run, not *executed*.  The replay run's
operation-tape shows what would have run; real re-execution
(rebuilding the DuckDB approved-tables map for the branch and
running the rewritten SQL against branch storage) lands with
the Phase 91 NL→SQL chat panel, which needs the same plumbing.

## Conformance with the wider stack

* **Agent supervision** (see [agent-supervision.md](agent-supervision.md))
  — the supervision UI on `/runs/<id>` shows the operation
  log for one run; the memory page on `/memory/<agent-id>`
  shows the cross-run aggregation.  Same underlying rows,
  different scope.
* **Audit trail** (see [audit-trail.md](audit-trail.md)) — every
  `pql.memory.record` call routes through `record_operation`,
  which fires the same post-commit lineage / column-edges /
  value-changes hooks every other primitive does.  Memory and
  audit are the same log read at different scopes.
* **Git-backed workspaces** (see [git-backed-workspaces.md](git-backed-workspaces.md))
  — agent-authored `.py` notebooks under `workspaces/<repo>/`
  are how the *code* the agent ran gets versioned; the memory
  log is how the *behaviour* of those runs gets versioned.
  Together they make a Git-style "trace + diff" for AI agents.

## When this is the wrong fit

`pql.memory` is intentionally *not* a general agent state
store.  It does not address:

* **Per-turn working memory** (LLM context window
  management).  That belongs in the framework layer
  (LangGraph, Hermes, the like).
* **Hot per-user session state** (last-seen, current_task,
  cached prefs).  Use Postgres / Redis alongside.
* **Cross-agent shared memory** (one agent reading another's
  memory in real-time).  The current model is per-agent; a
  cross-agent reasoner would mean a polymorphic
  `agent_id IN (…)` recall, which the existing SELECT helper
  already supports, but no UI flow drives it.

For those, lean on the framework above PointlesSQL.  The Phase
90 surface is for the *post-hoc supervision* layer: humans
auditing what their agents did, replaying suspicious runs
against a sandbox branch, posting reviewer comments inline.
