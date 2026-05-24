# Notebook AI-Assistant walkthrough

End-to-end replay of the inline AI assistant in the
notebook editor.  Covers all three plugin tools:

* `pql_propose_cell` — add a new cell.
* `pql_fix_cell` — replace an existing cell's source.
* `pql_explain_cell` — attach a pinned explanation to a cell
  (auto-accepts and persists in the per-cell social drawer).

Provenance is verified at the end: every accepted proposal lands
in `notebook_cell_provenance` and stays addressable from the
cell's stable UUID.

## Prerequisites

- A running PointlesSQL with `POINTLESSQL_EDITOR_CHAT_ENABLED=true`
  (the default in dev).  The same flag gates both the SQL editor
  chat and the notebook AI assistant —
  the env-var prefix renamed from `POINTLESSQL_SQL_CHAT_*` to
  `POINTLESSQL_EDITOR_CHAT_*` .
- An LLM provider key in the env (else the WS closes with
  `LLM_NOT_CONFIGURED`).
- An authenticated browser session.
- The seed notebook `notebooks/phase96_walkthrough.py` shipped
  alongside this playbook.

## Steps

### 0. (Optional sanity check) — LLM not configured

Open `/notebooks/edit/phase96_walkthrough.py` while no provider
env var is set.  Click the toolbar **AI** button
(`data-testid="notebook-chat-toggle"`).  Expected: drawer slides
in, status pill reads "LLM not configured", an alert explains
how to set `ANTHROPIC_API_KEY`.  Set the key and reload.

### 1. Open the chat drawer

1. Navigate to `/notebooks/edit/phase96_walkthrough.py`.
2. Wait for the editor to load (cells render, status pill reads
   "Kernel: ready").
3. Click the toolbar **AI** button.

Expected DOM:
- `.pql-right-drawer` becomes visible (Sprint 113.2 collapsed the
  former `.pql-notebook-chat-drawer` into one tabbed right-edge
  drawer; the **Chat** tab inside the drawer is auto-selected).
- Status label reads `connected`.
- Empty message list.

### 2. Propose a new cell

1. Click the chat textarea.
2. Type: `Add a code cell at the end that prints df.describe().`
3. Press **Enter**.

Expected sequence:
- User message renders immediately.
- Status pill flips to `thinking…`, then briefly `calling tool…`
  when the LLM calls `pql_propose_cell`.
- An **Insert / Discard** banner appears in the drawer with the
  proposed source (`print(df.describe())`) + rationale.

3. Click **Insert** (`data-testid="cell-propose-insert"`).

Expected:
- A new cell appears at the end of the notebook with the proposed
  source.
- A small "from chat" affordance marks the cell until the next
  save (`_proposalPending`).
- The chat banner disappears.

4. Click **Save** (or press ⌘S).

Expected:
- Save round-trip succeeds.
- The new cell receives a stable `cell_uuid` (visible in the
  cell's `data-cell-uuid` attribute if you inspect via DevTools).
- `notebook_cell_provenance` now contains one row with
  `action='propose'`, the chat session's `agent_run_id`, and
  the cell's new UUID.  (Verify via
  `psql -c "select cell_uuid, action, agent_run_id from
  notebook_cell_provenance order by created_at desc limit 5"` or
  the equivalent SQLite query.)

### 3. Fix the failing cell

1. Run the second seed cell (`df["events"].mean(typo_kwarg=True)`)
   — it raises a `TypeError`.
2. Open the chat drawer (if closed) and type:
   `The last cell errors with "unexpected keyword argument";
   fix it to just compute the mean.`
3. Press **Enter**.

Expected sequence:
- LLM calls `pql_fix_cell` with the failing cell's UUID.
- An **Apply / Discard** banner appears with the diff-style
  source preview (`df["events"].mean()`).

4. Click **Apply** (`data-testid="cell-fix-apply"`).

Expected:
- The cell's CodeMirror editor updates to the fixed source.
- The cell is marked dirty.
- The chat banner disappears.

5. Save the notebook.  Re-run the cell — the error is gone.

6. Verify: `notebook_cell_provenance` now has a second row with
   `action='fix'`, same `cell_uuid` as the targeted cell, same
   `agent_run_id`.

### 4. Attach an explanation

1. In the chat drawer, type:
   `Explain what the dataframe in the first code cell represents.`
2. Press **Enter**.

Expected sequence:
- LLM calls `pql_explain_cell` with the cell's UUID and the
  explanation text.
- A small inline note appears in the chat drawer (NOT a banner
  with an Accept button — explanations auto-accept).
- The note has a "Pinned to cell …{uuid suffix}" label.

3. In the notebook, click the 💬 chip on the first code cell
   to open the per-cell social drawer.
4. Scroll to the **AI Explanations** section.

Expected:
- The explanation appears as a bordered card with the agent run
  ID prefix + timestamp.
- Discarding the inline note in the chat drawer (the small ×
  button) flips the proposal's status to `discarded` and the
  explanation disappears from the cell drawer on next open.

### 5. (Optional) Reload + provenance survives

1. Reload the page (`Cmd/Ctrl+R`).
2. Re-open the cells affected by steps 2-4 and confirm:
   - The inserted cell from step 2 is still there with its
     stable UUID.
   - The fixed cell in step 3 still shows the corrected source.
   - The explanation in step 4 still renders in the cell's
     social drawer Explanations tab.

This proves provenance + cell identity survive reloads — the
cell-reconciliation pass + the append-only
`notebook_cell_provenance` table hold the chain across saves.

## Backend assertion script (optional)

A short sanity-check you can run from a separate terminal to
confirm provenance was written:

```sql
SELECT
  p.action,
  p.cell_uuid,
  p.agent_run_id,
  p.created_at,
  np.action AS proposal_action,
  np.rationale
FROM notebook_cell_provenance p
JOIN notebook_cell_proposals np ON np.proposal_id = p.proposal_id
ORDER BY p.created_at DESC
LIMIT 10;
```

You should see three rows for the steps above —
`propose`, `fix`, `explain` — all keyed on the same
`agent_run_id` (one chat session = one agent run).

## Replaying via Playwright MCP

Use `mcp__playwright__browser_*` with `--browser firefox` (see
`README.md`).  Targets:

- `data-testid="notebook-chat-toggle"` — toolbar AI button.
- `data-testid="notebook-chat-send"` — send button in the
  drawer footer.
- `data-testid="cell-propose-insert"` — Insert button on a
  propose banner.
- `data-testid="cell-fix-apply"` — Apply button on a fix
  banner.
