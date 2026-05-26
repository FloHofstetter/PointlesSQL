# Navigation Information Architecture

**Status:** authoritative contract.  Every user-facing page in the
PointlesSQL frontend must have an entry in this document.  Future
audit bots verify that the set of routes returning HTML matches the
set of entries below.

This document was introduced in Phase 80 (the navigation/UX overhaul)
and supersedes the implicit IA carried in
[icon_rail.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/icon_rail.html)
and ad-hoc URL discovery.

## Chrome model

PointlesSQL uses **four chrome slots**.  No layout may add a fifth.

```
┌─────────────────────────────────────────────────────────────┐
│ TOP BAR — global ops (brand · search · quick-create ·       │
│           theme · workspace · bell · user)                   │
├──────────┬─────────────┬─────────────────────────────────────┤
│          │             │                                     │
│ PRIMARY  │  CONTEXT    │  MAIN CONTENT                       │
│ SIDEBAR  │  SIDEBAR    │  (page-level tabs allowed)          │
│ "Haupt-  │  "Neben-    │                                     │
│  rail"   │   panel"    │                                     │
│ 64 ↔ 220 │  240 px     │                                     │
│          │             │                                     │
├──────────┴─────────────┴─────────────────────────────────────┤
│ FOOTER — ambient status (workspace · backend health ·       │
│          help/keyboard hint)                                 │
└─────────────────────────────────────────────────────────────┘
```

* **Top bar** — persona-agnostic global operations.  Implementation:
  [base.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/base.html) lines 91–159 plus
  [workspace_switcher.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/workspace_switcher.html),
  [notification_bell.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/notification_bell.html),
  [user_menu.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/user_menu.html),
  and the Phase-80 additions
  `components/quick_create_menu.html`.
* **Primary sidebar** — five grouped intent-sections + admin footer.
  Expandable 64 px ↔ 220 px.  Implementation:
  `components/primary_rail.html` (renamed from `icon_rail.html` in
  Phase 80.1).
* **Context sidebar** — per-section secondary nav.  Implementation:
  [context_panel.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/context_panel.html)
  dispatching on `active_section`.
* **Footer** — ambient awareness strip, hidden on auth pages.
  Implementation: `components/footer_bar.html` (Phase 80.7).

## Primary sidebar — IA tree

Order: **supervisor-first** (Today + Feed at top; Watch second).
Locked in Phase 80 plan; do not re-order without product approval.

Group headers are non-clickable visual labels.  Each group's entries
share an `active_section` and surface a distinct context-panel
partial (see next section).

### HOME

| Label  | URL    | Template                      | Route handler                                              | Badge |
|---|---|---|---|---|
| Today  | `/`    | `pages/home.html`             | [home_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/home_routes.py)     | —     |
| Feed   | `/feed`| `pages/feed.html`             | [feed_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/feed_html_routes.py) | —   |

### WATCH (supervision)

| Label              | URL              | Template                       | Route handler                                                                | Badge                  |
|---|---|---|---|---|
| Agent runs         | `/runs`          | `pages/runs_list.html`         | [runs_routes/list_view.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/runs_routes/list_view.py)   | pending approvals      |
| Audit cockpit      | `/audit/inbox`   | `pages/audit_inbox.html`       | [audit/inbox.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/audit/inbox.py)                       | unread anomalies       |
| Alerts             | `/alerts`        | `pages/alerts.html`            | [alerts_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/alerts_routes.py)                   | firing                 |

### BUILD (authoring)

| Label              | URL                    | Template                       | Route handler                                                                       | Badge |
|---|---|---|---|---|
| SQL editor         | `/sql`                 | `pages/sql_editor.html`        | [sql/editor.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/sql/editor.py)                                | —     |
| Lens (Q&A)         | `/lens`                | `pages/lens.html`              | `pointlessql/api/lens_routes.py`                                                    | —     |
| Notebooks          | `/notebooks/workspace` | `pages/notebooks_workspace.html` | [notebooks_routes/pages.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/notebooks_routes/pages.py)      | —     |
| Dashboards         | `/dashboards`          | `pages/dashboards.html`        | [dashboards_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/dashboards_routes.py)                  | —     |
| Scheduled jobs     | `/jobs`                | `pages/jobs.html`              | [jobs_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/jobs_routes.py)                              | —     |
| dbt                | `/dbt`                 | `pages/dbt.html`               | [dbt/html.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/dbt/html.py)                                    | —     |

### DATA (browse + lineage)

| Label              | URL              | Template                       | Route handler                                                                | Notes                              |
|---|---|---|---|---|
| Catalog            | `/`              | `pages/home.html` + tree       | [catalog_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/catalog_html_routes.py)       | Shares URL with HOME → Today via `active_section` |
| Data products      | `/data-products` | `pages/data_products.html`     | [data_products_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/data_products_html_routes.py) | —                                  |
| ML models          | `/models`        | `pages/models.html`            | [models_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/models_html_routes.py)         | —                                  |
| MLflow tracking    | `/ml`            | `pages/mlflow.html`            | [mlflow_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/mlflow_html_routes.py)         | iframe wrapper                     |
| Delta branches     | `/branches`      | `pages/branches.html`          | `pointlessql/api/branches_routes.py`                                         | —                                  |
| Lineage explorer   | `/lineage`       | `pages/lineage_index.html`     | [lineage/views.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/lineage/views.py)                   | **NEW** (Phase 80.4)               |

### COMMUNITY (social)

| Label   | URL        | Template                     | Route handler                                                                | Notes                |
|---|---|---|---|---|
| Topics  | `/topics`  | `pages/topics_index.html`    | [topics_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/topics_html_routes.py)         | —                    |
| Issues  | `/issues`  | `pages/issues_index.html`    | [issues_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/issues_html_routes.py)         | —                    |
| People  | `/users`   | `pages/users_index.html`     | [users_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/users_html_routes.py)           | **NEW** (Phase 80.4) |
| Agents  | `/agents`  | `pages/agents_index.html`    | [agents_html_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/agents_html_routes.py)         | —                    |

### WORKSPACE

| Label              | URL                              | Template                          | Route handler                                                        | Gate            |
|---|---|---|---|---|
| Workspace home     | `/workspaces/<my-slug>`          | `pages/workspace_landing.html`    | [workspaces_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/workspaces_routes.py)   | member          |
| Members & settings | `/workspaces/<my-slug>/settings` | `pages/workspace_settings.html`   | [workspaces_routes.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/workspaces_routes.py)   | workspace admin |

### Rail footer

| Label              | URL              | Template                       | Route handler                                                        | Gate         |
|---|---|---|---|---|
| Admin              | `/admin`         | `pages/admin_index.html`       | [admin/console.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/admin/console.py)           | install admin |
| Help & shortcuts   | (modal)          | inside `command_palette.html`  | —                                                                    | —             |

## Context-panel partials

The context panel (right of the primary rail, 240 px) renders a
different partial per `active_section`.  Mapping carried by
[context_panel.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/context_panel.html);
section is derived in
[base.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/base.html) `_section_map`.

| `active_section`  | Partial                                                      | Content                                                                  |
|---|---|---|
| `home`            | `components/sidebars/home_sidebar.html`                      | Pinned · Approvals · Unread inbox · Recent runs                          |
| `feed`            | `components/sidebars/feed_sidebar.html`                      | Filter chips · Saved filters · RSS                                       |
| `runs`            | `components/sidebars/runs_sidebar.html`                      | Approvals · Running · Recent · Scheduled jobs · Agent reviews            |
| `audit`           | (inline in `context_panel.html`)                             | Inbox · Search · By table · By query                                     |
| `alerts`          | `components/sidebars/alerts_sidebar.html`                    | Enabled · Disabled                                                       |
| `sql`             | (inline in `context_panel.html`)                             | Editor · History · Saved · Lens shortcut                                 |
| `lens`            | `components/sidebars/lens_sidebar.html`                      | Saved questions · Recent answers · Suggested                             |
| `workspace`       | `components/sidebars/workspace_sidebar.html`                 | Notebook tree                                                            |
| `jobs`            | `components/sidebars/jobs_sidebar.html`                      | Active · Paused                                                          |
| `dashboards`      | `components/dashboards_sidebar.html`                         | Dashboard tree                                                           |
| `mlflow`          | `components/sidebars/mlflow_sidebar.html`                    | Recent UC models                                                         |
| `dbt`             | `components/sidebars/dbt_sidebar.html`                       | Recent dbt runs · Project list                                           |
| `federation`      | `components/sidebar.html` (catalog tree)                     | Catalog tree · Starred · Recent · Branches · Lineage shortcut            |
| `data_products`   | `components/sidebars/data_products_sidebar.html`             | Trending · Followed · Mine · Candidates                                  |
| `branches`        | `components/sidebars/branches_sidebar.html`                  | Active · Promoted · Discarded                                            |
| `lineage`         | `components/sidebars/lineage_sidebar.html`                   | Trace row · Trace column · Recent traces                                 |
| `topics`          | `components/sidebars/topics_sidebar.html`                    | Trending · Subscribed · All · Create                                     |
| `issues`          | `components/sidebars/issues_sidebar.html`                    | Open/Closed · Mine · Assigned · By label · Create                        |
| `people`          | `components/sidebars/people_sidebar.html`                    | All users · Agents · Online · Recently active                            |
| `agents`          | `components/sidebars/agents_sidebar.html`                    | All · Mine · Active runs · Failed today                                  |
| `workspace_home`  | `components/sidebars/workspace_home_sidebar.html`            | Pinned · Members · Activity · README                                     |
| `me`              | `components/sidebars/me_sidebar.html`                        | Profile · My work · Inbox · Subscriptions · Settings · Sign out          |
| `admin`           | (inline in `context_panel.html`)                             | Overview · Audit log · Workspaces · Sinks · Destinations · Keys · System |

Sections marked **(inline)** above keep their static link list
directly in `context_panel.html` because the content is fully static.

## Top-bar slots

| Slot      | Component                                                | Visibility            |
|---|---|---|
| Brand     | `<a class="navbar-brand" href="/">`                      | always                |
| Search    | Cmd+K trigger → `command_palette.html`                   | always (≥ md)         |
| Quick-create | `components/quick_create_menu.html` (Phase 80.8)      | always (≥ md)         |
| Theme     | dropdown                                                 | always (≥ md)         |
| Workspace | [workspace_switcher.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/workspace_switcher.html) | members of ≥ 2 workspaces |
| Bell      | [notification_bell.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/notification_bell.html)   | authenticated |
| User      | [user_menu.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/user_menu.html)                   | authenticated |

## Footer slots (Phase 80.7)

| Slot   | Content                                                                  |
|---|---|
| Left   | Workspace slug pill + role chips (`auditor` / `supervisor` / `admin`)    |
| Center | Backend health pills — soyuz / MLflow / dbt / Hermes                     |
| Right  | Help hint — `?` shortcuts · `⌘K` search                                  |

Hidden on `pages/login.html`, `pages/register.html`, and on mobile.

## Command-palette entity coverage (Phase 80.6)

The Cmd+K palette indexes **every named entity** the user can reach.
Each kind below must be findable by `/api/search?q=<query>`.

| Kind            | Search fields                          | Backed by                       |
|---|---|---|
| `catalog`       | name + description                     | soyuz API                       |
| `schema`        | name + description                     | soyuz API                       |
| `table`         | name + description                     | soyuz API                       |
| `volume`        | name + description                     | soyuz API                       |
| `model`         | name + description                     | soyuz API                       |
| `data_product`  | full_name + description                | `DataProduct`                   |
| `notebook`      | path + title                           | `Notebook`                      |
| `dashboard`     | title + slug                           | `Dashboard`                     |
| `saved_query`   | title + body excerpt                   | `SavedQuery`                    |
| `topic`         | name + description                     | `Topic`                         |
| `issue`         | title + label name                     | `Issue`, `IssueLabel`           |
| `user`          | display_name + email                   | `User`, `WorkspaceMember`       |
| `agent`         | slug + display_name                    | `Agent`                         |
| `workspace`     | name + slug                            | `Workspace`, `WorkspaceMember`  |

Operators:

* `@<term>` — restrict to `user` kind (Slack convention).
* `#<term>` — restrict to `topic` kind.

Server-side rank: prefix-match > word-boundary-match > substring.
Cap at 50 results; group by kind in the dropdown.

## Active-section derivation

Pages thread `active_page` (a string) via their route context.
`base.html` derives `active_section` from `active_page` through
`_section_map`.  When adding a new page:

1. Pick or invent an `active_page` string.
2. Add it to `_section_map` in `base.html`.
3. The rail's `.active` highlight and context-panel partial select
   themselves.

The default fallback section is `federation` (catalog).  Pages that
don't set `active_page` (legacy or detail surfaces under a section)
keep the catalog tree visible.

## Locked design decisions (Phase 80 — 2026-05-15)

These ship with Phase 80 and are not subject to per-commit
re-negotiation:

1. **Group ordering**: `HOME → WATCH → BUILD → DATA → COMMUNITY →
   WORKSPACE`.  Supervisor-first.
2. **Default rail state**: **expanded** (220 px, labelled).  Persisted
   per-user in `localStorage["pql.primary-rail.collapsed"]`.
3. **Lens + dbt** keep their own BUILD entries.  Polish thin content
   on the page, never hide from nav.
4. **Footer**: always visible on authenticated pages.  No hide
   toggle in v1.
5. **No third sidebar.**  Detail pages do not grow a right rail; the
   four-slot chrome model is the contract.
6. **No HTTP route renames.**  Add new routes only; backward-compat
   with Hermes plugin + bookmarks.

## Maintenance discipline

When a Phase 81+ change adds a new HTML page:

1. Add the route to the right group table above.
2. Decide the `active_section` (or add a new one if no group fits).
3. If the new section needs its own context-panel partial, add it
   under `components/sidebars/` and wire it through
   `context_panel.html`.
4. Add the entity kind to the command-palette table if it has a
   detail page worth finding.
5. Update the rail entry list in
   `components/primary_rail.html`.

A page that doesn't appear here is, by definition, undiscoverable.
The Phase 80 walkthrough catalogued 5 such orphans
(`/issues`, `/topics`, `/feed`, `/users/{id}`, `/workspaces/{slug}`);
that count must stay at zero.
