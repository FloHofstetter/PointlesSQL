# Models browse walkthrough

> **Mode:** `browser` · **Surface:** /models + 5-tab detail

Exercises the registered-models browse surface
end-to-end: surface a registered model in the sidebar tree and the
top-level `/models` index, drill into the detail page, render the
focused lineage DAG, and side-by-side compare two versions with
metric/param diffs.

The goal is to prove the **catalog-tree integration** ("models
appear next to tables under each schema"), the **MLflow context
join** ("metrics + params from the linked MLflow run show up on
the versions tab"), and the **agent-run cross-link** ("clicking
the linked-run badge navigates to the auditing surface").

This walkthrough is **driven from a notebook + a browser**. It
can also be replayed by Claude Code via
`mcp__playwright__browser_*` against headful Firefox.

## Preconditions

- soyuz-catalog is running on `http://127.0.0.1:8080`.
- PointlesSQL is running on `http://127.0.0.1:8000` with the
 optional `[ml]` extra installed (`uv sync --extra ml`).
- The MLflow subprocess is enabled
 (`POINTLESSQL_MLFLOW_ENABLED=1`, the default) and reachable at
 `/mlflow/`.
- A test catalog `pql_test` exists with a writeable schema
 `mlflow_smoke`. The smoke test
 (`tests/test_mlflow_uc_oss_smoke.py`) creates these
 automatically.
- At least **two** ModelVersions of `pql_test.mlflow_smoke.smoke_model`
 exist with distinct MLflow runs. Train them via Hermes
 (preferred) or seed them via the smoke test fixtures.

## Walkthrough

### 1. The icon-rail "Models" tab

- Action: browse `http://127.0.0.1:8000/`, log in as the test user.
- Assert: the left icon rail shows a **`bi-box-seam`** icon labelled
 "Models" between the "ML" tab and any admin-only tabs. The icon
 is **not** the `bi-robot` glyph used by the MLflow iframe tab.
- Action: click "Models".
- Assert: the URL changes to `/models`. The breadcrumb at top
 shows `Home › Models`. The active section in the icon rail
 highlights "Models".

### 2. The metastore-wide models index

- Action: still on `/models`, observe the rendered table.
- Assert: the table has these columns: `Full Name`, `Owner`,
 `Latest Version`, `Status`, `Linked Runs`, `Updated`. At least
 one row contains `pql_test.mlflow_smoke.smoke_model` with:
 - **Latest Version**: `v2` (or higher)
 - **Status**: green `READY` badge
 - **Linked Runs**: an integer ≥ 1 in a small badge
- Action: in the catalog dropdown, select `pql_test`. Confirm the
 rendered list shrinks to that catalog only. Then clear back to
 "All catalogs" and verify other catalog models reappear.

### 3. Sidebar tree — models alongside tables

- Action: click the catalog tree breadcrumb / refresh the page.
 Expand `pql_test` → `mlflow_smoke` in the left sidebar tree.
- Assert: under `mlflow_smoke`, the schema node lists **both**:
 - the existing tables (with `bi-table` icon, green-bordered)
 - a new `smoke_model` row with the `bi-box-seam` icon
- Action: click the `smoke_model` row.
- Assert: the URL navigates to
 `/models/pql_test.mlflow_smoke.smoke_model`.

### 4. Tree search — model name match

- Action: clear navigation, type "smoke" into the sidebar search.
- Assert: the search results list contains a row of `kind="model"`
 with a `bi-box-seam` icon and `pql_test.mlflow_smoke.smoke_model`
 full name. Clicking it navigates to the detail page.

### 5. Model-detail page — five tabs

- Action: open `/models/pql_test.mlflow_smoke.smoke_model`.
- Assert: the page header shows the FQN, owner badge, and a tab
 bar with **Overview**, **Versions**, **Lineage**, **MLflow**,
 **Permissions**. The Overview tab is active by default.
- Assert: the Overview tab's "Linked Hermes runs" card lists the
 agent-run UUID that produced version 1, with a clickable
 `/runs/<id>` link.

### 6. Versions tab — MLflow context per version

- Action: click the **Versions** tab.
- Assert: the table renders one row per version. For the most
 recent version that has an MLflow run linked, the "Top Metrics"
 cell displays at least one metric like `loss=0.5` or
 `accuracy=0.92`. The "MLflow Run" cell shows a truncated
 run-id (`mlf-abc...`). The "Linked Agent Run" cell shows the
 first 8 chars of the agent-run UUID and links to `/runs/<id>`.

### 7. Compare view — side-by-side diff

- Action: in the Versions tab, click "Compare" on row v1. The
 button toggles into "vs v1" state. Click "Compare" on row v2.
- Assert: the URL changes to
 `/models/pql_test.mlflow_smoke.smoke_model/compare?v1=1&v2=2`.
- Assert: the page renders three cards:
 - **Metrics**: every metric is one row with columns
 `v1 | v2 | Δ | Δ%`. Metrics whose name contains `loss`/`error`
 show green Δ when the value drops, red when it rises. Metrics
 whose name contains `accuracy`/`f1`/`auc` show green when the
 value rises, red when it drops. Other metrics render the Δ
 in muted gray.
 - **Params**: shows added / removed / changed sections (any of
 `lr`, `batch_size`, `epochs`).
 - **Tags**: same shape as Params.
- Action: click "← Back to pql_test.mlflow_smoke.smoke_model" at
 the top.
- Assert: navigates back to the model-detail page.

### 8. Lineage tab — cytoscape mini-DAG

- Action: from the model-detail page, click the **Lineage** tab.
- Assert: the cytoscape container loads (briefly shows the
 loading spinner, then renders). The graph contains:
 - **One orange hexagon** in the centre — the model node. Its
 label is `smoke_model`.
 - **Zero or more rounded green rectangles** — the source tables
 consumed by any Hermes-agent-run linked to a version of the
 model. Edge labels read `trained_from`.
- If no source tables are recorded yet (run lineage table empty),
 the graph shows only the centre model node and a small empty
 hint. This is acceptable.

### 9. MLflow tab — iframe deep-link

- Action: click the **MLflow** tab.
- Assert: an iframe loads, pointing at
 `/mlflow/#/models/pql_test.mlflow_smoke.smoke_model`. The
 embedded MLflow UI shows the model registry page for this FQN
 (or its 404 page if MLflow's own browse can't find the FQN — see
 the BUG note below).

 > **Known limitation**: not every MLflow registry route is
 > deep-linkable. MLflow's OSS hash router occasionally renders
 > a "Model not found" placeholder when entered cold; refreshing
 > the iframe usually fixes it. This is upstream behaviour, not
 > a PointlesSQL bug.

### 10. Permissions tab — read-only stub

- Action: click the **Permissions** tab.
- Assert: an info-card explains that registered_model permissions
 must be set via the soyuz REST API, and shows the canonical
 endpoint path. No editable form.

### 11. Anonymous access — auth gate

- Action: log out (top-right user menu). Browse to
 `/models/pql_test.mlflow_smoke.smoke_model`.
- Assert: the auth middleware redirects to `/auth/login` (303).

## Playwright MCP script

Condensed browser replay for the eleven prose steps:

1. `browser_navigate('http://127.0.0.1:8000/')`,
   `browser_click(".rail-icon[aria-label='Models']")`
   — assert URL becomes `/models` and the active rail icon is
   highlighted.
2. `browser_evaluate('() => Array.from(document.querySelectorAll("table thead th")).map(n => n.innerText)')`
   — assert columns `Full Name`, `Owner`, `Latest Version`,
   `Status`, `Linked Runs`, `Updated`.
3. `browser_select_option(role="combobox", value="pql_test")`
   — table shrinks; reset to "All catalogs" and assert other
   rows reappear.
4. `browser_navigate('http://127.0.0.1:8000/')` then
   `browser_click("pql_test")` (sidebar tree),
   `browser_click("mlflow_smoke")`,
   `browser_click("smoke_model")`
   — URL becomes
   `/models/pql_test.mlflow_smoke.smoke_model`.
5. `browser_type(placeholder="Search…", text="smoke")`
   — assert the result list contains a `kind=model` row with
   `bi-box-seam` icon.
6. `browser_navigate('http://127.0.0.1:8000/models/pql_test.mlflow_smoke.smoke_model')`
   — assert the tab bar exposes Overview / Versions / Lineage /
   MLflow / Permissions.
7. `browser_click("Versions")`
   — assert ≥ 1 row has a "Top Metrics" cell with a `metric=value`
   substring.
8. `browser_click("Compare")` (on v1 row),
   `browser_click("Compare")` (on v2 row)
   — URL becomes
   `/models/pql_test.mlflow_smoke.smoke_model/compare?v1=1&v2=2`.
9. `browser_click("← Back")` — returns to model detail.
10. `browser_click("Lineage")` — `browser_wait_for(".cytoscape-canvas")`.
11. `browser_click("MLflow")` — assert iframe `src` ends with
    `/mlflow/#/models/pql_test.mlflow_smoke.smoke_model`.
12. **Anonymous:** logout + navigate the same URL — assert
    `browser_navigate` ends on `/auth/login`.

## Out of scope (defer to later sprints)

- Tag editing on registered_model securables (Soyuz
 excludes `registered_model` from `TagSecurableType`).
- Champion/challenger promotion UI.
- Inference lineage from a model to downstream prediction tables
.
- Forced autolog on PQL training hooks.
- Permissions UI.
