# ADR 0001 — Native notebook editor architecture

Status: Accepted (Phase 12.6, Sprint 58)
Supersedes: nothing (greenfield; the Sprint-3 JupyterLab iframe at
`/notebook` remains live until Sprint 63 retires it — hard rule,
no regression window for existing users)

## Context

Phase 12.6 replaces the JupyterLab iframe with a first-party
notebook editor. Three up-front architectural decisions bind every
subsequent sprint and are cheap to get wrong, expensive to reverse:

1. **Editor topology** — one Monaco instance over the whole
   notebook, or one per cell?
2. **Output persistence schema** — what tables, keyed by what?
3. **Cell identity** — how do we keep outputs attached to cells
   across edits, reorders, and renames?

Sprint-58 ships the skeleton that locks these in. Sprints 59–64
build on top and should not have to revisit any of the three.

## Decision 1 — Single Monaco over a virtual document

We run **one** Monaco editor over the entire `.py` file. Cell
boundaries render via Monaco *decorations* (background colour
bands) and *view zones* (gutter-inserted widgets for toolbars +
output areas). This matches VSCode's Python Interactive Window.

### Alternatives considered

**Monaco-per-cell** (classic Jupyter, Colab, nbclassic). Every
cell is its own editor instance, outputs sit in plain DOM flow
between cells.

- Pro: cell insert/delete is mount/unmount; output positioning is
  trivial; per-cell state is component-local.
- Contra: LSP boundary per cell. Pyright is file-based — to get
  cross-cell type inference we would synthesise a virtual file
  server-side and remap every diagnostic range. Every refactor
  across cells ("Go to definition of `df` from cell 3 when it's
  defined in cell 1") becomes protocol gymnastics.
- Contra: N editor instances ⇒ N tokenisers, N webworker
  contexts. Notebooks with 100+ cells become a memory problem.
- Contra: per-cell undo stack — VSCode users expect global
  Cmd+Z across the whole notebook.
- Contra: cross-cell keyboard nav requires bespoke blur-on-
  boundary logic; single-Monaco gets this for free.

**Single Monaco + view zones + overlay widgets** (VSCode approach).

- Pro: Pyright sees the file exactly as it is on disk. No
  wrapping, no remapping, no virtual-file server.
- Pro: Global undo, global find/replace, global cursor history.
- Pro: One tokeniser, one webworker. Scales to large notebooks.
- Pro: Keyboard nav across cells = native editor navigation.
- Contra: cell insert/delete = surgical text ops
  (`editor.executeEdits` inserting `\n# %% id=<uuid>\n`). More
  intricate than DOM mount/unmount.
- Contra: output areas and per-cell toolbars require Monaco's
  view-zone + content-widget API — steeper learning curve.
- Contra: view-zone DOM updates retrigger Monaco layout; rich
  outputs in many cells could be janky at scale. Mitigation: use
  view zones as **spacers only** and render output DOM in a
  separate layer that tracks view-zone top offsets. If we still
  see layout stalls after Sprint 60, measure before pivoting.

### Why single wins

The LSP argument alone is decisive. The whole phase's quality
bar is "as good as VSCode Python Interactive"; VSCode is
single-Monaco and that is not incidental. Multi-Monaco is what
makes classic Jupyter feel broken for cross-cell refactors. The
view-zone complexity is a **one-time up-front cost**; the multi-
Monaco complexity is a recurring tax (cross-cell LSP, undo,
focus) paid in every subsequent sprint.

Rejection is final for Phase 12.6 — revisit only if Sprint-60
measurements show unfixable layout jank.

## Decision 2 — Output persistence schema

Outputs live in the existing PointlesSQL SQLite metadata DB
(same DB as users / audit_log / query_history). Alembic 017
ships the two tables below. Sprint 58 defines the DDL here
so Sprint 59's ephemeral output flow already writes into a
schema-compatible in-memory shape.

```sql
CREATE TABLE notebook_outputs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path          TEXT    NOT NULL,
    cell_id            TEXT    NOT NULL,
    kernel_session_id  TEXT    NOT NULL,
    output_index       INTEGER NOT NULL,
    msg_type           TEXT    NOT NULL,  -- stream | execute_result | display_data | error
    mime_bundle        TEXT    NOT NULL,  -- JSON: {mime: data}
    metadata           TEXT,              -- JSON, nullable
    created_at         TIMESTAMP NOT NULL,
    UNIQUE (file_path, cell_id, kernel_session_id, output_index)
);
CREATE INDEX ix_notebook_outputs_lookup
    ON notebook_outputs (file_path, cell_id);

CREATE TABLE notebook_cell_runs (
    file_path          TEXT    NOT NULL,
    cell_id            TEXT    NOT NULL,
    kernel_session_id  TEXT    NOT NULL,
    execution_count    INTEGER,
    status             TEXT    NOT NULL,  -- ok | error | aborted
    started_at         TIMESTAMP NOT NULL,
    finished_at        TIMESTAMP,
    PRIMARY KEY (file_path, cell_id, kernel_session_id)
);
```

### Design notes

- **Key triple `(file_path, cell_id, kernel_session_id)`.** A
  given cell can have outputs from multiple kernel sessions —
  e.g. you reload after a crash and re-run selectively. We keep
  the latest session's outputs visible by default; older sessions
  are addressable for future "history" UI without a schema change.
- **`mime_bundle` as JSON TEXT.** Binary mimes (`image/png`,
  `image/svg+xml`) travel base64-encoded per Jupyter convention
  — same way `.ipynb` stores them. No BLOB column, no separate
  blob table. If 10+ MB outputs become common we add a
  sidecar-file pointer later without breaking this table.
- **Orphan policy.** Editor-level file rename → transactional
  `UPDATE notebook_outputs SET file_path = <new> WHERE
  file_path = <old>` (Sprint 63's workspace-tree integration
  handles this). File deletion → cascade-delete outputs. Simpler
  than a grace window; the user has git for recovery.
- **Clear / Restart.** Explicit `DELETE` by `file_path` +
  optional `cell_id` filter. Restart-kernel deletes for the
  outgoing `kernel_session_id` only, so a concurrent read-only
  tab keeps its view until it refreshes.
- **No size cap enforcement in schema.** Sprint 60 enforces a
  per-cell output byte-budget at the service layer; the DB
  just stores what it's given.

## Decision 3 — Cell identity via UUID in jupytext metadata

Every cell carries a UUID stored in its jupytext cell-marker
metadata under the key ``pql_cell_id``. jupytext's percent-format
writer round-trips arbitrary cell metadata when the notebook-
level ``jupytext.cell_metadata_filter`` allow-lists the key; we
pin the filter to ``pql_cell_id,-all`` on save so only this key
survives in the marker. (The Notebook-v4 top-level ``cell.id``
attribute is *not* preserved by jupytext's percent format, which
is why we carry our own key rather than the native one.)
Write example:

```python
# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: pql_cell_id,-all
#     text_representation: …
# ---

# %% pql_cell_id="4f8a1b7c-2d4e-4b3f-9c1a-6e8d7f5a2b1d"
import pandas as pd
df = pql.read_table("main.default.sales")

# %% [markdown] pql_cell_id="…"
# Optional markdown cell.
```

### Alternatives considered

**cell_hash = hash(cell.source).** Zero file pollution, no
metadata round-trip.
- Dealbreaker: editing one character of the cell source changes
  the hash, which orphans every output instantly. This defeats
  the persistence motivation — without persistence every reopen
  with a slow `pql.read_table()` is a 90-second wait; cell_hash
  keeps outputs only until you touch the cell, which is
  approximately never. Rejected on day one.

**UUID in an `.ipynb`-style sidecar JSON.** Keep the `.py` clean,
store `{path → {cell_index: uuid}}` in `.pql/notebooks.json`.
- Pro: `.py` stays copy-paste-clean.
- Contra: sidecar drifts on external edits (rename via `mv`,
  commit via `git add`), orphaning outputs on every round-trip
  with any non-PointlesSQL tool. The whole point of "`.py` is
  the source of truth" is that external tools don't break
  anything. A sidecar inverts that. Rejected.

**Hybrid: cell_hash fallback for foreign notebooks, upgrade to
UUID on first save.**
- This is actually just "UUID strategy with a migration path";
  adopted as an *implementation detail*, not a separate
  strategy. Foreign `.py` opens → load assigns fresh UUIDs to
  any cell without one (see :func:`notebook_doc.load_document`
  and its ``dirty`` flag), editor prompts save, on-disk file
  gains IDs.

### Why UUID-in-metadata wins

- Stable across edits (the persistence motivation holds).
- Stable across cell reorders (UUID travels with the cell, not
  with its position).
- External `mv` of the file: UUIDs still match; only the
  `file_path` column needs updating (see orphan policy above).
- jupytext already does the round-trip — zero custom parser on
  the server. Client-side the regex
  ``^#\s*%%(\s+\[markdown\])?\s+pql_cell_id="([0-9a-fA-F-]{36})"\s*$``
  is the one narrow parse the editor does — foreign marker
  variants are only accepted via jupytext on the server load path.
- One extra token per cell marker; visible in the `.py` but
  unobtrusive. Copy-paste into another script drops the marker
  line entirely (Python comment), so it's not even "leaking"
  into downstream scripts.

### Trade-off acknowledged

First open of an externally-authored `.py` notebook triggers a
dirty save (assigns UUIDs). The editor surfaces this via the
``dirty`` flag on the `NotebookDocument` payload, and the client
prompts via the toolbar's "unsaved changes" badge. Acceptable.

## Consequences

- Monaco vendored under `frontend/js/vendor/monaco/vs/` via
  `scripts/vendor-monaco.sh` (rev 0.52.0 pin). Contents are
  gitignored — dev/Docker bootstraps run the script once per
  version bump. The decision was made after confirming that the
  Chart.js precedent uses the jsDelivr CDN
  (`base.html:102`) — that works for single-file UMD bundles
  but Monaco is multi-file (workers, languages, themes) and
  wiring a runtime CDN base URL for those adds a production
  dependency on an external host that we reject for an offline-
  first dev story. Vendoring with a script is the middle ground
  between "commit 14 MB into git" and "trust npmjs.com at
  runtime".
- `jupytext>=1.16` added to `pyproject.toml` in Sprint 58.
- Sprint-60's Alembic migration 017 is pre-defined by this ADR
  — scope-creep on the schema goes through an ADR amendment,
  not a silent migration bump.
- Single-Monaco locks out any future "side-by-side two-notebook"
  tab UI from sharing an editor — each tab is its own Monaco
  instance. Acceptable; not a Phase-12.6 requirement.
- UUID-in-metadata pollutes the `.py` visually (one extra token
  per marker). Accepted trade-off for output persistence.

## Out of scope for Sprint 58

The skeleton intentionally stops at load / save / paint. Not
landing in Sprint 58, but tracked against their target sprints:

- Cell execution + ZMQ kernel over WebSocket — Sprint 59.
- Output rendering + persistence — Sprint 60 (schema is locked
  above; Sprint 59 writes into schema-shaped in-memory state).
- Pyright LSP + dual-source autocomplete — Sprint 61.
- Variable Explorer + "Insert from catalog" command — Sprint 62.
- Papermill bridge + Sprint-26 viewer re-point + JupyterLab
  subprocess retirement — Sprint 63.
- Playbook + phase close — Sprint 64.
