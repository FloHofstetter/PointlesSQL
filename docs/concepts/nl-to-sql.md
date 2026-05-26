# NL → SQL chat panel

Phase 91 ships the [`hermes-agent`](https://github.com/FloHofstetter/hermes-agent) –
powered chat drawer in the SQL editor: a side panel that turns
natural-language questions into either capped SELECT results or
human-reviewed DML/DDL drafts.  The drawer never executes
destructive SQL silently — every non-SELECT statement is fenced
behind a "Run / Discard" banner the human must click.

This page is the conceptual companion to
[Agent memory](agent-memory.md) — Phase 90 shipped the storage
side (what agents remember), Phase 91 ships the *speak* side
(how a human asks).  Together they form the agent-native lakehouse
loop: ask in the chat, the agent's tool-calls land on its memory
timeline, branches off the conversation become real Delta branches.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Browser (SQL editor)                                              │
│   * sqlEditor()  — CodeMirror + run/explain/save                  │
│   * chatPanel()  — WebSocket /ws/sql/chat/{editor_session_id}     │
│        ↓                                                          │
└──────────────────────────────────────────────────────────────────┘
                 │ WebSocket frames (JSON-RPC envelope)
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ PointlesSQL FastAPI                                              │
│   pointlessql/api/sql_chat_ws.py                                 │
│     • cookie / Bearer auth on upgrade                            │
│     • load_or_create EditorChatSession (1:1 agent_run)           │
│     • per-turn: run_in_executor(hermes_agent.AIAgent.run_conv…)  │
│       └─ stream_delta_callback bridges tokens → broker → WS      │
│                                                                  │
│   pointlessql/services/editor_chat/                                 │
│     • _session.py  — load/create, append messages, claim/release │
│     • _turn.py     — orchestrate AIAgent + cancel-event          │
│     • _broker.py   — fan-out frames to the per-session WS queue  │
│     • _agent_factory.py — instantiate hermes_agent.AIAgent       │
└──────────────────────────────────────────────────────────────────┘
                 │ in-process tool calls via hermes-plugin-pointlessql
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ Plugin tools (Family A unless gated):                            │
│   pql_list_tables, pql_describe_columns_with_stats, pql_explain, │
│   pql_query (executes capped SELECT), pql_save_query,            │
│   pql_propose_sql (drafts DML/DDL — never executes itself)       │
└──────────────────────────────────────────────────────────────────┘
```

Every tool call ships an ``X-Agent-Run-Id`` header tied to the
chat session's agent_run.  The `/memory/<agent-id>` page from
Phase 90 surfaces that trace as a memory timeline — there is no
separate "chat history" view to maintain.

## The DML/DDL gate

`pql_query` auto-executes SELECT statements with the existing
10 000-row cap and EXPLAIN-first cost gate.  Non-SELECT must go
through `pql_propose_sql` — a tool that, instead of running the
SQL, drops a row into a ``chat_proposals`` table and fan-outs a
``proposal_created`` event over the chat session's WebSocket.
The drawer renders the draft as a banner with **Load in editor**
and **Discard** buttons.

When the human clicks "Load in editor":

1. The client POSTs ``/api/sql/chat/proposals/{id}/accept``.
2. The server marks the row ``status="accepted"`` (or
   ``"expired"`` when older than 24 hours) and returns the SQL
   plus the chat session's ``agent_run_id``.
3. The drawer loads the SQL into the CodeMirror buffer and the
   editor's normal **Run** button now sends
   ``X-Agent-Run-Id: <chat_run_id>``.
4. The existing ``/api/sql/execute`` dispatcher records the
   operation row against the chat run, so the operation appears
   in the memory timeline next to every other tool-call from the
   conversation.

The split is deliberate: `pql_query` is a read-tool the LLM can
use freely; `pql_propose_sql` is the only write-path and it
always involves human review.

## The refinement loop

When a SELECT returns 0 rows or fails, the drawer surfaces a
**Refine** button.  Clicking it sends a ``refine`` frame with
the prior SQL + the failure mode (``zero_rows`` or ``error``) —
the server templates a structured user-message and runs a normal
turn on the same conversation.  Each refine appends to the same
``conversation_json`` so the memory timeline shows the whole
back-and-forth.

## Configuration

| Setting | Default | Purpose |
|---|---|---|
| `POINTLESSQL_EDITOR_CHAT_ENABLED` | `true` | Hide the chat toggle + reject WS upgrades when `false`. |
| `POINTLESSQL_EDITOR_CHAT_DEFAULT_MODEL` | `claude-haiku-4-5-20251001` | Model the in-process `AIAgent` uses. |
| `POINTLESSQL_EDITOR_CHAT_PROVIDER` | empty (auto-detect) | Override the provider when the model id doesn't disambiguate. |
| `POINTLESSQL_EDITOR_CHAT_BASE_URL` | empty | Override the provider's base URL (e.g. local Ollama). |
| `POINTLESSQL_EDITOR_CHAT_MAX_TURNS_PER_SESSION` | `20` | Hard cap before the WS layer asks the user to reset. |
| `POINTLESSQL_EDITOR_CHAT_EXECUTOR_WORKERS` | `2` | Threads dedicated to in-flight turns. |

`hermes-agent` reads provider credentials from the standard env
vars (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, …).  When none
is set, the WS closes with code 1011 + reason
``LLM_NOT_CONFIGURED`` so the drawer can show a deterministic
"Set up an LLM provider" error rather than a cryptic SDK trace.

## Files

| File | Role |
|---|---|
| [`pointlessql/api/sql_chat_ws.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/sql_chat_ws.py) | WebSocket route `/ws/sql/chat/{editor_session_id}` |
| [`pointlessql/api/sql_chat_routes/`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/sql_chat_routes/) | `POST .../propose`, `.../accept`, `.../discard` |
| [`pointlessql/services/editor_chat/`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/editor_chat/) | Session lifecycle + turn orchestration + broker |
| [`pointlessql/services/column_stats/`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/column_stats/) | Live PQL→pandas reduction for `pql_describe_columns_with_stats` |
| [`frontend/templates/pages/_partials/sql_editor/chat_drawer.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/_partials/sql_editor/chat_drawer.html) | Right-side drawer markup |
| [`frontend/js/sql_editor/chat.js`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/sql_editor/chat.js) | `chatPanel()` Alpine factory + WebSocket client |

## Where to read next

- [Agent memory](agent-memory.md) — Phase 90 storage side
- [Agent supervision](agent-supervision.md) — three privilege
  families that decide which tools each session sees
- [SQL chat walkthrough](../e2e-walkthroughs/sql-chat.md) —
  Playwright playbook covering the full flow
