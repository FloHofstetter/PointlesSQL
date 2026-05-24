# E2E walkthrough — Per-cell social in the notebook editor

> **Mode:** browser · **Surface:** `/notebooks/edit/<path>`

This playbook validates Phase 95's cell-level social surface end to
end: open a notebook, comment on a single cell, react to it, follow
it, tag it, then **edit the cell's source and reload** to confirm
the comment / reaction / follow / tags all survive the
similarity-gated reconciliation pass.

The identity-survival step (5) is the headline test — it's the
single behaviour the entire phase exists for.

## Setup

```bash
# Terminal 1 — soyuz-catalog
cd ~/git/soyuz-catalog
uv run soyuz-catalog       # http://127.0.0.1:8080

# Terminal 2 — PointlesSQL
cd ~/git/PointlesSQL
uv run pointlessql         # http://127.0.0.1:8000
```

Log in as a user with notebook-editor access.  Use
`notebooks/mcp_demo.py` as the playground notebook — pick any
three-or-four-cell notebook if you prefer; the test is independent
of the source.

## 1. Open the notebook, identify a cell

Navigate to `http://127.0.0.1:8000/notebooks/edit/mcp_demo.py`.  Pick
the second cell (index 2 in the file order).  Confirm the cell
header shows:

* Left cluster: cell-type pill, `[N]` exec-count placeholder,
  duration field, **tag picker icon**.
* Right cluster: dirty dot (if pending), **💬 chip** (Phase 95.2 —
  `<i class="bi bi-chat-dots">`), Run, type-dropdown, History,
  cell-management group.

If the 💬 chip is missing, the cell has no stable UUID yet — hit
Cmd-S (or wait for the 5-second autosave).  The first save mints
the UUID and the chip appears.

## 2. Post a comment on the cell

Click the 💬 chip.  An inline thread expands **between the cell's
output zone and the next cell**.  Initial state: "No comments on
this cell yet."  Six reaction buttons render (👍 ❤️ 🎉 😄 😕 👀)
above the comment list; a Follow button sits in the thread header.

Type `looks off, double-check the filter` into the textarea, click
Post.  Verify:

* The comment renders with your display name + relative timestamp.
* The chip badge updates from `💬` to `💬 1`.
* The bulk-counts endpoint reflects the new count — open
  DevTools → Network and force a notebook reload; the
  `/_bulk_counts?notebook_id=...` round-trip should return
  `{"comments": 1}` for this cell's UUID.

## 3. Add an emoji reaction

Click the ❤️ button in the reaction strip.  The button flips to
filled (`btn-primary`), the count appears as `1`.  Reload the page
to confirm persistence.

## 4. Follow the cell

Click the Follow button in the thread header.  It flips from
`btn-outline-primary` to `btn-primary` and reads "Following (1)".
This is now a notification target — future writes to this cell's
comments / reactions hit the user's feed via the existing fanout.

## 5. **Identity-survival test (the headline)**

Click into the cell's editor and add a blank line, or rename one
variable.  Wait for autosave (5 seconds), or hit Cmd-S.

Hard-reload the page (Cmd-Shift-R).  Confirm:

* The 💬 chip still shows `💬 1` on the same cell.
* Clicking it still shows the same comment, the ❤️ reaction is
  still there, the Follow button still says "Following".

The cell's `content_hash` changed (the source changed), but the
reconciler matched the new hash to the existing `notebook_cells`
row via pass-2 ordinal-similarity, kept the same `cell_uuid`, and
all social rows stayed attached.

## 6. Add a curated tag

Click the `<i class="bi bi-tag">` icon in the cell-header left
cluster.  The dropdown shows the curated list (`#etl`, `#draft`,
`#prod`, `#wip`, `#verified`, `#broken`).

Click `#wip`.  A pill `#wip` appears next to the type-pill in the
header.  The cell goes dirty (yellow dot); autosave persists the
new `tags=["wip"]` marker into the `.py` file.

Open `notebooks/mcp_demo.py` in a separate terminal:

```bash
grep -n "tags=" notebooks/mcp_demo.py
```

The `# %% tags=["wip"]` line appears on the cell's marker.

## 7. Add a custom tag via the escape hatch

Open the tag picker again.  Click "Custom…".  Type
`integration-blocker`, hit Enter.  Confirm:

* The pill appears next to `#wip`.
* The `.py` file now has `tags=["wip", "integration-blocker"]` on
  that cell.
* Removing a tag is a click on the pill (× icon on hover).

## 8. Delete the cell — chip disappears

Hit the trash button in the cell-management group to delete the
cell.  Save (Cmd-S).

The 💬 chip is gone (the cell is gone).  Open the activity feed at
`/feed` — the comment is still reachable via its
`#notebook_cell:<ref>` citation, but resolving the link lands on
the "deleted cell" placeholder page.

## Coverage

| Behaviour | Validated by step |
| --- | --- |
| Chip render gated on cell_uuid | 1 |
| Inline thread mount + lazy load | 2 |
| Comment POST + bulk-count refresh | 2 |
| Reactions per-emoji toggle | 3 |
| Follow / unfollow + count | 4 |
| **Identity survival across edit + reload** | **5** |
| Curated tag pick | 6 |
| Custom tag escape hatch | 7 |
| Soft-delete on cell removal | 8 |

## Known limitations to test against

* **Cut + edit + paste-elsewhere loses identity** — moving a cell
  AND editing it heavily lands below the similarity gate and mints
  a fresh UUID.  Documented in
  [`docs/concepts/cell-level-social.md`](../concepts/cell-level-social.md).
* **Delete + identical replacement keeps UUID** — typing back the
  exact same source at the same position re-claims the soft-deleted
  row.  Rare enough in practice that we accept it.

## Related walkthroughs

* [`agent_memory.md`](agent_memory.md) — Phase 90's brain browser
  uses the same polymorphic social surface for `agent_memory`.
* [`notebook-editor.md`](notebook-editor.md) — the broader notebook
  editor walkthrough.
