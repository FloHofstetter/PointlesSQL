# Entity-link discovery review walkthrough

> **Mode:** `agent` · **Surface:** four `pql_*` entity-discovery tools

End-to-end replay of a Family-A agent triaging the auto-
discovery candidate queue: list pending matches scored by the
Jaccard / token-overlap detector, accept a high-confidence
`same_as` candidate, reject a noise match, defer one for a
human reviewer.  Browser-pendant: the `/admin/entity-discovery`
page (also ships with a "Run now" trigger button).

The auto-discovery scheduler scans entity pairs in the same
workspace, scores PK-column overlap (Jaccard) plus column-name
similarity (token overlap after snake / camel splitting), and
persists candidates scoring ≥ 0.7 into a pending queue.  This
playbook exercises the four tools:

* `pql_list_pending_entity_link_candidates` — read the queue.
* `pql_accept_entity_link_candidate` — promote to a live link.
* `pql_reject_entity_link_candidate` — drop it.
* `pql_defer_entity_link_candidate` — punt to a future review.

## Prerequisites

- A running PointlesSQL with the API key reaching a steward or
  admin principal.  All four review actions are gated steward /
  admin server-side.
- A `hermes-agent` session loaded with the
  `hermes-plugin-pointlessql` plugin.
- At least one pending candidate in the workspace — either via
  the `/admin/entity-discovery/run-now` trigger or by waiting
  for the `entity_link_discovery` scheduler kind (enabled in
  the registry, default-disabled at install).

## Steps

### 1. List the pending queue

Drive `pql_list_pending_entity_link_candidates` with no args
(defaults to `status: pending`).  Verify the envelope:

```json
{
  "ok": true,
  "data": {
    "candidates": [
      {
        "id": 11,
        "kind": "same_as",
        "source_entity_id": 4,
        "target_entity_id": 7,
        "confidence_score": 0.92,
        "evidence_json": "{...}",
        "discovered_at": "..."
      },
      ...
    ]
  }
}
```

Candidates are sorted by `confidence_score` descending — high-
confidence matches surface first.  The `evidence_json` payload
encodes which columns drove the match (PK overlap set + token
similarity score per column pair).

### 2. Inspect the evidence on the top candidate

Hold the first candidate's `id` in agent memory.  Read its
`evidence_json` to decide whether to accept, reject, or defer.
A typical accept signal: `confidence_score ≥ 0.85` plus the PK
overlap set covers the natural-key columns the human steward
would also use.

### 3. Accept a high-confidence candidate

Drive `pql_accept_entity_link_candidate` with:

```json
{ "candidate_id": <id> }
```

Verify `{ok: true, data: {decision: "accepted", reviewed_at: ...}}`.
The promotion goes through the canonical `link_entities` helper
— a single `entity_link` row appears, and the candidate is
removed from the pending queue.

### 4. Re-list the queue

Drive `pql_list_pending_entity_link_candidates` again.  The
accepted row no longer appears; the next-best candidate is now
at index 0.

### 5. Reject a low-confidence candidate

Pick a candidate with `confidence_score < 0.75` (or with
evidence that looks coincidental — e.g. only one column matched
because both products carry a `created_at` column).  Drive
`pql_reject_entity_link_candidate` with `{candidate_id: <id>}`.
Verify `data.decision == "rejected"`.  No `entity_link` row is
created; the candidate is permanently out of the pending queue.

### 6. Defer an ambiguous candidate

Pick a candidate the agent is uncertain about and drive
`pql_defer_entity_link_candidate` with `{candidate_id: <id>}`.
Verify `data.decision == "deferred"`.  Re-list with
`{status: "deferred"}` to confirm the candidate moved out of
pending into the deferred bucket — a human reviewer can revisit
from `/admin/entity-discovery` later.

### 7. Double-decision is a conflict

Drive `pql_accept_entity_link_candidate` again with a
`candidate_id` that has already been decided.  Verify the
envelope is `{ok: false, error: "http 409", ...}` — the
server-side guard refuses to re-decide a candidate.  This is
the safety net that prevents accidental double-promotion.

### 8. Trigger a fresh discovery pass (admin)

If the agent has admin scope, POST `/api/admin/entity-discovery/
run-now` synchronously.  No plugin tool ships for this trigger
by design — admin one-off ops route through the browser surface
or a curl call.  The next `pql_list_pending_entity_link_candidates`
call surfaces any new matches.

## Found bugs

* **Admin review queue at `/admin/entity-discovery` would never
  surface candidates** (2026-05-31 replay). The Alpine factory
  read `res.json?.candidates`, but `window.pqlApi.fetch` returns
  the parsed body under `res.data`. Empty workspace masked the
  symptom; switching to `res.data?.candidates` and re-triggering
  `Run now` confirmed the fix. Fixed at source in
  [frontend/js/pages/admin_entity_discovery.js](../../frontend/js/pages/admin_entity_discovery.js).
* **Three-way route collision on `/api/data-products/{catalog}/{schema}/entities`**
  blocks seed-via-API for end-to-end accept/reject/defer replay
  (2026-05-31 round-two replay, pre-existing). GET / POST / DELETE
  on `…/entities` are each defined twice — once in
  [api/data_products_routes/entities.py](../../pointlessql/api/data_products_routes/entities.py)
  (the Phase-134 declare-entity surface that the candidate scorer
  feeds from) and once in
  [api/data_products_routes/interop.py](../../pointlessql/api/data_products_routes/interop.py)
  (mesh column-to-entity binding). `interop_router` is registered
  first, so the entities.py handlers are unreachable from the
  network. POST `{entity_name, source_table, primary_key_columns}`
  returns the interop validator's `"entity_slug, table and column
  are required"`. No client (UI, plugin, hermes-agent) currently
  uses the shadowed entities.py POST, so production paths still
  work via the plugin tool surface — but the bug means the Phase
  145 admin review queue cannot be exercised end-to-end from the
  browser alone until the routes are disambiguated. Out-of-scope
  for the replay session; flagged for a future refactor pass.
