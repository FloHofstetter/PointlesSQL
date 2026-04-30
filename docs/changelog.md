# What's new

The full per-sprint changelog lives in
[`CHANGELOG.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/CHANGELOG.md)
in the repo root (~7800 LOC; Phase 0 through current).

This page is the **digest** — the most recent sprints in
calendar order.  Sprint 22.5 will add a `gen_whats_new.py`
script that auto-snips the `[Unreleased]` block + last 3
sprints from `CHANGELOG.md` so this page stays fresh on every
build.  Until then, the snapshot below is hand-curated.

## Phase 22 — Documentation site (in progress)

- **22.0** — mkdocs-material tooling foundation.  Site builds
  locally; deploy workflow staged but inert.
- **22.1** — Landing page rewrite + 5-min quickstart + concepts
  overview.  README ASCII → Mermaid.
- **22.2** — Architecture, audit-trail, lineage, and agent-
  supervision deep-dive concept pages.
- **22.3** — Reference manual: Python API (mkdocstrings) + REST
  top-30 + CLI + configuration + CloudEvents + permissions.
- **22.4** — Guides reorganisation: agent bring-up + operator
  cookbook + troubleshooting + FAQ; 38 walkthroughs themed into
  five sub-sections.
- **22.5** — Cross-link sweep + integrations pages + ADR-0004
  public-flip checklist + this digest page.  Site is launch-
  ready (build green under `--strict`).

## Phase 21 — ML Registry + Auditable Training (closed 2026-04-30)

Nine sub-sprints that turned the data-engineering audit into a
**model-training audit**.  ~133 new pytest cases, 10 commits
(8 server + 2 cross-repo).  Headline features:

- **MLflow Tracking subprocess** + `/mlflow/` reverse-proxy
  (21.0)
- **soyuz `MODEL` Securable** with finalize + status state-
  machine (21.1)
- **`agent_runs.mlflow_run_id`** cross-link via `_pql_link`
  JSON-marker bridge (21.2)
- **Forced autolog** wrapping `mlflow.autolog()` with
  `training_params_json` capture (21.3)
- **Hardware / library fingerprint** in
  `agent_run_operations.env_snapshot` (21.4)
- **Models browse**: catalog tree + 5-tab detail + cytoscape
  mini-DAG (21.5)
- **Champion / challenger promotion** with `_pql_promotion`
  marker grammar + supervisor-gated POST + CloudEvent (21.6)
- **Inference-lineage**: `source_model_uri` column ties
  predictions back to the model that produced them; bidirectional
  model DAG (21.7)
- **Hermes plugin extension**: 8 new tools + 2 extended
  (write_table + merge accept `source_model_uri`); tool count
  34 → 42 (21.8)

## Phase 20 — Audit ergonomics

Five sub-sprints landed 2026-04-29:

- Audit-stream forwarder with three sinks (webhook + S3 + AWS
  CloudTrail with httpx + SigV4)
- PII `hash_only` default + `system_keys` table
- Lineage retention TTLs (`row_edges`/`row_rejects` 365d,
  `value_changes` 730d, `column_map` never)
- Time-travel UI (table picker + admin row-at-version)
- soyuz cross-repo facet ingest (columnLineage + custom
  valueChange)

## Phase 19 — Agent supervision

Six sub-sprints that built the four canonical bot personas:

- Daily Audit-Reviewer (cron, wake-gate skips LLM on `ok` days)
- Compliance-Bot (wake-on-message, read-only)
- Incident-Responder (wake-on-message, multi-turn drill-down)
- Promotion-gate (supervisor-scoped, exercised in 21.6)
- `agent_reviews` + `review_destinations` tables with
  CloudEvents fan-out
- Plugin tool count grew 29 → 32

## Earlier phases

Collapsed.  Read [`ROADMAP.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/ROADMAP.md)
for the per-phase summary or
[`CHANGELOG.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/CHANGELOG.md)
for the full per-sprint detail.
