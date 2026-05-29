# Architecture Decision Records

Decisions worth re-reading in six months land here as ADRs.
The numbering is sequential.  Format is loosely
[MADR](https://adr.github.io/madr/) — Status, Context,
Decision, Consequences.

| # | Status | Decision |
|---|---|---|
| [0001](0001-notebook-editor.md) | Accepted | Notebook editor: native Monaco + `pql_cell_id` marker grammar |
| [0002](0002-duckdb-first.md) | Accepted | DuckDB-first: DuckDB owns compute, deltalake owns writes |
| [0003](0003-delta-branching-spike.md) | Accepted | Delta-branching: hybrid symlink-local / deep-copy-cloud |
| [0004](0004-public-flip-checklist.md) | Accepted | Docs-site public-flip three-commit procedure with EUIPO / NOTICE / CLA / domain pre-flight |
| [0009](0009-doc-publication-decisions.md) | Accepted | Doc-publication: 8 cross-cutting decisions (CHANGELOG granularity, dev-log location, version scheme, doc visibility, asset storage, auto-gen balance, density norm, doc-vs-code scope) |
| [0010](0010-cedar-policy-as-code.md) | Accepted | Cedar policy-as-code: cedarpy hooks into pql/_hooks, fail-closed on parse/runtime error, per-version cache, decision ledger separate from audit log |
| [0011](0011-data-product-as-code.md) | Accepted | Data-Product-as-Code: strict pydantic DataProductSpec + state-style plan→apply reconciler that reuses existing CRUDs; round-trip apply→export→plan is a no-op |

## Conventions

- One file per decision, named `NNNN-short-title.md`
- Status values: `Proposed` → `Accepted` → `Superseded by NNNN`
- Date the decision in the front-matter
- Open a new ADR for any change to a previous one — never
  rewrite history
