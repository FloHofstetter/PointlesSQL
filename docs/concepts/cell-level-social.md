# Cell-level social — Comments, reactions, and tags per notebook cell

Phase 95 extends the polymorphic social schema from Phase 77 down a
level: any **single cell** inside a `.py` notebook is now its own
social entity.  A user (or a Phase-101 reviewer agent) can drop a
comment on the cell that broke, react to the chart in cell 7, or
follow that specific cell so a future edit pings them.

The conceptual counterpart of Google Colab cell-comments — but with
two additions that lean into the agent-supervision posture:

* **Lightweight cell-tags** (`#etl`, `#draft`, `#prod`, `#wip`,
  `#verified`, `#broken`) for status / lifecycle categorisation.
* **Stable cell identity** that survives source edits, so a thread
  attached to "cell 7" doesn't orphan the moment the user fixes a
  typo.

## Cell identity: the hard part

The on-disk `.py` format is IDE-agnostic.  No PointlesSQL-specific
sidecar tokens ride the marker grammar — anyone opens the file in
VSCode or vim, edits, saves, and the file stays clean.  This rules
out the easy path of writing a per-cell UUID into the marker line.

PointlesSQL already uses an FNV-1a-64 `content_hash` of the
normalised source as the per-cell identity for `notebook_outputs` and
`notebook_cell_runs`.  But that hash **changes on every meaningful
edit** — a typo fix breaks the social link.

Phase 95 introduces a thin mapping table `notebook_cells` keyed by a
UUID minted at first save.  The save-path reconciler in
[`cell_reconciliation.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/notebook/cell_reconciliation.py)
maps new cell positions to existing UUIDs via a three-pass algorithm:

1. **Exact-hash match** — handles reorderings + whitespace-only edits +
   no-op saves.  When multiple existing rows share a hash, the
   tiebreak is smallest `|ordinal_hint − i|`.
2. **Similarity-gated ordinal fallback** — for each new cell still
   unmatched, the existing row at the same position is considered.
   Match only if the Jaccard similarity of their normalised
   3-char-shingle sets ≥ 0.5.  This is the gate that prevents the
   "delete cell, type unrelated replacement at same position" case
   from silently stealing the deleted cell's UUID.
3. **Fresh UUID** — anything still unmatched is treated as a brand-new
   cell.

Existing rows that finish all three passes unmatched are
soft-deleted via `removed_at = NOW()`.  Their social anchor stays
addressable from the notebook-level activity feed; the inline chip
just doesn't render.

The `entity_ref` for `kind='notebook_cell'` is the composite
`{notebook_uuid}:{cell_uuid}` — both halves UUID4 strings.  This
makes workspace-scoped probes a cheap `LIKE 'nb_uuid:%'` against the
existing `social_targets` index.

### Known limitation: cut + edit + paste-elsewhere

There is no signal to distinguish "move a cell and edit it" from
"delete a cell and insert a different one at a different position".
The reconciler treats the latter — which is what the source
similarity gate sees — as the truth.  An edit-and-move-far loses
the UUID; an edit-and-stay-put keeps it.

This is intentional.  Restoring identity through aggressive
heuristics would steal UUIDs across genuine cell boundaries,
which is the worse failure mode (a thread silently re-anchors to
unrelated code).

## API contract

The polymorphic `/api/social/{kind}/{ref:path}/...` routes
automatically dispatch for the new kind:

```text
GET    /api/social/notebook_cell/{nb}:{cell}/comments
POST   /api/social/notebook_cell/{nb}:{cell}/comments         {body_md}
DELETE /api/social/notebook_cell/{nb}:{cell}/comments/{id}
GET    /api/social/notebook_cell/{nb}:{cell}/reactions
POST   /api/social/notebook_cell/{nb}:{cell}/reactions        {emoji}
DELETE /api/social/notebook_cell/{nb}:{cell}/reactions/{emoji}
GET    /api/social/notebook_cell/{nb}:{cell}/followers/count
POST   /api/social/notebook_cell/{nb}:{cell}/follow
DELETE /api/social/notebook_cell/{nb}:{cell}/follow
```

To avoid N+1 round-trips on notebook load, a bulk-count endpoint
returns every cell's counts in one shot:

```text
GET    /api/social/notebook_cell/_bulk_counts?notebook_id={uuid}
```

The frontend calls this once on notebook open and again after each
save (debounced).  Realtime updates while a thread is open piggyback
on the existing notification stream — no separate SSE for Phase 95.

## Cell-tag vocabulary

Curated list, hybrid escape:

| Tag | Intended semantics |
| --- | --- |
| `#etl` | Step in an ETL pipeline |
| `#draft` | Exploratory, not promoted yet |
| `#prod` | Stable, used downstream |
| `#wip` | Active work, expect churn |
| `#verified` | Reviewed and confirmed correct |
| `#broken` | Known failure, do not run |

The picker also exposes a "Custom…" entry that lets users add
free-text tags.  The marker grammar already round-trips arbitrary
`tags=[...]` losslessly, so custom tags persist without any schema
work.  The `parameters` tag is special-cased via the existing
cell-header dropdown (papermill convention) and stays out of the
curated list to avoid double-surface.

## Forward compatibility

Phase 101 (Reviewer-Agent v2 per-cell) keys off this exact
`entity_ref` format.  Phase 96 (inline AI-assistant in notebook)
references "the cell I'm proposing this for" via the same
`cell_uuid`.  Phase 97 (revision history + diff) pins snapshots to
the cell UUID so the diff viewer can walk the time axis of one
specific thread.

The single contract change Phase 95 ships — the composite
`notebook_uuid:cell_uuid` ref shape — is the load-bearing piece;
later phases extend the surface without breaking the existing
threads.
