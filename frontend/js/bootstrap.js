// ESM bridge entrypoint.
//
// Loaded as ``<script type="module">`` from base.html, ordered BEFORE
// Alpine's CDN bundle.  ``type="module"`` scripts are defer-by-default
// and run in document order, so anything we register on ``window``
// inside this module is visible when Alpine's ``x-data`` walk begins.
//
// Each migrated factory is imported here as an ES module export and
// re-attached to ``window`` under the same name templates already use
// in their ``x-data="..."`` attributes — so migrating a file from
// IIFE-shape to ESM never requires touching template HTML.
//
// Ordering invariant (enforced by scripts/check-frontend-bootstrap-order.sh):
//   bootstrap.js  <script type="module">   // this file
//   alpine.js     <script defer>           // CDN bundle
//
// If a consumer of ``window.pql*`` ever throws at first render, check
// the script-tag order in frontend/templates/base.html before blaming
// the consumer.

// Singletons consumed by the editor factories below.  Imported first
// so the import graph resolves toast → api before the editors that
// depend on ``window.pqlApi`` evaluate.
import { pqlToast } from './toast.js';
import { pqlApi } from './api.js';

window.pqlToast = pqlToast;
window.pqlApi = pqlApi;

// Copy-button delegated listener (Sprint 56.7).  Registers a single
// document-level click listener that handles every ``.pql-copy-btn``
// rendered by ``_macros/copy_button.html``.
import './copy_button.js';

// Per-entity ⋯-action menu mute handler (Phase 81.M).  Document-level
// click listener for every ``.pql-entity-mute-btn`` rendered by
// ``_macros/entity_actions.html``.
import './entity_actions.js';

// Permission-locked nav-link delegated listener.  Captures clicks
// on anchors rendered by ``_macros/permission_link.html`` when the
// caller passed ``granted=False`` and surfaces a toast naming the
// missing role instead of letting the dead ``href="#"`` swallow it.
import './permission_link.js';

// Bootstrap-tab URL-state sync (Sprint 59.2).  Self-bootstrapping;
// reads ``?tab=…&subtab=…`` on DOMContentLoaded and mirrors active
// tabs back via history.replaceState.  Idempotent on pages without
// tabs.
import './tab_sync.js';
// Read-only CodeMirror viewer for static SQL blocks (saved-query
// detail page etc.).  Self-mounts on ``.pql-sql-viewer`` elements
// and re-runs on ``htmx:afterSwap`` so HTMX-injected fragments
// pick up the same syntax highlighting as the editor.
import './sql_viewer.js';

// Pure utility helpers — no Alpine factories, but used directly from
// templates as ``x-text="pqlRelativeTime(iso)"`` etc.
import { pqlParseServerIso, pqlRelativeTime, pqlAbsTime } from './relative_time.js';
import { pqlHumanizeCron } from './humanize_cron.js';

window.pqlParseServerIso = pqlParseServerIso;
window.pqlRelativeTime = pqlRelativeTime;
window.pqlAbsTime = pqlAbsTime;
window.pqlHumanizeCron = pqlHumanizeCron;

// Multi-select state mixin (Phase 81.G.B).  Re-attached to window
// so inline-script Alpine factories on alerts / audit_inbox /
// issues_index can spread the mixin into their own x-data return.
import { bulkSelect } from './bulk_actions.js';
window.bulkSelect = bulkSelect;

// Inline-editor factories.
import { editable } from './editable.js';
import { permissionsEditor } from './permissions_editor.js';
import { tagsEditor } from './tags_editor.js';
import { propertiesEditor, optionsEditor } from './properties_editor.js';

window.editable = editable;
window.permissionsEditor = permissionsEditor;
window.tagsEditor = tagsEditor;
window.propertiesEditor = propertiesEditor;
window.optionsEditor = optionsEditor;

// Federation create-forms + delete-confirm.  federation.js is split
// into three sibling modules; bootstrap.js imports from each directly
// so the window-name surface stays identical without an extra façade
// layer.
import { createConnectionForm } from './pages/federation/connections.js';
import {
    createCredentialForm,
    createExternalLocationForm,
} from './pages/federation/credentials.js';
import {
    createForeignCatalogForm,
    deleteConfirm,
} from './pages/federation/catalogs.js';

window.createConnectionForm = createConnectionForm;
window.createExternalLocationForm = createExternalLocationForm;
window.createCredentialForm = createCredentialForm;
window.createForeignCatalogForm = createForeignCatalogForm;
window.deleteConfirm = deleteConfirm;

// List table + job-row hover actions + SQL editor.
import { listTable } from './list_table.js';
import { jobRowActions } from './job_row_actions.js';
import { sqlEditor } from './sql_editor/index.js';

window.listTable = listTable;
window.jobRowActions = jobRowActions;
window.sqlEditor = sqlEditor;

// Phase 77.1.5 — polymorphic social-tabs Alpine factory.  Used by
// table.html + branch_detail.html via the kind-agnostic
// ``_endorsements_pane.html`` + ``_followers_pane.html`` partials.
// ``data_product.html`` keeps its inline x-data + DP-flavoured
// partials until Phase 77.11 polish unifies the two.
import { socialTabs } from './social_tabs.js';

window.socialTabs = socialTabs;

// Phase 66 — browser notebook editor.  cellEditor is the per-cell
// CodeMirror factory; notebookEditor is the top-level Alpine factory
// mounted on /notebooks/edit/{path}.
import { cellEditor } from './notebook/cell_editor.js';
import { notebookEditor } from './notebook/notebook_editor.js';

window.cellEditor = cellEditor;
window.notebookEditor = notebookEditor;

// Cmd+K command palette.  bootstrap.js re-attaches the factory under
// the same window name so the partial's x-data="commandPalette()"
// keeps working unchanged.
import { commandPalette } from './components/command_palette.js';

window.commandPalette = commandPalette;

// Lineage-DAG factory for the Graph sub-tab on /runs/{id}.
// cytoscape.js + dagre + cytoscape-dagre are loaded LAZILY by the
// factory itself (``loadCytoscapeOnce()`` inside the lineage_dag/ bundle)
// the first time the Graph sub-tab is activated, gated on Bootstrap's
// ``shown.bs.tab`` event.  No CDN bytes hit the wire on a normal
// /runs/{id} page load.
import { lineageDag } from './components/lineage_dag/index.js';

window.lineageDag = lineageDag;

// Lineage drill-down sub-pane factories (Phase 41 / Sprint 41.1).
// Three panes — Row trace / Column trace / Value changes — sit
// next to the existing Summary + Graph sub-pills inside the
// Lineage top-tab on /runs/{id}.  Each pane wraps one of the
// existing GET /api/lineage/{row-trace,column-trace,value-changes}
// endpoints; deep-linked via the pql:trace-{row,column,value}
// custom events fired from Summary "Trace" buttons + the Graph
// side-panel column-pair "Trace this column" button.
import {
    rowTracePane,
    columnTracePane,
    valueChangesPane,
    bindLineageTraceButtons,
} from './components/lineage_panes.js';

window.rowTracePane = rowTracePane;
window.columnTracePane = columnTracePane;
window.valueChangesPane = valueChangesPane;

// One-shot wiring for the Summary "Trace target row" buttons +
// the three window.pqlLineageTrace* helper functions.  Idempotent.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindLineageTraceButtons, { once: true });
} else {
    bindLineageTraceButtons();
}

// Page-template factories.  Each was previously an inline
// ``<script>`` IIFE inside its pages/*.html file; lifting them here
// means a single shared import graph and the synchronous-window-
// attach-before-Alpine-DOM-walk invariant stays defused without
// per-page boilerplate.
import { alertsPage } from './pages/alerts.js';
import { alertDetail } from './pages/alert_detail.js';
import { volumeDetail } from './pages/volume_detail.js';
import { notebookWorkspace } from './pages/notebooks_workspace.js';
import { tablePreview } from './pages/table_preview.js';
import { catalogTree, pathFromUrl } from './pages/catalog_tree.js';
import { dbtSchemaContext } from './pages/dbt_schema_context.js';
import { dbtTableContext } from './pages/dbt_table_context.js';
import { mlflowCockpit } from './pages/mlflow_cockpit.js';
import { mlTableContext } from './pages/ml_table_context.js';

// Per-section context-panel factories.  Each replaces a static link
// list in components/context_panel.html with a navigable,
// refresh-aware Alpine factory analogous to catalogTree() above.
import { runsSidebar } from './components/sidebars/runs_sidebar.js';
import { branchesSidebar } from './components/sidebars/branches_sidebar.js';
import { workspaceSidebar } from './components/sidebars/workspace_sidebar.js';
import { jobsSidebar } from './components/sidebars/jobs_sidebar.js';
import { alertsSidebar } from './components/sidebars/alerts_sidebar.js';
import { mlflowSidebar } from './components/sidebars/mlflow_sidebar.js';

window.alertsPage = alertsPage;
window.alertDetail = alertDetail;
window.volumeDetail = volumeDetail;
window.notebookWorkspace = notebookWorkspace;
window.tablePreview = tablePreview;
window.catalogTree = catalogTree;
window.pathFromUrl = pathFromUrl;
window.dbtSchemaContext = dbtSchemaContext;
window.dbtTableContext = dbtTableContext;
window.mlflowCockpit = mlflowCockpit;
window.mlTableContext = mlTableContext;
window.runsSidebar = runsSidebar;
window.branchesSidebar = branchesSidebar;
window.workspaceSidebar = workspaceSidebar;
window.jobsSidebar = jobsSidebar;
window.alertsSidebar = alertsSidebar;
window.mlflowSidebar = mlflowSidebar;
