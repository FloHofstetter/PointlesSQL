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

Sprint 22.5 adds **ADR-0004 Public-flip checklist** documenting
the trigger flip in `.github/workflows/docs.yml`, the EUIPO
trademark check, NOTICE / CLA hygiene, and custom domain
decision.

## Conventions

- One file per decision, named `NNNN-short-title.md`
- Status values: `Proposed` → `Accepted` → `Superseded by NNNN`
- Date the decision in the front-matter
- Open a new ADR for any change to a previous one — never
  rewrite history
