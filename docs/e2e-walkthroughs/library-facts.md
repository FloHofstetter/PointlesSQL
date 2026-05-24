# library/facts — pin-to-memory browse page

**Mode**: playbook
**Phase**: 97 — Pin-to-Memory
**Surface**: ``/library/facts`` browse page + per-fact detail
URL + Phase-81 feed fan-out.

## Status

Phase 97.X.1 shipped the backend in commit ``36dc878``; 97.X.2
shipped the UI affordances + ``/library/facts`` page in
``cfaad5c``; 97.X.3 added a dedicated ``render_kind = "fact"``
branch in the feed renderer so pinned-fact events surface with a
📌 icon instead of falling through to the generic notification
card.

## Preconditions

- PointlesSQL stack up at
  [http://127.0.0.1:8000](http://127.0.0.1:8000) with at least
  one workspace member logged in.
- At least two notebook revisions exist (run + save a scratch
  notebook twice). One whole-revision pin + one cell-output pin
  give the browse page meaningful cards.
- Playwright-MCP attached with ``--browser firefox`` per
  [`CLAUDE.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md)
  line 220.
- Asset version is ``rc72`` or higher (the relative-import
  asset-stamping picks up the latest activity_pane.html +
  scripts.html diffs).

## Walkthrough

### Part A — page renders

1. Navigate to
   [/library/facts](http://127.0.0.1:8000/library/facts).
2. Assert: ``<h1>`` shows ``Facts`` and a card grid renders.
   Each card carries the fact title, optional description
   markdown, notebook path, pinned-by avatar, and ``pinned_at``
   timestamp. Cards with ``cell_content_hash`` set show a small
   source excerpt; whole-revision cards show a
   ``Whole revision`` chip instead.
3. Assert: 0 console errors. ``GET /api/notebooks/facts`` is the
   data source; check Network tab for a single 200.

### Part B — filter by notebook

1. Use the ``Notebook`` filter input to type the path of one of
   the pinned notebooks (e.g. ``scratch.py``).
2. Assert: card grid filters down to cards whose
   ``notebook_path`` matches. Empty filter restores the full
   grid. The filter is purely client-side over the already-fetched
   list (so the same ``GET /api/notebooks/facts`` is reused) — no
   second network call.

### Part C — include unpinned toggle

1. Pick a card and click ``Unpin`` (button on the detail panel,
   see Part D for navigation).
2. Return to the grid. Assert: that card is gone.
3. Toggle the ``Include unpinned`` switch on. Assert: the
   unpinned card returns with a strikethrough on the title and a
   greyed-out avatar. The toggle persists via localStorage
   under ``pql.library.facts.includeUnpinned.v1``.

### Part D — click into detail

1. From the grid, click any active card.
2. Assert: URL flips to ``/library/facts/<fact_uuid>``. The
   detail view shows the fact title + description + revision
   snapshot (or cell-output snapshot for cell-scoped facts).
3. For cell-output facts, the snapshot includes the source
   excerpt + the frozen ``result_snapshot_json`` (rendered as a
   small table preview). For whole-revision facts, the detail
   shows the revision UUID + the
   [/notebook/editor?path=...&rev=...](http://127.0.0.1:8000/notebook/editor)
   link.
4. Click the notebook link in the detail. Assert: lands on the
   notebook editor at the right revision (Phase 97 revision
   panel highlights the right row).

### Part E — unpin from detail + feed surfaces it

1. From the detail panel, click ``Unpin``. Assert: confirmation
   toast ``Unpinned`` appears; ``DELETE
   /api/notebooks/facts/<uuid>`` returns 200; the page
   re-renders with the unpinned banner.
2. Navigate back to [/feed?filter=all](http://127.0.0.1:8000/feed?filter=all).
3. Assert: the original pin event is still in the feed (unpin
   does not retroactively erase the notification; it is the
   audit of the moment-it-was-pinned). The card carries the
   ``bi-pin-angle-fill`` icon + summary text and links to
   ``/library/facts/<uuid>`` — clicking now shows the unpinned
   detail (Part E.1).

## Found bugs

- (initially empty)

## What the replay caught

- (initially empty; bugs discovered land here with
  ``BUG-97-XX-XX`` IDs.)
