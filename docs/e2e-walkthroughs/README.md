# End-to-end walkthroughs

Deterministic, step-for-step UI walkthroughs that exercise every
HTML route, every interactive Alpine component, and every
UI-relevant setting of PointlesSQL against a freshly-composed
stack. Each walkthrough lives in its own Markdown playbook and
can be replayed by either:

- **A human** with a browser and a text editor, or
- **Claude Code** in an MCP-enabled session using the
 `mcp__playwright__browser_*` tool family.

 of [`ROADMAP.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/ROADMAP.md) explains the
motivation: unit and integration tests have never instantiated
the rendered templates — commit `e09a661` (the job-pause form
landing on a raw JSON page) is the kind of bug only a live
browser surfaces.

 delivered the harness plus the five **data-surface**
playbooks. adds five **orchestration + operational**
playbooks on top of the same harness (jobs, notebook, OIDC,
`/metrics`, config matrix) — closing.

## Playbooks

**Tour-level entry-point.** If you are new to the project, start here —
it visits every major UI surface in one ~30-minute click-through and
cross-links to the deep-dive playbooks below for the edge cases:

0. [`grand-tour.md`](grand-tour.md) — single coherent journey through
 the catalog, lineage (incl. the row / column / value
 axes), SQL editor, jobs, run-detail, ML Registry with the
 bidirectional inference DAG, branches, dashboards, alerts (incl.
 the Atom feed), audit cockpit, federation, volumes, and the
 responsive + theme toggles. Self-bootstraps via
 `seed-full-stack-demo.py --fresh --demo-rollback --keep-state`.

**Data-surface**. Run these first, in order — later
ones reuse users and catalogs created by earlier ones:

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

**Orchestration + operational**. Each one assumes the
data-surface playbooks have run at least once:

6. [`jobs-dag.md`](jobs-dag.md) — single-task + DAG job creation,
 Run-now, retry + fail-skip propagation, Pause/Resume, per-task
 log panel, and a `pg_sync`-kind cross-feature smoke against
 `pg_mirror`.
7. [`notebook-editor.md`](notebook-editor.md) — native
 editor end-to-end: open + autosave, cell execute + output
 persistence across reload, kernel restart, Pyright LSP
 (completion / hover / diagnostics), Variable Explorer,
 Insert-from-catalog modal, and the post-retirement surfaces
 that prove the JupyterLab iframe is really gone. Replaced
 the `notebook.md` playbook when the
 iframe retired.
8. [`oidc.md`](oidc.md) — OIDC-off (SSO button absent) then
 OIDC-on via the `mock-oidc` sidecar; full authorize-code + PKCE
 round-trip with auto-user-creation and claim mapping.
9. [`operational.md`](operational.md) — public `/healthz`, admin
 `/metrics`, non-admin `/403`, JSON-error envelope, and the
 `X-Request-ID` generate-and-forward middleware contract.
10. [`config-matrix.md`](config-matrix.md) — one primary golden
 path (`engine=pandas, log=text, db=sqlite`) plus five delta
 walks for every non-default value of `POINTLESSQL_DELTA_ENGINE`,
 `POINTLESSQL_LOG_FORMAT`, and `POINTLESSQL_DB_URL`.

**Packaging**. Validates the GHCR-pull install path —
the one install flavour that cannot be run from a source checkout
at all. Runs on its own, no dependency on the harness above:

11. [`packaging.md`](packaging.md) — clean-machine flow: `docker
 login ghcr.io`, download the compose file at a tag, flip
 `build:` → `image:`, `docker compose pull && up`, home page
 renders, OCI labels verified on the pulled images.

**Agent supervision**. Exercises the registry +
CloudEvents + control-room surface end-to-end through an
external runtime that pretends to be Hermes:

12. [`agent_drift_monitor.md`](agent_drift_monitor.md) —
 demo. Registers an agent run via
 `POST /api/agent-runs`, runs the
 [`notebooks/agent_drift_monitor.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/notebooks/agent_drift_monitor.py)
 notebook (freshness + null-rate + value-drift checks),
 appends results to `ops.quality_history`, fires a
 CloudEvent on threshold breach, drills into `/runs/{id}`
 in Firefox to verify the conformance card + audit log +
 tables-touched chips, all attributed to the
 `X-Principal`-forwarded identity.

13. [`hermes_medallion.md`](hermes_medallion.md) —
 the **done moment**. A real
 Hermes session (with `hermes-plugin-pointlessql` loaded)
 autoloads
 [`notebooks/hermes_medallion_data/orders.csv`](https://github.com/FloHofstetter/PointlesSQL/blob/main/notebooks/hermes_medallion_data/orders.csv)
 into `main.bronze.orders_raw`, upserts into
 `main.silver.orders`, aggregates into
 `main.gold.orders_summary`, and the run-detail view shows
 Source + Operations + Tool calls + Queries + Conformance
 tabs all populated. Agent-authored Medallion lakehouse
 in one playbook.

**Delta-Branching**. Exercises the zero-copy branch
primitives end-to-end:

14. [`branches.md`](branches.md) — closing replay.
 Notebook + browser combo: ``pql.branch`` → write to branch →
 prove parent untouched → preview-promote → break it with a
 competing parent write → discard → re-branch → clean
 promote. Covers the symlink-strategy storage layout,
 conflict-detection, audit-log entries, and the three new
 `pointlessql.branch.*` CloudEvents. Local FS only —
 cloud-storage discard / promote is documented out-of-scope
 for v1.

**ML registry**. Replay these after the
audit-foundation lifespan-config is in place
(`POINTLESSQL_MLFLOW_ENABLED=1`) and at least one trained
model lives in soyuz:

15. [`models-tab.md`](models-tab.md) — browse +
 compare-view replay.
16. [`models-promotion.md`](models-promotion.md) —
 promote a challenger to champion through the modal,
 confirm marker on soyuz + `agent_reviews` row +
 `pointlessql.model.promoted` envelope.
17. [`inference-lineage.md`](inference-lineage.md) —
 `pql.write_table(..., source_model_uri=...)` writes inference
 edges, the model-detail Lineage tab paints both the
 upstream (`trained_from`) and downstream (`inferred_to`)
 halves of the bidirectional DAG, the Predictions card
 surfaces the target-table edge counts.
18. [`agent-ml-registry.md`](agent-ml-registry.md) —
 cross-repo closure. An agent connected through
 `hermes-plugin-pointlessql` exercises the eight new ML-
 Registry tools end-to-end (browse → log-training → write
 inference → promote) — fully HTTP-only, no PointlesSQL
 imports on the agent side.

**Phase 37 — admin + audit cockpit + dbt**.  Five new
playbooks (one rewritten + four new) closing coverage gaps
that opened in Phase 14, 17, 18.6+, 28, 33, and 36.  Replay
them after `auth.md` (admin user must exist + be signed in):

19. [`admin-console.md`](admin-console.md) — Phase-33
 admin landing 7-card grid + ``/admin/external-writes``
 (Phase 14) + ``/admin/api-keys`` (with the plaintext-
 secret modal + load-bearing
 secret-not-in-outerHTML assertion) + ``/admin/review-
 destinations`` + ``/admin/system-info``.  ``/admin/audit-
 sinks`` and ``/admin/workspaces`` cross-link out to the
 dedicated playbooks.
20. [`audit-cockpit-deep.md`](audit-cockpit-deep.md) — the
 four Phase-18.6 → 18.x cockpit pages: anomaly inbox +
 FTS search (Sprint 18.7's custom path-segment tokenizer
 verified) + by-table reverse index +
 saved audit queries workbench.  Distinguishes "chrome"
 path (works on ``seed-e2e.py``) from "data" path (needs
 ``seed-full-stack-demo.py --demo-rollback --keep-state``).
21. [`run-comparisons.md`](run-comparisons.md) — both
 compare surfaces in one playbook: the structured 6-tab
 audit run-diff at ``/runs/{a}/diff/{b}`` (Sprint 18.4)
 with Chart.js bars + the side-by-side jobs run-compare
 at ``/jobs/{job_id}/runs/{a}/compare?with={b}``
 (Sprint 12.x).  Carries the Phase-18 prior-art mitigation
 for Chart.js async render against hidden tab-panes.
22. [`alerts.md`](alerts.md) — alert list + detail +
 destination CRUD with HMAC redaction + the per-user
 ``/alerts/feed.atom`` + ``/alerts/feed.json`` pull feed
 URLs.  Cross-link in from grand-tour Act 9.
23. [`dbt-pipeline.md`](dbt-pipeline.md) — Phase-36 dbt
 cockpit at ``/dbt`` covering both states (iframe to
 ``/dbt-docs/`` + warning card when subprocess is
 down).  The Phase-36.B read-only API surface
 (``/api/dbt/manifest``, ``/coverage``, ``/test-failures``)
 is exercised programmatically pending the still-paused
 Phase-36.4 chrome work (filed as BUG-37-06).

[`audit-sinks.md`](audit-sinks.md) was rewritten from a
curl-only operational runbook into a UI-driven walkthrough
during Phase-37 Wave 0a — the original "no UI yet" caveat is
gone.  Wave 0a also surfaced BUG-37-01 (Alpine ``x-data``
attribute escaping on four admin row templates), fixed in
``a744b52``.

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

## Host env overlays

The `docker-compose.e2e.yml` overlay exposes a handful of
`${…:-default}` env passthroughs so a playbook can flip a single
knob without editing the file. All are off/default unless the host
exports the override:

| Host env var | Default | Used by |
| ----------------------------------- | ------- | -------------------- |
| `POINTLESSQL_SCHEDULER_TICK_SECONDS`| `2` | `jobs-dag.md` |
| `POINTLESSQL_JUPYTER_ENABLED` | `true` | ( no-op; kept for backward-compat) |
| `POINTLESSQL_LOG_FORMAT` | `text` | `config-matrix.md` |
| `POINTLESSQL_DELTA_ENGINE` | `pandas`| `config-matrix.md` |
| `POINTLESSQL_OIDC_DISCOVERY_URL` | (empty) | `oidc.md` Pass 2 |
| `POINTLESSQL_OIDC_CLIENT_ID` | (empty) | `oidc.md` Pass 2 |
| `POINTLESSQL_OIDC_CLIENT_SECRET` | (empty) | `oidc.md` Pass 2 |
| `POINTLESSQL_SERVER_BASE_URL` | (empty) | `oidc.md` Pass 2 |

** note:** ``POINTLESSQL_ENGINE`` and ``POINTLESSQL_BASE_URL``
were renamed to ``POINTLESSQL_DELTA_ENGINE`` and
``POINTLESSQL_SERVER_BASE_URL`` when the flat :class:`Settings` moved
to nested sub-models. See ``CHANGELOG.md`` for the full mapping;
``config-matrix.md`` and ``oidc.md`` still document the old names
and will be refreshed on their next replay.

Flipping an override requires recreating the `pointlessql`
container so the new env reaches the uvicorn process:

```bash
POINTLESSQL_JUPYTER_ENABLED=false docker compose \
 -f docker-compose.yml -f docker-compose.e2e.yml \
 up -d --force-recreate pointlessql
```

The `mock-oidc` container is always running (idle < 80 MB). The
`oidc_enabled` computed property in `pointlessql/settings.py` only
returns `true` when both `POINTLESSQL_OIDC_DISCOVERY_URL` and
`POINTLESSQL_OIDC_CLIENT_ID` are set, so the other playbooks stay
unaffected.

## Test users

The playbooks create and then reuse the following accounts:

| Email | Password | Role | Created in |
| ------------------ | ---------- | ----- | ----------------- |
| `admin@pql.test` | `Passw0rd!` | admin | `auth.md` step 1 |
| `user@pql.test` | `Passw0rd!` | user | `auth.md` step 3 |

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
 [`ROADMAP.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/ROADMAP.md) prelude).

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
