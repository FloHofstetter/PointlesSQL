---
title: ADR-0010 Cedar policy-as-code
status: Accepted
date: 2026-05-30
---

# ADR-0010 — Cedar policy-as-code

## Status

**Accepted** (2026-05-30).

## Context

PointlesSQL's governance surface up to phase 140 carried policy as
typed JSON fields on `data_product_policies` and
`workspace_governance_policies` (retention, encryption class,
residency, consent, ISO-8601 enforcement, consumption mode).
Inheritance is product ⇐ workspace ⇐ unset.  Enforcement happens at
specific call sites — masking on read, retention scan on schedule,
ISO-8601 validation before write, consumption enforcement at
discovery.

The data-mesh book asks for one more axis: **computational policy
as code** — policies authored as small, executable modules a data
product owner can edit, version, and dry-run *outside* the
PointlesSQL release cycle, then **evaluated at every read / write**
of the products they cover.

Three engines were on the table:

* **OPA / Rego** — battle-tested, but requires a sidecar.
  PointlesSQL is single-process by design; adding a Rego server
  doubles the operational surface.
* **Hand-rolled DSL** — controllable, but every project that
  reaches this milestone learns the bitter lesson that policy
  languages are harder than they look.
* **AWS Cedar** — purpose-built for ABAC.  Dehghani's *Data Mesh
  in Practice* names Cedar specifically as the reference shape.
  Has first-party Python bindings (`cedarpy`, the PyO3 wrapper
  around Cedar's Rust engine), pip-installable, single process.

## Decision

Phase 141 adopts **Cedar via `cedarpy`** as the policy-as-code
engine.

1. **Modules live in the metadata DB.**  `policy_modules` carries
   the authored Cedar source, version, enabled flag, and workspace
   scope.  Links to data products go through the existing
   governance policy rows as a JSON column
   (`linked_policy_module_ids`), preserving the product ⇐
   workspace inheritance the rest of the policy fields use.

2. **Linksverschiebung at the PQL layer.**  The engine plugs into
   the central `pql/_hooks.py` registry (introduced in phase 139),
   *not* at the HTTP rim.  Notebook, script, and agent callers can
   never bypass Cedar — they go through the same PQL primitives a
   web request does.  Cedar's `before_read` and `before_write`
   hooks each resolve the linked modules for the target product,
   ask `cedarpy.is_authorized` to evaluate, persist the decision,
   and raise `PermissionDeniedError` on `forbid`.

3. **Fail-closed on every error.**  Parse errors, runtime errors,
   and an empty effective-policy set after a link explicitly
   collapse to `forbid`.  The decision row records the failure
   class (`cedar_parse_error` / `cedar_runtime_error`) in
   `context_json` so the admin can see *why* the deny happened
   without spelunking application logs.  The empty-policy case
   stays a sentinel and is filtered before reaching the engine —
   no policy linked means "Cedar abstains", and the request
   continues through the other hooks.

4. **Per-version cache.**  The compiled Cedar policy set is cached
   on `(module_id, version)` so a 1k-eval/sec hot path avoids
   re-parsing.  Edits bump `version`; cache invalidation is
   scoped to the touched module so other workspaces don't pay the
   cost of one workspace's edit.

5. **Decision ledger separate from audit log.**
   `policy_module_decisions` is the engineering-shaped surface
   (one row per evaluation, joins back to module + principal +
   resource + latency + diagnostics).  `audit_log` keeps its
   human-shaped `policy.evaluation` rows.  The two writes happen
   in one `persist_decision` helper so call sites never forget
   one.

## Consequences

**Positive.**

- Owners can edit policies as code, test them in the admin
  sandbox, and link them to products without a PointlesSQL
  release.
- Every PQL read / write is gated by the same engine the discovery
  endpoint advertises.  No skew between "the contract says X" and
  "the runtime does Y".
- The decision ledger is a first-class audit surface — the admin
  sees not just *that* a policy denied access, but the Cedar
  diagnostic that explains *why*.

**Negative.**

- `cedarpy` is a Rust extension; the wheel size adds ~5MB to the
  install.  CI now has to keep `cedarpy` PyPI availability on the
  watch list.
- Cedar's diagnostic surface is engine-shaped (`Decision`,
  `Diagnostics.reasons`, `Diagnostics.errors`) — we serialise
  best-effort, so a Cedar version bump could change the shape of
  the `diagnostics` blob in the decision ledger.  The serialiser
  guards against missing fields; the contract is "shape is engine-
  defined".
- The fail-closed default trades soft failure for one-more-thing
  to debug.  Operators must be able to recover from a self-
  inflicted forbid — the admin endpoint to disable a module
  exists; documentation lives alongside the surface in the
  walkthroughs.

## Open follow-ups

- Schema-based ABAC: Cedar supports a schema declaration that
  validates principals / resources at compile time.  Phase 141
  ships without it because the resource set is tiny (DataProduct,
  OutputPort).  When `OutputPort` / `Table` / `EventSubscription`
  resources multiply, a schema becomes necessary; revisit in the
  Substrate-Welle 144 (schema versioning) follow-up.
- Cross-workspace inheritance: today modules are workspace-scoped.
  A future ADR may introduce platform-default modules that all
  workspaces inherit, mirroring the proposed Cost-Quota
  inheritance order (phase 146).
