# End-to-end walkthroughs

Deterministic, step-for-step UI walkthroughs that exercise every
HTML route, every interactive Alpine component, and every
UI-relevant setting of PointlesSQL against a freshly-composed
stack. Each walkthrough lives in its own Markdown playbook and
can be replayed by either:

- **A human** with a browser and a text editor, or
- **Claude Code** in an MCP-enabled session using the
  `mcp__playwright__browser_*` tool family.

Phase 7 of [`ROADMAP.md`](../../ROADMAP.md) explains the
motivation: unit and integration tests have never instantiated
the rendered templates — commit `e09a661` (the job-pause form
landing on a raw JSON page) is the kind of bug only a live
browser surfaces.

Sprint 22 delivers the harness plus the **data-surface**
playbooks. Sprint 23 will add **orchestration + operational**
playbooks (jobs, notebook, OIDC, `/metrics`, config matrix) on
top of the same harness.

## Playbooks

Run them in this order — the later ones reuse users and
catalogs created by the earlier ones:

1. [`auth.md`](auth.md) — register the first-user admin, then a
   non-admin user, log in and out, cover redirect-to-login and
   the `/403` gate on `/metrics`.
2. [`catalog-browsing.md`](catalog-browsing.md) — navigate the
   catalog/schema/table detail pages, exercise the sidebar tree
   and its sessionStorage persistence, copy the PQL snippet.
3. [`inline-editors.md`](inline-editors.md) — drive every
   inline-edit component (`editable`, `properties_editor`,
   `tags_editor`, `permissions_card` grant/revoke + Assigned /
   Effective tabs, `lineage_card`).
4. [`federation.md`](federation.md) — admin CRUD of connections,
   external locations, credentials (list + detail + create modal
   + `deleteConfirm`), plus a non-admin negative pass.
5. [`foreign-catalog-sync.md`](foreign-catalog-sync.md) — create
   a foreign catalog via the modal on `/`, run "Sync now",
   confirm the sync-history card and mirrored schemas/tables.

## Stack start

```bash
# from repo root
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
# wait for health: `docker compose ps` should show both PointlesSQL
# and soyuz-catalog "(healthy)" plus postgres-e2e "(healthy)"
docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
```

Seed runs **inside the PointlesSQL container** because
soyuz-catalog stores absolute `file://` URIs as storage roots —
running seed server-side means the registered paths match the
container's view of `/app/warehouse` and stay valid for any
subsequent notebook or scheduler access. The overlay mounts
`./scripts:/app/scripts:ro` so the script is available without
a rebuild.

The seed script is idempotent — re-running is safe and turns
into a no-op once the demo catalog, schemas, tables, and
Postgres Connection exist.

If the cached `pointlessql-pointlessql` image predates Sprint
11 (when `pyarrow` was added to the main deps), rebuild before
first seed:

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
    build pointlessql
docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
    up -d --force-recreate pointlessql
```

## Test users

The playbooks create and then reuse the following accounts:

| Email              | Password   | Role  | Created in        |
| ------------------ | ---------- | ----- | ----------------- |
| `admin@pql.test`   | `Passw0rd!` | admin | `auth.md` step 1 |
| `user@pql.test`    | `Passw0rd!` | user  | `auth.md` step 3 |

The first-registered account is auto-promoted to admin by
PointlesSQL's first-user bootstrap (see
`pointlessql/services/auth.py`), so `auth.md` always runs first
against a **clean metadata DB**. To reset:

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml down -v
```

`down -v` removes the volumes (including the metadata DB and
the Delta warehouse), so the next `up -d` starts with no users.

## How to replay a playbook

Every playbook has three sections:

- **Preconditions** — which previous playbooks must have run,
  and any environment assumptions.
- **Walkthrough** — numbered steps. Each step names the intent,
  the action to take (MCP tool call or equivalent browser
  interaction), and the assertion that confirms the step worked.
- **Found bugs** — problems surfaced in a live run. Either
  fixed in the same sprint commit (with a short-SHA link) or
  left as a `BUG-22-NN` TODO with a clear next action. No
  "something was weird" entries (per
  [`ROADMAP.md`](../../ROADMAP.md) Phase 7 prelude).

### Human replay

Open the playbook, follow the numbered steps in a browser
pointed at `http://127.0.0.1:8000`. Each step's **Assert** line
describes what you should see on the rendered page.

### Claude / Playwright MCP replay

In a Claude Code session with the Playwright MCP server
configured, ask the model to "replay playbook `<name>`" and it
will walk the numbered steps using `browser_navigate`,
`browser_click`, `browser_fill_form`, `browser_snapshot`,
`browser_wait_for`, `browser_evaluate`, and
`browser_network_requests`. The playbooks reference MCP tool
names directly in each step so the model can map from intent to
tool call.

## Selector conventions

Templates intentionally do **not** carry `data-test`
attributes. Playbook steps use, in order of preference:

1. **Visible text** — `getByRole('button', {name: /Save/})`,
   `getByText('Create foreign catalog')`
2. **ARIA labels** or form `label for=`
3. **Placeholder text** — `getByPlaceholder('key')`
4. **Modal ID** — `#createForeignCatalogModal`,
   `#createConnectionModal`
5. **Alpine state** inspected via `browser_evaluate` — check
   `x-show`, `x-text`, or `sessionStorage` keys directly when
   the DOM selector alone would be ambiguous.

## Teardown

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml down -v
```

`-v` wipes volumes so the next run starts from a known clean
state. Leave the volumes in place between playbook runs inside
a single walk-through session — they share seeded data.
