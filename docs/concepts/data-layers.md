# Data layers — Medallion conventions

PointlesSQL ships an opinionated default for organising lakehouse
tables: the **Medallion** layout (bronze → silver → gold). These
conventions matter because PointlesSQL is the *persistent
analytical memory for agents* — without a shared idiom every
agent re-invents bronze/silver/gold semantics and the
"persistent memory" pitch collapses. The defaults are
configurable; they are not hard-coded.

## The three layers

### Bronze — raw fidelity, append-only

Bronze tables hold the source data as it was received, with the
schema inferred from the file (CSV → DuckDB type-infer, Parquet
→ logical type carried through, JSON → DuckDB schema-on-read).

Every bronze row carries three **audit columns** so you can trace
any value back to the file it came from months later:

| Column | Meaning |
| ----------------- | ---------------------------------------------------------- |
| `_ingested_at` | UTC timestamp of the autoload run that wrote this row. |
| `_source_file` | Volume-relative path of the source file (e.g. `2026/04/orders.csv`). |
| `_source_system` | Free-form name of the upstream system (e.g. `salesforce`). |

The autoload primitive (`pql.autoload`, ) injects
these columns automatically; manual writes are checked passively
by the conformance check on `/runs/{id}`.

### Silver — deduplicated, typed, conformed keys

Silver tables are the cleanest representation of the source
domain. Duplicate rows are removed (typically via `pql.merge`
upsert), business keys are conformed across upstreams, and
narrow types replace the inferred-from-CSV strings.

Silver does **not** require audit columns. Provenance lives one
hop upstream in bronze; if you want column-level lineage at
silver, add it explicitly.

### Gold — business facts, aggregated, star-schema-ready

Gold tables are what the dashboards and ML feature stores read.
They are denormalised, pre-aggregated, and indexed by the grain
that matters to the consumer (`day × product`, `customer ×
campaign`, etc.).

Gold also has no audit-column requirement — by the time you are
at gold the lineage is encoded in the SQL that built the table.

## How the layers are advertised

Every table that participates in the Medallion convention carries
a UC tag with key `layer` and value `bronze`, `silver`, or `gold`.
This is the contract the conformance check reads, the agent
system prompt surfaces, and downstream consumers (ML feature
stores, BI tools) can filter on without reading naming
conventions out of schema names.

The tag key is overridable via `layer_tag_key` in
`pointlessql.yaml`.

## Overriding the defaults

The Medallion defaults live in
`pointlessql/conventions/_defaults.py`. To override them, copy
[`pointlessql.yaml.example`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql.yaml.example) to
`pointlessql.yaml` and point `POINTLESSQL_CONVENTIONS_PATH` at
it. Overrides shallow-merge over the defaults at the top level
— if you redefine `layers`, you must include every layer you
want, because the entire list is replaced (so a partial override
doesn't accidentally leave a stale default in the middle).

## Why DuckDB underneath

The new compute primitives (`pql.merge`, `pql.autoload`, the
SQL-editor EXPLAIN gate, the column-stats refresh) all run on
DuckDB. `deltalake` Python owns writes (schema evolution,
protocol upgrades, `VACUUM`); DuckDB owns the scan + transform
side. Storage stays Delta-portable, the catalog stays
UC-portable, the runtime stays pluggable — the opinion only
binds the compute layer. See
[`docs/adr/0002-duckdb-first.md`](../decisions/0002-duckdb-first.md) for
the full rationale.
