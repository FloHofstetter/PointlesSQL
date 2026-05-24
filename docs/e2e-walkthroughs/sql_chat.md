# SQL chat walkthrough

Walks through the NL→SQL chat drawer end-to-end:
ask a SELECT question, propose a DML, accept the draft, then
refine a zero-rows turn.  Replays cleanly via Playwright (the
fake-LLM fixture lives in `tests/test_sql_chat_ws.py`); a
real-LLM replay needs an `ANTHROPIC_API_KEY` (or equivalent) in
the host env.

## Prerequisites

- A running PointlesSQL with `POINTLESSQL_EDITOR_CHAT_ENABLED=true`
  (the default).
- An LLM provider key in the env (else the WS closes with
  `LLM_NOT_CONFIGURED` — verified by step 0 below).
- An authenticated browser session (admin or non-admin both work
  — chat sessions are per-user).
- A non-empty Delta table reachable via UC; this playbook uses
  `main.silver.ingest` as a stand-in.

## Steps

### 0. (Optional sanity check) — LLM not configured

Open `/sql` while no provider env var is set.  Click the **Chat**
toggle in the editor header.  Expected: drawer slides in, status
pill reads "LLM not configured", an alert explains how to set
`ANTHROPIC_API_KEY`.  Set the key and reload — the rest of the
playbook resumes.

### 1. Open the chat drawer

1. Navigate to `/sql`.
2. Click the **Chat** button (`data-testid="sql-chat-toggle"`)
   in the header.
3. Wait for the drawer to open + the status pill to read
   `connected`.

Expected DOM:
- `.pql-chat-drawer` is visible.
- Status label shows `connected`.
- Empty message list (or restored history if a session id was
  cached in `sessionStorage`).

### 2. Ask a capped SELECT

1. Click the chat textarea (`.pql-chat-input`).
2. Type: `Show me the top 5 countries in main.silver.ingest by
   row count.`
3. Press **Enter** (or click the Send button —
   `data-testid="chat-send"`).

Expected sequence:
- User message appears immediately.
- Status pill flips to `thinking…`, then briefly to `calling
  tool…` when the LLM calls `pql_list_tables` /
  `pql_describe_columns_with_stats` / `pql_query`.
- Token frames stream into a streaming-assistant bubble; final
  assistant message replaces it.
- Memory page `/memory/sql-chat-<short>` shows the new
  operations in chronological order (open in a second tab to
  verify).

### 3. Ask for a write — propose flow

1. In the same drawer, type: `Delete the rows in
   main.silver.dupes where id < 10.`
2. Send.

Expected:
- The LLM emits a tool-call to `pql_propose_sql` (status pill
  briefly reads `calling tool…`).
- A yellow-bordered banner appears below the latest assistant
  message:
  - badge reads `DML`
  - pre-formatted SQL: `DELETE FROM main.silver.dupes WHERE id <
    10`
  - two buttons: **Load in editor**
    (`data-testid="propose-run"`) and **Discard**.

### 4. Accept the draft

1. Click **Load in editor**.
2. The drawer closes (or stays open, depending on tab focus);
   the CodeMirror buffer in the editor now shows the proposed
   SQL.
3. Click the editor's **Run** button.

Expected:
- `POST /api/sql/chat/proposals/{id}/accept` returns 200 with
  `agent_run_id` matching the chat session's run.
- `POST /api/sql/execute` runs with `X-Agent-Run-Id` set to that
  run id.
- The result card shows the operation summary (`DELETE … rows
  affected`).
- Open `/memory/<agent-id>`: the DELETE operation appears under
  the same agent run as the chat tool-calls.

### 5. Refine a zero-rows turn

1. Open the editor and type a SELECT that returns 0 rows, e.g.
   `SELECT * FROM main.silver.ingest WHERE country = 'ZZ'`.
2. Click **Run**.
3. In the chat drawer (which has access to `$root.result` and
   `$root.lastRun`), a yellow info banner appears: "Previous
   query returned 0 rows. Ask chat to refine".
4. Click the **Ask chat to refine** link
   (`data-testid="chat-refine-zero"`).

Expected:
- A synthetic user message appears: `(refine: zero_rows)`.
- The LLM redrafts the SQL (e.g. widening the WHERE clause), and
  drops a fresh `pql_propose_sql` banner.
- The original conversation history stays intact — the memory
  page now shows both the original + refined operations.

### 6. Reset + reconnect

1. Click the reset button (`<i class="bi bi-arrow-counterclockwise">`)
   in the drawer header.
2. The conversation goes empty; `conversation_json` in
   `editor_chat_sessions` is `[]` (verify via SQL).
3. Reload the tab — the chat drawer restores the (now-empty)
   session.

## Verifying programmatically

Headless replays exist in `tests/test_sql_chat_ws.py`,
`tests/test_sql_chat_propose_route.py`,
`tests/test_sql_chat_accept_proposal.py`, and
`tests/test_sql_chat_refine.py`.  The full suite runs in under
3 seconds because every WS-bound test uses `FakeAIAgent` rather
than spinning up a real LLM session.

## Known follow-ups

- **BUG-91-01**: when the editor session id changes (browser
  cleared `sessionStorage`), accepted proposals from the prior
  session orphan in `chat_proposals` until the 24-hour expiry
  sweep.  Fix would be a background scrubber.  Not blocking the
  walkthrough.
