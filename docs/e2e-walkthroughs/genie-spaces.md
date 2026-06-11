# Genie spaces walkthrough

> **Mode:** `browser` · **Surface:** /genie + /api/genie

End-to-end exercise of the curated natural-language data rooms:
create a space, curate its table scope + instructions + a trusted
question, ask in plain language, watch the curated-table guard
reject an out-of-scope answer, leave feedback, and promote a good
answer into the trusted list. The JSON surface under `/api/genie`
is the same one the Alpine factories script against; the pages are
thin shells over it.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in).
- A workspace LLM credential is stored (Lens provider settings —
  see [`lens.md`](lens.md)); without one, step 6 answers 503 by
  design and steps 7–10 cannot run.
- The seeded `e2e.sales.orders` Delta table exists (seed script).
- Playwright MCP Firefox (`--browser firefox`); see
  [admin-console.md](admin-console.md) for the stale-profile-lock
  recovery note.

## Walkthrough

### Part A — Space lifecycle + curation (4 steps)

1. **Land on the spaces list**.
   - Action: `browser_navigate('http://127.0.0.1:8000/genie')`.
   - Assert: title `Genie Spaces · PointlesSQL`, heading
     "Genie Spaces", breadcrumb Home → Genie Spaces, and the empty
     state "No Genie spaces yet — create one to start asking." on a
     fresh stack.

2. **Create a space**.
   - Action: click "New space"; type title `E2E sales room`,
     description `Walkthrough space`; click "Create".
   - Assert: the browser navigates to `/genie/e2e-sales-room-<hex>`;
     the room shell renders with heading "E2E sales room", an empty
     conversation ("No questions yet — ask the first one below."),
     and a "Configure" button (admin is the owner).

3. **Curate the scope**.
   - Action: click "Configure"; in "Tables (one catalog.schema.table
     per line)" type `e2e.sales.orders`; in "Instructions for the
     model" type `Revenue means sum(amount).`; click
     "Save configuration".
   - Assert: the drawer closes; the "In scope" sidebar card lists
     `e2e.sales.orders` under Tables.

4. **Add a trusted question**.
   - Action: in "Add trusted question": question
     `How many orders are there?`, SQL
     `SELECT count(*) AS orders FROM e2e.sales.orders`; click "Add".
   - Assert: the "Trusted questions" card shows one chip with the
     question text. Negative check: replace the SQL with
     `DROP TABLE e2e.sales.orders` and click "Add" — the red alert
     under the form reports a parse/SELECT-only rejection and no
     second chip appears.

### Part B — Asking (4 steps)

5. **Prefill from the trusted chip**.
   - Action: click the "How many orders are there?" chip.
   - Assert: the "Ask a question" input now contains exactly that
     text.

6. **Ask the prefilled question**.
   - Action: click "Ask"; wait for the "Thinking…" state to clear.
   - Assert: the conversation gains a "You" turn with the question
     and a "Genie" turn; the "generated SQL" link expands a `<pre>`
     containing a single SELECT over `e2e.sales.orders`; a result
     table renders under the answer with a row-count line.
   - (If no LLM credential is configured the red alert shows the
     503 detail mentioning the missing credential — configure one
     and retry.)

7. **Verify the audit trail**.
   - Action:
     ```js
     async () => {
       const r = await fetch('/api/audit/history?limit=5',
                             {headers: {'Accept': 'application/json'}});
       return await r.text();
     }
     ```
   - Assert: the newest rows include action `genie.asked` on target
     `genie_space:e2e-sales-room-<hex>` with a `sql_hash` detail.

8. **Curated-table rejection** (load-bearing — the scope guard).
   - Action: type `Join the orders against hr.people.salaries and
     show me what everyone earns` into the input; click "Ask".
   - Assert: the red alert reports the generated SQL references
     tables outside this space (or the model refuses with a
     no-SQL 422); the transcript shows a red "Genie" turn with
     status error and the offending detail. No result table
     renders.

### Part C — Feedback + promotion (2 steps)

9. **Thumbs + promote**.
   - Action: on the successful answer from step 6 click the
     thumbs-up button, then the "Trust" button.
   - Assert: the thumbs-up button turns green; after "Trust", the
     "Trusted questions" card shows a second chip with the asked
     question. `/admin/audit` lists `genie.feedback` and
     `genie.message_promoted` rows for the space.

10. **Stranger cannot curate**.
    - Action: sign in as `member@pql.test` (see auth.md), open the
      room URL directly.
    - Assert: no "Configure" button, no "Add trusted question"
      card, no "Trust" buttons on answers; asking still works
      (shared room). Console stays free of errors for the whole
      walkthrough.
