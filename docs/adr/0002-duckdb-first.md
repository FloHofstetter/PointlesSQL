# ADR 0002 — DuckDB-first for compute

Status: Accepted (Phase 13.5, Sprint 13.5.1)
Supersedes: nothing (the Sprint-2 pandas read path stays — this
ADR governs *new* compute primitives, not the existing
DataFrame-engine seam in `pointlessql/pql/engine.py`)

## Context

Phase 13.5 ("Medallion core + DuckDB-first opinion") introduces
two new compute-touching primitives — `pql.merge` (Sprint 13.5.2)
and `pql.autoload` (Sprint 13.5.3) — and an EXPLAIN gate
(Sprint 13.1) that needs a query planner.  The Phase-12 SQL
editor already runs on DuckDB; the column-stats refresh
(Sprint 54) runs on DuckDB; the alert evaluator (Sprint 55) runs
on DuckDB.  We have an implicit DuckDB-first stance for compute
already.  This ADR makes it explicit so the new primitives don't
re-open the question and so future contributors stop trying to
abstract the compute engine prematurely.

The orthogonal question — which DataFrame engine `pql.read_table`
returns (pandas / polars / daft / spark) — is *not* what this ADR
governs.  That seam stays via
:class:`pointlessql.pql.engine.Engine` and the
``POINTLESSQL_DELTA_ENGINE`` env var.

## Decision 1 — DuckDB owns compute and read

The new merge / autoload primitives, the EXPLAIN gate, the
column-stats refresh, the alert evaluator, and the SQL editor
all run on DuckDB.  Concretely: queries are issued as DuckDB
SQL, plans are extracted via DuckDB's `EXPLAIN (FORMAT JSON)`,
file scans use DuckDB's `read_parquet` / `read_csv_auto` /
`read_json_auto`, and the column-stats refresh runs DuckDB
aggregates over Delta scans.

### Alternatives considered

**Polars-first.**  Lazy frame model, Rust core, very fast
single-machine analytics.

- Pro: zero-copy interop with the existing pandas read path via
  Arrow.
- Pro: Rust core, fewer heap-fragmentation surprises than
  DuckDB's memory model in long-running processes.
- Contra: no SQL planner with EXPLAIN-extractable plans.  The
  EXPLAIN gate's whole motivation is that an agent can read the
  plan, see "this will scan 50M rows", and self-rewrite.  Polars
  surfaces a logical-plan repr but it isn't a stable contract
  for cost estimation.
- Contra: silver/gold workloads are SQL-shaped (joins,
  aggregations, window functions).  Forcing them through Polars'
  expression DSL drops the SQL-fluency the agent already has from
  its training data.

**Daft-first.**  Distributed-by-default, Ray-friendly.

- Pro: scales out without rewriting the primitives.
- Contra: distributed-by-default is a tax on the single-node
  workloads that 100% of PointlesSQL's current users run.  The
  whole point of "no second-engine user exists today"
  (project_catalog_strategy.md) applies here too.
- Contra: less mature SQL surface than DuckDB; we'd inherit any
  bugs in Daft's SQL → expression compiler.

**Spark-first.**  The reference Databricks engine.

- Pro: feature-complete; everyone in the data world knows it.
- Contra: JVM startup cost dominates on the single-table
  EXPLAIN-gate workload (sub-100ms target vs. several-second
  Spark cold-start).
- Contra: brings the JVM back into a project that explicitly
  retired the JVM UC server in Sprint 38.  Adding a JVM compute
  engine right after retiring the JVM catalog server is the
  wrong direction.
- Contra: the ROADMAP entry for Phase 13.5 explicitly defers
  cross-engine abstraction until a concrete second-engine user
  materialises.  Picking Spark now is exactly that abstraction.

### Why DuckDB wins

- Stable EXPLAIN format — `EXPLAIN (FORMAT JSON)` returns a
  parseable plan; the cost estimator (Sprint 13.1) can extract
  `row_count × join_depth` heuristics from it.
- Native Delta-table scan support and zero-copy Arrow handoff to
  pandas / polars / Arrow consumers — no extra serialisation hop.
- In-process, sub-100ms cold start — the EXPLAIN gate runs
  per-request and a Spark/JVM cold start would dominate latency.
- SQL surface mirrors PostgreSQL closely enough that any agent
  already has training data for it.
- File-scan readers (`read_parquet`, `read_csv_auto`,
  `read_json_auto`) cover the autoload primitive without us
  writing a custom type-inference pass.

## Decision 2 — `deltalake` Python owns writes

Writes — schema evolution, protocol upgrades, `MERGE` invocation,
`VACUUM`, write-time validation — go through the `deltalake`
Python package.  DuckDB's Delta write support is improving but
trails `deltalake` on protocol features (writer protocol v7,
generated columns, deletion vectors).

Concretely: `pql.merge` calls `deltalake.DeltaTable.merge()` for
the actual MERGE op; `pql.autoload` builds the row batch in
DuckDB and writes via `deltalake.write_deltalake(mode="append")`;
schema migrations happen via `deltalake.DeltaTable.alter`.  DuckDB
is read-only for the write paths.

### Why a hard split

- Single owner per concern → no race between two engines deciding
  what the on-disk Delta protocol version should be.
- The Delta protocol is the only thing portable across engines.
  Anchoring the writer to the language-of-record library (`deltalake`)
  keeps that portability honest.

## Decision 3 — Storage / catalog / runtime stay pluggable

The DuckDB opinion binds the **compute** layer only.  Storage
stays Delta-portable (no DuckDB-native file format), the catalog
stays UC-portable (soyuz-catalog speaks the spec), and the
runtime stays pluggable (Hermes / OpenShell / Claude Code all
register agent runs the same way).  Where abstraction has a
real second-implementation user (catalog provider via soyuz,
DataFrame engine via :class:`Engine`) we keep the interface;
where it doesn't (compute), we don't pre-build it.

## Consequences

- The new primitives `pql.merge` (Sprint 13.5.2), `pql.autoload`
  (Sprint 13.5.3), and the EXPLAIN endpoint (Sprint 13.1) are
  DuckDB-only by contract.  No `engine=` parameter, no
  abstraction-leak placeholder.  When and if a polars/spark/daft
  user shows up, we add the abstraction with their concrete
  workload as the test case.
- The existing :class:`pointlessql.pql.engine.Engine` seam stays.
  It governs *read-result DataFrame type* (pandas today,
  polars/daft tomorrow), not query execution.  Don't conflate the
  two — the read-result engine and the compute engine are
  orthogonal concerns.
- The pyproject.toml gains no new top-level deps in this
  sprint; DuckDB is already pinned for the SQL editor and
  column-stats work.
- A repo-level `pointlessql.yaml` (parser shipped in Sprint 13.5.1)
  can override layer names / audit columns / UC tag schema, but
  it cannot override the compute-engine choice — that lives in
  this ADR.

## Out of scope for Sprint 13.5.1

- Polars / Daft / Spark backends for the new primitives — wait
  for a concrete second-engine user, per
  `project_catalog_strategy.md`.
- Structured-streaming ingest — Hermes cron pulling files is the
  Phase 13.5 MVP; real streaming (Kafka, CDC-from-Postgres,
  Kinesis) is a separate future phase.
- Cross-engine compute abstraction layer — same reasoning;
  premature without a second user.
- Migrating the existing pandas-engine read path to DuckDB — the
  read-result engine is a separate seam; this ADR doesn't touch it.
