---
title: ADR-0011 Data-Product-as-Code
status: Accepted
date: 2026-05-30
---

# ADR-0011 — Data-Product-as-Code

## Status

**Accepted** (2026-05-30).

## Context

Up to phase 142 PointlesSQL accumulated declarative artefacts for a
data product across many endpoints — output ports, input ports,
SLOs, entities, contract tests, fixtures, policies, glossary
bindings — each authored through its own surface and stored in its
own table.

The data-mesh book asks for these artefacts to be expressible as
**one YAML document** that lives under Git, gets code-reviewed like
any other source, and is reconciled into the platform via a
plan-then-apply cycle.  PointlesSQL already has
`DataProductYamlDraft` rows that track *drafts on disk* — what was
missing was the reconciler that converts a draft into the live DB
state without piecewise calls.

The book offers two shapes:

* **State**-style (Terraform): the spec is the source of truth;
  drift between spec and live state is reconciled towards the spec
  on every apply.
* **Migration**-style (Alembic): every change is a versioned
  upgrade; the spec drives forward-only steps.

State-style fits the data-product lifecycle better — a product
owner edits one YAML file, and the platform converges every
substrate (ports / SLOs / entities / contracts / fixtures /
policies) towards it.

## Decision

Phase 143 ships state-style **Data-Product-as-Code**:

1. **Strict spec.**  `DataProductSpec` is a pydantic model with
   `extra=forbid` on every nested model.  Typos in user-authored
   YAML surface as validation errors rather than silently-ignored
   fields.  `protected_namespaces=()` on the top model so `schema`
   can stay a domain field without conflicting with pydantic's
   reserved `schema` method.

2. **Planner before applier.**  `plan_spec(...)` walks each
   sub-section, queries the matching DB rows for the product, and
   emits ordered `Op` records — `additions`, `modifications`,
   `removals`.  Equality is shallow on the discovery-shaped dict
   the exporter produces, so a round-trip `plan(export(p))`
   returns a no-op plan.

3. **Applier reuses existing CRUDs.**  Each Op routes to the
   existing service helper (`create_output_port`,
   `declare_entity`, `declare_slo`, `declare_contract_test`,
   `declare_fixture`, `set_product_policy`) — no direct
   `session.add`, no duplicate validation logic.  Idempotency is
   the test surface: applying a spec twice produces zero ops the
   second time.

4. **Exporter as inverse.**  `export_data_product(...)` snapshots
   the live state into a `DataProductSpec`.  The round-trip
   `apply → export → plan` produces an empty plan.

5. **Routes shaped like a Plan-then-Apply API.**  Three endpoints
   on the data-products router:
   - `POST /api/data-products/plan` (any-user, dry-run only).
   - `POST /api/data-products/apply` (steward/admin; `?dry_run=1`
     supported).
   - `POST /api/data-products/{c}/{s}/export` (any-user).

6. **Spec field carries unit auto-resolution.**  KIND_META on the
   SLO service auto-assigns a `unit` when the declare helper
   resolves an SLO.  The planner mirrors that — if the spec leaves
   `unit` as `None`, the planner treats the DB-side unit as the
   desired value.  Without this, an exported-then-re-applied spec
   would always produce a modification op on the SLO.

## Consequences

**Positive.**

- Owners can version a product as a YAML file; CI can `plan` the
  PR before merge.
- Drift between spec and DB is observable (the plan output) and
  recoverable (the apply outcome).
- The applier becomes the canonical write path for batch product
  authoring; piecemeal endpoints stay available for surgical
  edits.

**Negative.**

- The applier carries the union of every CRUD's argument set; new
  subentity kinds must extend both the planner diff and the
  applier dispatch.  The hard-coded dispatch table is a
  forward-cost we accept for explicit op handling.
- Idempotency is at-the-field-level only.  A breaking change to
  the discovery shape (e.g. a SLO kind rename) would produce a
  remove + add op pair instead of an in-place update.  Acceptable
  trade-off — the result still converges on the spec.
- Top-level `name` in the spec is currently stored in
  `contract_json`'s name field; if `DataProduct.name` becomes a
  first-class column in a future phase, the exporter + applier
  need a one-line update.

## Open follow-ups

- CLI: `pql apply -f product.yaml`, `pql plan -f product.yaml`,
  `pql export {catalog}.{schema}` belong on the Typer surface so
  CI workflows do not need a running web server.  Substrate is
  ready; CLI wiring lands in the Surface-Welle alongside the
  admin UI.
- Glossary bindings + identity_requirements JSON: today they
  round-trip through the spec untouched; the applier writes them
  only as part of the policies block, not as standalone subentity
  ops.  Future phase: per-kind `glossary_binding` op + dedicated
  port-identity write helper.
