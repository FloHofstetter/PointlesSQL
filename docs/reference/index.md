# Reference

The complete API surface of PointlesSQL.

Sprint 22.3 fills this section in:

- **Python API** — auto-generated from the `PQL` class and
  service layer via `mkdocstrings`
- **REST API** — the 212 FastAPI routes, grouped by tag, with
  a hand-polished prelude for the 30 most-used routes (auth,
  runs, models, lineage, write, merge, branching, supervisor,
  auditor)
- **CLI** — `pointlessql` command + management subcommands
- **Configuration** — every env var grouped by
  `pointlessql/settings.py` sub-model
- **CloudEvents** — every event type emitted by PointlesSQL
- **Permissions** — the trust-tier matrix
