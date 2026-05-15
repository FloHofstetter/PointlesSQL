# Phase 77 — Social as Connective Tissue

> "GitHub on Git, but for data."

Phase 77 lifted PointlesSQL's social layer from a DP-only surface
into kind-agnostic connective tissue.  After Phase 77, every named
platform entity carries the same Discussion / Endorsements /
Followers / README / Stars / Issues primitives that data products
have had since Phase 71.

## What landed

Across eleven sub-phases, the social layer became polymorphic
along every axis:

| Sub-phase | Scope | Migrations |
|---|---|---|
| 77.0 (+ A–H) | Polymorphic foundation: `social_targets` anchor + entity registry + kind-dispatch + audit-mirror + `fanout_event` | 3 |
| 77.1 (+ 1.5) | UC tables get social surface | 0 |
| 77.2 (+ 2.1) | Registered models get social surface | 1 |
| 77.3 (+ 3.B) | Branches get social surface + promote-gate | 1 |
| 77.4 | Agent runs get social surface | 0 |
| 77.5 | Schemas + catalogs get social surface | 0 |
| 77.6 | Notebooks (new UUID identity) + saved queries | 1 |
| 77.7 | GitHub-Issues entity | 1 |
| 77.8 | Stars + polymorphic Follow + Reactions | 3 |
| 77.9 | Cross-entity feed (full-body FTS deferred) | 0 |
| 77.10 | Workspace-as-Organization landing | 1 |
| 77.11 | Polish + announce (this doc) | 0 |

Total: 11 alembic migrations, ~230 new pytest cases, every
registered entity kind exposes the same polymorphic
`/api/social/{kind}/{ref}/...` namespace.

## Architecture

**One polymorphic anchor.**  Every social row keys on
`social_targets.id`.  The anchor carries the polymorphic
discriminator `entity_kind` plus an opaque `entity_ref` string
that addresses the underlying entity:

* `dp` — `catalog.schema` (+ optional `data_product_id` back-pointer)
* `table` — `catalog.schema.table`
* `model` — `catalog.schema.name`
* `branch` — branch FQN (`catalog.schema__branch_xxx`)
* `run` — agent_run UUID
* `schema` — `catalog.schema`
* `catalog` — bare catalog name
* `notebook` — `notebooks.id` UUID (new in 77.6)
* `saved_query` — saved-query slug
* `issue` — issue id as text (issues are themselves anchors)
* `workspace` — workspace slug

**One registry.**  `pointlessql/services/social/entity_registry.py`
is the single source of truth for what each kind means.  Adding
a new kind is mostly declarative: register an `EntityKindSpec`,
add a `parse_ref` branch in `_kind_dispatch.py`, add a citation
regex in `citations.py`, wire the tab strip into the detail-page
template.

**Capability flags drive the UI.**  `supports_reviews` /
`supports_endorsements` / `supports_readme` / `supports_issues` /
`supports_stars` opt entity kinds into specific tabs.  The
polymorphic handlers gate themselves via the same flags so
non-applicable kinds 404 / 501 cleanly.

## Locked decisions

These survived the entire Phase-77 sequence:

1. **Polymorphic sidecar** stays the schema strategy.
2. **Issues vs Discussions** = GitHub split; an issue has its own
   `social_target` row.
3. **Branch promote-gate** is opt-in (workspace flag).
4. **READMEs are polymorphic** via `social_target_id`.
5. **Stars separate from Follows** — different primitives.
6. **Workspace-as-Organization** with pinned entities (77.10).
7. **77.0 foundation** stays the single polymorphic refactor;
   77.1–77.10 are pure entity-type / feature additions.
8. **Notebook entity_ref = immutable UUID** (77.6).
9. **Audit-log prefix back-compat**: `data_product:` for
   `kind='dp'`; generic `{kind}:` for every other kind.
10. **Sibling-table pattern** for polymorphic rollouts on tables
    with unnamed implicit PKs (per 77.8.B post-mortem).
11. **Additive UNIQUE pattern** for polymorphic idempotency on
    tables with composite legacy PKs (per 77.8.C post-mortem).

## Deferred work

The plan called for a consolidation migration in 77.11 (collapse
`data_product_follows` → `social_follows`, rename
`data_product_reactions` → `social_reactions`,
`data_product_readmes` → `entity_readmes`, drop the legacy
`uq_dp_review_one_per_user`).  This was deliberately split out:

* **Full-body FTS in `audit_search`** — `audit_fts.py` extension
  to include comment bodies in the index.  Cross-kind FTS search.
* **Comment-reactions polymorphism unlock** — the underlying table
  is polymorphic-safe (keyed by `comment_id`); the open work item
  is refactoring the route to look up the comment row without a
  DP context.  Currently 501 for non-DP kinds.
* **Schema rename + legacy UNIQUE drop** — the consolidation
  migration risks-vs-reward stayed unfavourable for the close-out
  sweep (every consumer table reads correctly against the legacy
  names today).
* **Generalised badges** — `badges.py` thresholds query DP-only.
* **`data_product.html` migration** to `socialTabs(kind, ref)` —
  remaining inline Alpine still works; the migration is a polish
  ask.
* **`fanout_dataproduct_event` deletion** — wrapper has zero
  active call-sites in routes/handlers; three test files still
  reference it.  Defer to a dedicated cleanup phase.

Each of these is fully scoped in the plan file at
`/home/flo/.claude/plans/ja-plane-phase-28-tidy-feather.md` and
can land as a follow-up "Phase 77.X polish" sub-phase without
phase-77-foundation rework.

## Test surface

| Phase | New tests |
|---|---|
| 77.0–77.3.B | ~50 cumulative |
| 77.4 | 18 |
| 77.5 | 27 |
| 77.6 | 17 |
| 77.7 | 32 |
| 77.8 | 27 |
| 77.9 | 7 |
| 77.10 | 9 |
| **Total Phase 77** | **~167 incremental, ~232 cumulative** |

Pyright budget stays at 609 warnings across the entire phase
(no regressions, no headroom burned on social-layer work).

## What's next

Phase 77 closes here.  The deferred polish work above lands in a
future "Phase 77 polish" sub-phase tracked separately in the
roadmap.  The user-visible outcome of Phase 77 is straightforward:
every named platform entity now has the same social surface as a
data product.  The platform has GitHub-style connective tissue at
every junction where two humans need to coordinate.
