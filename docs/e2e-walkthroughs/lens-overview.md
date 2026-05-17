# Lens overview walkthrough

> **Mode:** `browser` · **Phase:** 65 · **Surface:** /lens chat-style Q&A

End-to-end exercise of the new Lens read-only Q&A surface (Phase 65.5):
admin sets up a BYO LLM-provider key, an analyst opens a chat
session, asks a question that triggers a tool call, pins the answer,
and re-opens the pinned page.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- An Anthropic (or OpenAI) API key on the operator's clipboard.
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in).

## Walkthrough

### Part A — Admin: configure BYO LLM provider (4 steps)

1. **Navigate to the Lens-providers admin page**.
   - Action: log in as `admin@pql.test`, navigate to
     `http://127.0.0.1:8000/admin/lens-providers` (the JSON CRUD;
     a polished UI is a follow-up).
   - Assert: the page returns either an empty `{"providers": []}`
     list or a previously-stored row.

2. **Upsert the Anthropic credential** via the JSON CRUD.
   - Action:
     ```bash
     curl -X POST http://127.0.0.1:8000/api/admin/lens-providers \
       -H 'Content-Type: application/json' \
       -b cookies.txt \
       -d '{"provider":"anthropic","api_key":"sk-ant-...","default_model":"claude-haiku-4-5-20251001"}'
     ```
   - Assert: `200 OK`, response body carries `provider:"anthropic"`
     and **does NOT** include the cleartext key (`api_key_encrypted`
     is the only stored form).

3. **Verify the credential decrypts**.
   - Action:
     `curl -X POST -b cookies.txt http://127.0.0.1:8000/api/admin/lens-providers/anthropic/test`
   - Assert: `{"ok": true, "key_prefix": "sk-ant-x"}`.

4. **List provider keys**.
   - Action: `curl -b cookies.txt http://127.0.0.1:8000/api/admin/lens-providers`
   - Assert: one row for `anthropic`, `enabled=true`, no cleartext.

### Part B — Analyst: open Lens, ask a question, observe tool call (5 steps)

5. **Navigate to /lens**.
   - Action: `browser_navigate('http://127.0.0.1:8000/lens')`.
   - Assert: page title `Lens · PointlesSQL`. Heading reads
     "Lens" with the `bi-eye` icon. Empty session-list shows the
     "No sessions yet" hint.

6. **Click "New session"** and accept the prompted title.
   - Action: `browser_click(role="button", name="New session")`,
     enter "First analysis" in the title prompt.
   - Assert: a new row appears in the session list highlighted
     active; the chat panel becomes visible with an input box.

7. **Ask a tool-driven question**.
   - Action: type "How many catalogs are there?" into the input
     and click Send.
   - Assert (after 5–10s): the chat panel grows three new rows in
     order: `user` → `tool` (one with `tool_name=list_catalogs` or
     `tool_name=query` depending on which path the LLM picks) →
     `assistant`. The assistant text references a number.

8. **Inspect the persisted transcript via the API**.
   - Action: `curl -b cookies.txt
     http://127.0.0.1:8000/api/lens/sessions/1/messages`
   - Assert: at least one row with `role=tool, tool_status=ok`;
     one `role=assistant` carrying the answer text.

9. **Run a follow-up question** that exercises provenance.
   - Action: type "Where does this catalog count come from?" and
     send.
   - Assert: another tool call lands; the assistant text references
     the source table or `provenance` shape.

### Part C — Pin + re-render (3 steps)

10. **Pin the assistant answer**.
    - Action: take the assistant message id from
      `/api/lens/sessions/1/messages` and POST it:
      ```bash
      curl -X POST http://127.0.0.1:8000/api/lens/pinned \
        -H 'Content-Type: application/json' -b cookies.txt \
        -d '{"title":"Catalog count","source_message_id":<msg_id>}'
      ```
    - Assert: 201, response carries `slug:"catalog-count"`.

11. **Open the pinned-answer standalone page**.
    - Action: `browser_navigate('http://127.0.0.1:8000/api/lens/pinned/catalog-count/view')`.
    - Assert: page title contains "Catalog count". The Answer card
      shows the snapshot text. The "Back to Lens" button is
      present.

12. **List pins via the JSON API**.
    - Action: `curl -b cookies.txt http://127.0.0.1:8000/api/lens/pinned`
    - Assert: at least one entry with the expected slug.

## Coverage

* `/lens` chat surface — session list, new-session flow, message
  thread, tool-call rendering.
* `/api/admin/lens-providers` — Fernet-encrypted upsert + test
  decrypt + list.
* `/api/lens/{sessions,messages,pinned}` end-to-end with at least
  one tool call.
* Pinned-answer standalone view.
