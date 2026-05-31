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

import { pqlApi } from './api.js';
// Singletons consumed by the editor factories below.  Imported first
// so the import graph resolves toast → api before the editors that
// depend on ``window.pqlApi`` evaluate.
import { pqlToast } from './toast.js';

window.pqlToast = pqlToast;
window.pqlApi = pqlApi;

// Copy-button delegated listener.  Registers a single
// document-level click listener that handles every ``.pql-copy-btn``
// rendered by ``_macros/copy_button.html``.
import './copy_button.js';

// base.html inline-script exodus — five side-effect modules that
// install per-page wiring (htmx bridge, theme toggle, panel toggles,
// tooltips, recent-storage). All five used to live as inline
// ``<script>`` blocks in base.html; lifting them here keeps base.html
// markup-only and the JS in a place where tooling can see it.
import './base_htmx_bridge.js';
import './base_theme_toggle.js';
import './base_panel_toggles.js';
import './base_tooltips.js';
import './base_recent_storage.js';

// Per-entity ⋯-action menu mute handler.  Document-level
// click listener for every ``.pql-entity-mute-btn`` rendered by
// ``_macros/entity_actions.html``.
import './entity_actions.js';

// Permission-locked nav-link delegated listener.  Captures clicks
// on anchors rendered by ``_macros/permission_link.html`` when the
// caller passed ``granted=False`` and surfaces a toast naming the
// missing role instead of letting the dead ``href="#"`` swallow it.
import './permission_link.js';

// Bootstrap-tab URL-state sync.  Self-bootstrapping;
// reads ``?tab=…&subtab=…`` on DOMContentLoaded and mirrors active
// tabs back via history.replaceState.  Idempotent on pages without
// tabs.
import './tab_sync.js';
// Read-only CodeMirror viewer for static SQL blocks (saved-query
// detail page etc.).  Self-mounts on ``.pql-sql-viewer`` elements
// and re-runs on ``htmx:afterSwap`` so HTMX-injected fragments
// pick up the same syntax highlighting as the editor.
import './sql_viewer.js';

import { pqlHumanizeCron } from './humanize_cron.js';
// Pure utility helpers — no Alpine factories, but used directly from
// templates as ``x-text="pqlRelativeTime(iso)"`` etc.
import { pqlAbsTime, pqlParseServerIso, pqlRelativeTime } from './relative_time.js';

window.pqlParseServerIso = pqlParseServerIso;
window.pqlRelativeTime = pqlRelativeTime;
window.pqlAbsTime = pqlAbsTime;
window.pqlHumanizeCron = pqlHumanizeCron;

// Multi-select state mixin.  Re-attached to window
// so inline-script Alpine factories on alerts / audit_inbox /
// issues_index can spread the mixin into their own x-data return.
import { bulkSelect } from './bulk_actions.js';

window.bulkSelect = bulkSelect;

// Inline-editor factories.
import { editable } from './editable.js';
import { permissionsEditor } from './permissions_editor.js';
import { optionsEditor, propertiesEditor } from './properties_editor.js';
import { tagsEditor } from './tags_editor.js';

window.editable = editable;
window.permissionsEditor = permissionsEditor;
window.tagsEditor = tagsEditor;
window.propertiesEditor = propertiesEditor;
window.optionsEditor = optionsEditor;

import { createForeignCatalogForm, deleteConfirm } from './pages/federation/catalogs.js';
// Federation create-forms + delete-confirm.  federation.js is split
// into three sibling modules; bootstrap.js imports from each directly
// so the window-name surface stays identical without an extra façade
// layer.
import { createConnectionForm } from './pages/federation/connections.js';
import {
  createCredentialForm,
  createExternalLocationForm,
} from './pages/federation/credentials.js';

window.createConnectionForm = createConnectionForm;
window.createExternalLocationForm = createExternalLocationForm;
window.createCredentialForm = createCredentialForm;
window.createForeignCatalogForm = createForeignCatalogForm;
window.deleteConfirm = deleteConfirm;

import { jobRowActions } from './job_row_actions.js';
// List table + job-row hover actions + SQL editor.
import { listTable } from './list_table.js';
import { sqlEditor } from './sql_editor/index.js';

window.listTable = listTable;
window.jobRowActions = jobRowActions;
window.sqlEditor = sqlEditor;

// polymorphic social-tabs Alpine factory.  Used by
// table.html + branch_detail.html via the kind-agnostic
// ``_endorsements_pane.html`` + ``_followers_pane.html`` partials.
// ``data_product.html`` keeps its inline x-data + DP-flavoured
// partials polish unifies the two.
import { socialTabs } from './social_tabs.js';

window.socialTabs = socialTabs;

// browser notebook editor.  cellEditor is the per-cell
// CodeMirror factory; notebookEditor is the top-level Alpine factory
// mounted on /notebooks/edit/{path}.
import { cellEditor } from './notebook/cell_editor.js';
import { notebookEditor } from './notebook/notebook_editor.js';

window.cellEditor = cellEditor;
window.notebookEditor = notebookEditor;

// per-cell social thread.  cellThread powers the inline
// 💬 chip + collapsible thread below each cell on /notebooks/edit/{path}.
// Comments + reactions + follows ride the polymorphic
// /api/social/notebook_cell/{ref}/... routes.
import { cellThread } from './notebook/cell_thread.js';

window.cellThread = cellThread;

// workspace library browse page for pinned facts.
// Backs the ``factsLibrary()`` factory mounted on
// ``/library/facts``.  Lives outside the notebook editor so the
// page can render without the heavy editor coordinator.
import { factsLibrary } from './facts_library.js';

window.factsLibrary = factsLibrary;

// the cell-tag picker lives inside the per-cell
// ``cellThread`` factory now (was a separate nested ``cellTagPicker``
// x-data, but Alpine snapshotted the ``cell`` POJO so picker mutations
// never reached ``cells[i].tags``).  No separate registration needed.

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

// Lineage drill-down sub-pane factories.
// Three panes — Row trace / Column trace / Value changes — sit
// next to the existing Summary + Graph sub-pills inside the
// Lineage top-tab on /runs/{id}.  Each pane wraps one of the
// existing GET /api/lineage/{row-trace,column-trace,value-changes}
// endpoints; deep-linked via the pql:trace-{row,column,value}
// custom events fired from Summary "Trace" buttons + the Graph
// side-panel column-pair "Trace this column" button.
import {
  bindLineageTraceButtons,
  columnTracePane,
  rowTracePane,
  valueChangesPane,
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

import { dashboardTree } from './components/dashboards_sidebar.js';
import { footerBar } from './components/footer_bar.js';
import { notificationBell } from './components/notification_bell.js';
import { notebookDiscussion, notebookReadme } from './notebook/discussion.js';
import { apiKeyGrants, apiKeyUsageChart } from './pages/admin_api_key_detail.js';
import { apiKeyCreate, apiKeyCreatedModal, apiKeyRow } from './pages/admin_api_keys.js';
import { auditSinkCreate, auditSinkRow } from './pages/admin_audit_sinks.js';
import { adminDataProductApply } from './pages/admin_data_product_apply.js';
import { adminDomains, domainArchiveButton, domainMembers } from './pages/admin_domains.js';
import { adminEntityDiscovery } from './pages/admin_entity_discovery.js';
import { adminGlossary } from './pages/admin_glossary.js';
import { adminGovernance } from './pages/admin_governance.js';
import { adminMeshDashboard } from './pages/admin_mesh_dashboard.js';
import { adminMeshEntities } from './pages/admin_mesh_entities.js';
import { adminPolicyModules } from './pages/admin_policy_modules.js';
import { reviewDestCreate, reviewDestRow } from './pages/admin_review_destinations.js';
import { adminSourcesList } from './pages/admin_sources.js';
import { adminWorkspaces, archiveButton } from './pages/admin_workspaces.js';
import { agentProfile } from './pages/agent_profile.js';
import { alertDetail } from './pages/alert_detail.js';
// Page-template factories.  Each was previously an inline
// ``<script>`` IIFE inside its pages/*.html file; lifting them here
// means a single shared import graph and the synchronous-window-
// attach-before-Alpine-DOM-walk invariant stays defused without
// per-page boilerplate.
import { alertsPage } from './pages/alerts.js';
import { branchDiscussion } from './pages/branch_detail.js';
import { canvasEditor } from './pages/canvas.js';
import { catalogTree, pathFromUrl } from './pages/catalog_tree.js';
import { dataProductDetail } from './pages/data_product.js';
import { dpCanvasEditor } from './pages/dp_canvas_editor.js';
import { dpCanvasDiff } from './pages/dp_canvas_diff.js';
import { meshCanvasEditor } from './pages/mesh_canvas_editor.js';
import { dataProductDomainPanel } from './pages/data_product_domain.js';
import { dpReleasesCard, ingestStatusBand } from './pages/data_product_extras.js';
import { dataProductContractTests } from './pages/data_product_contract_tests.js';
import { dataProductGovernance } from './pages/data_product_governance.js';
import { dataProductInterop, dataProductSloPanel } from './pages/data_product_interop.js';
import {
  dataProductBitemporalPanel,
  dataProductConsumptionPanel,
  dataProductEventPortPanel,
  dataProductInfrastructurePanel,
  dataProductLifecyclePanel,
  dataProductRatingWidget,
  dataProductUseCasesPanel,
} from './pages/data_product_overview_panels.js';
import {
  dataProductDiscoveryCard,
  dataProductInputPortsList,
  dataProductPortsPanel,
  dataProductSemanticPanel,
  dataProductStatsPanel,
} from './pages/data_product_quantum.js';
import { dataProductsBrowse } from './pages/data_products.js';
import { dataProductsCandidates } from './pages/data_products_candidates.js';
import { dataProductsFollowed } from './pages/data_products_followed.js';
import { dataProductsTrending } from './pages/data_products_trending.js';
import { dbtSchemaContext } from './pages/dbt_schema_context.js';
import { dbtTableContext } from './pages/dbt_table_context.js';
import { domainDetail } from './pages/domain_detail.js';
import { domainsBrowse } from './pages/domains.js';
import { feedPage } from './pages/feed.js';
import { glossaryBrowse, glossaryDetail } from './pages/glossary.js';
import { homeRecentCatalogs, homeSparkline } from './pages/home.js';
import { ingestSourceDetail } from './pages/ingest_source_detail.js';
import { ingestSourceCreate } from './pages/ingest_sources_new.js';
import { issueDetail } from './pages/issue_detail.js';
import { issuesIndex } from './pages/issues_index.js';
import { lensChat } from './pages/lens_index.js';
import { lineageExplorerForm } from './pages/lineage_index.js';
import { meSettingsForm } from './pages/me_settings.js';
import { meSubscriptions } from './pages/me_subscriptions.js';
import { meshEntities } from './pages/mesh_entities.js';
import { meshGraph } from './pages/mesh_graph.js';
import { meshHealth } from './pages/mesh_health.js';
import { mlTableContext } from './pages/ml_table_context.js';
import { mlflowCockpit } from './pages/mlflow_cockpit.js';
import {
  modelDiscussion,
  modelLineageDag,
  modelPromotion,
  modelReadme,
  modelReviews,
  modelVersions,
} from './pages/model.js';
import { modelsBrowse } from './pages/models.js';
import { notebookWorkspace } from './pages/notebooks_workspace.js';
import { notificationsInbox } from './pages/notifications.js';
import { rowAtVersion } from './pages/row_trace.js';
import { savedQueryDiscussion, savedQueryReadme } from './pages/saved_audit_query_detail.js';
import { savedViewDetail } from './pages/saved_view_detail.js';
import { savedViewForm } from './pages/saved_view_new.js';
import { catalogDiscussion, catalogReadme } from './pages/schemas.js';
import { notificationSettings } from './pages/settings_notifications.js';
import { tableDiscussion, tableReadme, tableStats } from './pages/table.js';
import { tablePreview } from './pages/table_preview.js';
import { schemaDiscussion, schemaReadme } from './pages/tables.js';
import { topicDetail } from './pages/topic_detail.js';
import { topicsIndex } from './pages/topics_index.js';
import { userProfile } from './pages/user_profile.js';
import { volumeDetail } from './pages/volume_detail.js';
import { workspaceLanding } from './pages/workspace_landing.js';
import { issuesPane } from './partials/issues_pane.js';
// W2.8 Tier-3 named-export imports.
import { runDiscussion } from './run_view/tab_social.js';
import { rollbackPanel } from './run_view/uc_mutations.js';
import { semanticSearch } from './table/semantic_search.js';

// Side-effect IIFE modules.  Each guards on a page-local element id so
// the cost on unrelated pages is one ``getElementById`` lookup.
import './pages/audit_inbox.js';
import './pages/dbt.js';
import './pages/audit_search.js';
import './pages/audit_by_table.js';
import './pages/agent_run_compare.js';
import './pages/run_view.js';

// row_trace.js + saved_audit_query_detail.js carry both an exported
// factory AND a page-local side-effect binder; the export imports
// above already evaluate them, so no extra side-effect import here.

import { alertsSidebar } from './components/sidebars/alerts_sidebar.js';
import { branchesSidebar } from './components/sidebars/branches_sidebar.js';
import { jobsSidebar } from './components/sidebars/jobs_sidebar.js';
import { mlflowSidebar } from './components/sidebars/mlflow_sidebar.js';
// Per-section context-panel factories.  Each replaces a static link
// list in components/context_panel.html with a navigable,
// refresh-aware Alpine factory analogous to catalogTree() above.
import { runsSidebar } from './components/sidebars/runs_sidebar.js';
import { workspaceSidebar } from './components/sidebars/workspace_sidebar.js';
import { notebookChatPanel } from './notebook/chat.js';
import { chatPanel } from './sql_editor/chat.js';

window.alertsPage = alertsPage;
window.feedPage = feedPage;
window.dataProductDetail = dataProductDetail;
window.modelVersions = modelVersions;
window.modelPromotion = modelPromotion;
window.modelDiscussion = modelDiscussion;
window.modelReadme = modelReadme;
window.modelReviews = modelReviews;
window.modelLineageDag = modelLineageDag;
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
window.semanticSearch = semanticSearch;
window.tableStats = tableStats;
window.tableDiscussion = tableDiscussion;
window.tableReadme = tableReadme;
window.rollbackPanel = rollbackPanel;
window.notebookDiscussion = notebookDiscussion;
window.notebookReadme = notebookReadme;
window.apiKeyRow = apiKeyRow;
window.apiKeyCreate = apiKeyCreate;
window.apiKeyCreatedModal = apiKeyCreatedModal;
window.apiKeyGrants = apiKeyGrants;
window.apiKeyUsageChart = apiKeyUsageChart;
window.ingestSourceDetail = ingestSourceDetail;
window.ingestSourceCreate = ingestSourceCreate;
window.auditSinkRow = auditSinkRow;
window.auditSinkCreate = auditSinkCreate;
window.reviewDestRow = reviewDestRow;
window.reviewDestCreate = reviewDestCreate;
window.canvasEditor = canvasEditor;
window.dpCanvasEditor = dpCanvasEditor;
window.dpCanvasDiff = dpCanvasDiff;
window.meshCanvasEditor = meshCanvasEditor;
window.dataProductsBrowse = dataProductsBrowse;
window.userProfile = userProfile;
window.meSubscriptions = meSubscriptions;
window.notificationsInbox = notificationsInbox;
window.rowAtVersion = rowAtVersion;
window.savedQueryDiscussion = savedQueryDiscussion;
window.savedQueryReadme = savedQueryReadme;
window.runDiscussion = runDiscussion;
window.branchDiscussion = branchDiscussion;
window.lensChat = lensChat;
window.schemaDiscussion = schemaDiscussion;
window.schemaReadme = schemaReadme;
window.catalogDiscussion = catalogDiscussion;
window.catalogReadme = catalogReadme;
window.topicsIndex = topicsIndex;
window.issuesIndex = issuesIndex;
window.lineageExplorerForm = lineageExplorerForm;
window.issueDetail = issueDetail;
window.workspaceLanding = workspaceLanding;
window.footerBar = footerBar;
window.adminWorkspaces = adminWorkspaces;
window.archiveButton = archiveButton;
window.adminDomains = adminDomains;
window.domainArchiveButton = domainArchiveButton;
window.domainMembers = domainMembers;
window.domainsBrowse = domainsBrowse;
window.domainDetail = domainDetail;
window.dataProductDomainPanel = dataProductDomainPanel;
window.dataProductPortsPanel = dataProductPortsPanel;
window.dataProductInputPortsList = dataProductInputPortsList;
window.dataProductSemanticPanel = dataProductSemanticPanel;
window.dataProductStatsPanel = dataProductStatsPanel;
window.dataProductDiscoveryCard = dataProductDiscoveryCard;
window.dataProductGovernance = dataProductGovernance;
window.dataProductContractTests = dataProductContractTests;
window.dataProductInterop = dataProductInterop;
window.dataProductSloPanel = dataProductSloPanel;
window.dataProductLifecyclePanel = dataProductLifecyclePanel;
window.dataProductBitemporalPanel = dataProductBitemporalPanel;
window.dataProductInfrastructurePanel = dataProductInfrastructurePanel;
window.dataProductUseCasesPanel = dataProductUseCasesPanel;
window.dataProductRatingWidget = dataProductRatingWidget;
window.dataProductConsumptionPanel = dataProductConsumptionPanel;
window.dataProductEventPortPanel = dataProductEventPortPanel;
window.meshGraph = meshGraph;
window.meshHealth = meshHealth;
window.meshEntities = meshEntities;
window.adminMeshEntities = adminMeshEntities;
window.adminGlossary = adminGlossary;
window.adminGovernance = adminGovernance;
window.adminPolicyModules = adminPolicyModules;
window.adminMeshDashboard = adminMeshDashboard;
window.adminEntityDiscovery = adminEntityDiscovery;
window.adminDataProductApply = adminDataProductApply;
window.glossaryBrowse = glossaryBrowse;
window.glossaryDetail = glossaryDetail;
window.savedViewDetail = savedViewDetail;
window.issuesPane = issuesPane;
window.savedViewForm = savedViewForm;
window.modelsBrowse = modelsBrowse;
window.topicDetail = topicDetail;
window.dataProductsCandidates = dataProductsCandidates;
window.ingestStatusBand = ingestStatusBand;
window.dpReleasesCard = dpReleasesCard;
window.notificationBell = notificationBell;
window.notificationSettings = notificationSettings;
window.adminSourcesList = adminSourcesList;
window.meSettingsForm = meSettingsForm;
window.dataProductsFollowed = dataProductsFollowed;
window.dataProductsTrending = dataProductsTrending;
window.agentProfile = agentProfile;
window.dashboardTree = dashboardTree;
window.homeSparkline = homeSparkline;
window.homeRecentCatalogs = homeRecentCatalogs;
window.chatPanel = chatPanel;
window.notebookChatPanel = notebookChatPanel;
window.runsSidebar = runsSidebar;
window.branchesSidebar = branchesSidebar;
window.workspaceSidebar = workspaceSidebar;
window.jobsSidebar = jobsSidebar;
window.alertsSidebar = alertsSidebar;
window.mlflowSidebar = mlflowSidebar;
