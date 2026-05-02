/**
 * Lineage-DAG Alpine factory.
 *
 * Mounts on the Graph sub-tab inside the Lineage top-pane of
 * /runs/{id}. Fetches the JSON payload from
 * GET /api/runs/{run_id}/graph?op_id=... and feeds it into
 * cytoscape.js with the dagre layout extension for a top-down
 * directed graph (one box per touched table, arrows annotated
 * with transform_kind).
 *
 * cytoscape, dagre, and the cytoscape-dagre
 * adapter are loaded LAZILY: the three CDN scripts are no longer
 * in run_view.html's extra_js block. ``loadCytoscapeOnce()``
 * below injects them on demand the first time the user activates
 * the Graph sub-tab, gated by ``shown.bs.tab`` on the sub-tab
 * button. Alpine's eager x-init still fires at page load, but it
 * only registers the listener and immediately returns; no
 * cytoscape bytes hit the wire until the user actually opens the
 * Graph view. Idempotent across tab toggles via a module-level
 * Promise cache.
 *
 * Click behaviour:
 * - Click a node (table) → highlight the node + its incident
 * edges, dim the rest.
 * - Click an edge → highlight the edge + its endpoints
 * + label both columns of the first column-pair on the edge
 * in a side panel.
 * - Click a column label → not on the canvas itself; the
 * side panel below the canvas exposes a per-edge column list
 * and clicking a column highlights every edge that carries
 * it (upstream + downstream simultaneously, per the Sprint
 * 17.3 plan).
 */

const CYTOSCAPE_SRCS = [
 'https://cdn.jsdelivr.net/npm/cytoscape@3.30.4/dist/cytoscape.min.js',
 'https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js',
 'https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.js',
];

let _cytoscapeLoadPromise = null;

/**
 * Lazy-load cytoscape + dagre + cytoscape-dagre in order.
 *
 * Returns a Promise that resolves once all three scripts have run
 * AND ``window.cytoscape`` / ``window.cytoscapeDagre`` are defined.
 * Repeated calls return the same Promise — the loader is
 * idempotent across tab toggles, multiple component mounts, and
 * navigation back-and-forth. Promise rejects on first script
 * load failure so the caller can surface a fail-soft error.
 */
function loadCytoscapeOnce() {
 if (_cytoscapeLoadPromise) return _cytoscapeLoadPromise;
 _cytoscapeLoadPromise = (async () => {
 for (const src of CYTOSCAPE_SRCS) {
 await new Promise((resolve, reject) => {
 const s = document.createElement('script');
 s.src = src;
 s.async = false;
 s.onload = () => resolve();
 s.onerror = () => reject(new Error('failed to load ' + src));
 document.head.appendChild(s);
 });
 }
 })();
 return _cytoscapeLoadPromise;
}

// exposed on window so the model-detail Lineage tab
// (inline script, not part of the ESM bundle) can call the same
// lazy-loader the run-detail Graph sub-tab uses.
if (typeof window !== 'undefined') {
 window.loadCytoscapeOnce = loadCytoscapeOnce;
}

/**
 * render a focused model-lineage DAG.
 *
 * The model-detail page builds its own ``{nodes, edges}`` payload
 * via ``GET /api/models/{full_name}/lineage`` and feeds it to this
 * helper after ``loadCytoscapeOnce()`` resolves. The render is
 * intentionally minimal: no click highlighting, no side panel, no
 * column-pair overlay. The model node renders as an orange hexagon
 * so it stands out from the green table predecessors.
 *
 * @param {string} containerId DOM id of the cytoscape mount.
 * @param {{nodes: object[], edges: object[]}} graphData Payload.
 */
function renderModelGraph(containerId, graphData) {
 if (typeof window.cytoscape !== 'function') return null;
 if (typeof window.cytoscapeDagre === 'function' && !window.__cytoscapeDagreRegistered) {
 window.cytoscape.use(window.cytoscapeDagre);
 window.__cytoscapeDagreRegistered = true;
 }
 const elements = [
...(graphData.nodes || []).map((n) => ({
 data: {
 id: n.id,
 label: n.label || n.id,
 kind: n.kind || n.type || 'table',
 },
 })),
...(graphData.edges || []).map((e) => ({
 data: {
 id: e.id,
 source: e.source,
 target: e.target,
 label: e.label || '',
 },
 })),
 ];
 const style = [
 {
 selector: 'node[kind = "table"]',
 style: {
 'background-color': '#1e293b',
 'border-color': '#76b900',
 'border-width': 1,
 'shape': 'round-rectangle',
 'label': 'data(label)',
 'color': '#e6e6e6',
 'font-family': 'Inter, system-ui, sans-serif',
 'font-size': 11,
 'text-valign': 'center',
 'text-halign': 'center',
 'width': 'label',
 'height': 'label',
 'padding': '12px',
 },
 },
 {
 selector: 'node[kind = "prediction"]',
 style: {
 'background-color': '#1e293b',
 'border-color': '#3b82f6',
 'border-width': 1,
 'shape': 'round-rectangle',
 'label': 'data(label)',
 'color': '#bfdbfe',
 'font-family': 'Inter, system-ui, sans-serif',
 'font-size': 11,
 'text-valign': 'center',
 'text-halign': 'center',
 'width': 'label',
 'height': 'label',
 'padding': '12px',
 },
 },
 {
 selector: 'node[kind = "model"]',
 style: {
 'background-color': '#3a2a1e',
 'border-color': '#fb923c',
 'border-width': 2,
 'shape': 'hexagon',
 'label': 'data(label)',
 'color': '#fde68a',
 'font-family': 'Inter, system-ui, sans-serif',
 'font-size': 13,
 'font-weight': 'bold',
 'text-valign': 'center',
 'text-halign': 'center',
 'width': 'label',
 'height': 'label',
 'padding': '18px',
 },
 },
 {
 selector: 'edge',
 style: {
 'curve-style': 'bezier',
 'target-arrow-shape': 'triangle',
 'line-color': '#475569',
 'target-arrow-color': '#475569',
 'width': 2,
 'label': 'data(label)',
 'font-size': 9,
 'color': '#94a3b8',
 'text-background-color': '#0f172a',
 'text-background-opacity': 0.7,
 'text-background-padding': 2,
 },
 },
 {
 selector: 'edge[label = "inferred_to"]',
 style: {
 'line-style': 'dashed',
 'line-color': '#3b82f6',
 'target-arrow-color': '#3b82f6',
 'color': '#bfdbfe',
 },
 },
 ];
 return window.cytoscape({
 container: document.getElementById(containerId),
 elements,
 style,
 layout: window.__cytoscapeDagreRegistered
 ? { name: 'dagre', rankDir: 'LR', nodeSep: 60, rankSep: 80 }
 : { name: 'breadthfirst', directed: true },
 });
}

if (typeof window !== 'undefined') {
 window.renderModelGraph = renderModelGraph;
}

const STYLE = [
 {
 selector: 'node',
 style: {
 'background-color': '#1e293b',
 'border-color': '#76b900',
 'border-width': 1,
 'label': 'data(table)',
 'color': '#e6e6e6',
 'font-family': 'Inter, system-ui, sans-serif',
 'font-size': 11,
 'text-wrap': 'wrap',
 'text-max-width': 180,
 'text-valign': 'center',
 'text-halign': 'center',
 'shape': 'round-rectangle',
 'width': 'label',
 'height': 'label',
 'padding': '12px',
 },
 },
 {
 selector: 'node.highlighted',
 style: {
 'background-color': '#3a4a2a',
 'border-color': '#9fd554',
 'border-width': 2,
 },
 },
 {
 selector: 'node.dimmed',
 style: {
 'opacity': 0.25,
 },
 },
 {
 selector: 'edge',
 style: {
 'curve-style': 'bezier',
 'target-arrow-shape': 'triangle',
 'line-color': '#475569',
 'target-arrow-color': '#475569',
 'width': 2,
 'label': 'data(label)',
 'font-size': 9,
 'color': '#94a3b8',
 'text-background-color': '#0f172a',
 'text-background-opacity': 0.7,
 'text-background-padding': 2,
 },
 },
 {
 selector: 'edge.highlighted',
 style: {
 'line-color': '#76b900',
 'target-arrow-color': '#76b900',
 'width': 3,
 'color': '#9fd554',
 },
 },
 {
 selector: 'edge.dimmed',
 style: {
 'opacity': 0.2,
 },
 },
];

export function lineageDag(initial) {
 return {
 runId: initial.runId,
 opId: initial.opId || null,
 loading: true,
 error: null,
 nodes: [],
 edges: [],
 cy: null,
 // Side-panel state.
 selectedEdgeId: null,
 selectedColumn: null, // {column: str, direction: 'upstream'|'downstream'} | null

 // the loading flag stays true until the user
 // first activates the Graph sub-tab. The canvas template's
 // ``x-show="!loading && !error && nodes.length > 0"`` keeps
 // showing the spinner until then, which is the correct UX
 // (the user just clicked into the tab; brief load is expected).
 _started: false,

 async init() {
 const tabBtn = document.querySelector(
 '[data-bs-target="#tab-lineage-graph"]',
 );
 if (!tabBtn) {
 // No Bootstrap tab navigation context (e.g. test
 // harness, deeplinked iframe). Fall through to an
 // immediate load so the component still works.
 return this._loadAndRender();
 }
 if (tabBtn.classList.contains('active')) {
 // Page-load with hash deeplink (#tab-lineage-graph)
 // already activated the tab — load immediately.
 return this._loadAndRender();
 }
 tabBtn.addEventListener(
 'shown.bs.tab',
 () => this._loadAndRender(),
 { once: true },
 );
 },

 async _loadAndRender() {
 if (this._started) return;
 this._started = true;
 try {
 await loadCytoscapeOnce();
 } catch (e) {
 this.error = 'cytoscape.js failed to load: ' + String(e);
 this.loading = false;
 return;
 }
 try {
 const res = await fetch(this._url(), {
 headers: { Accept: 'application/json' },
 });
 if (!res.ok) {
 throw new Error('HTTP ' + res.status);
 }
 const data = await res.json();
 this.nodes = data.nodes || [];
 this.edges = data.edges || [];
 } catch (e) {
 this.error = String(e);
 this.loading = false;
 return;
 }
 this.loading = false;
 // Render after Alpine has flipped the loading flag away
 // (so the canvas div is in the DOM).
 this.$nextTick(() => this._render());
 },

 _url() {
 const params = new URLSearchParams();
 if (this.opId) params.set('op_id', String(this.opId));
 const qs = params.toString();
 return `/api/runs/${encodeURIComponent(this.runId)}/graph${qs ? '?' + qs : ''}`;
 },

 _render() {
 if (this.nodes.length === 0) {
 return;
 }
 if (typeof window.cytoscape !== 'function') {
 this.error =
 'cytoscape.js failed to load — loadCytoscapeOnce() resolved but window.cytoscape is undefined.';
 return;
 }
 // Wire the dagre extension on first call (idempotent — the
 // extension itself guards against double-registration).
 if (typeof window.cytoscapeDagre === 'function' && !window.__cytoscapeDagreRegistered) {
 window.cytoscape.use(window.cytoscapeDagre);
 window.__cytoscapeDagreRegistered = true;
 }

 const elements = [
...this.nodes.map((n) => ({ data: { id: n.id, table: n.table } })),
...this.edges.map((e) => ({
 data: {
 id: e.id,
 source: e.source,
 target: e.target,
 label: this._edgeLabel(e),
 },
 })),
 ];

 const container = this.$refs.canvas;
 this.cy = window.cytoscape({
 container,
 elements,
 style: STYLE,
 layout: window.__cytoscapeDagreRegistered
 ? { name: 'dagre', rankDir: 'TB', nodeSep: 60, rankSep: 80 }
 : { name: 'breadthfirst', directed: true, padding: 20 },
 wheelSensitivity: 0.2,
 });

 this.cy.on('tap', 'edge', (evt) => {
 const id = evt.target.data('id');
 this.selectedEdgeId = id;
 this.selectedColumn = null;
 this._highlightEdge(id);
 });
 this.cy.on('tap', 'node', (evt) => {
 const id = evt.target.data('id');
 this.selectedEdgeId = null;
 this.selectedColumn = null;
 this._highlightNode(id);
 });
 this.cy.on('tap', (evt) => {
 if (evt.target === this.cy) {
 this._clearHighlight();
 this.selectedEdgeId = null;
 this.selectedColumn = null;
 }
 });
 },

 _edgeLabel(edge) {
 if (!edge.transform_kinds || edge.transform_kinds.length === 0) {
 return edge.op_name || '';
 }
 return edge.transform_kinds.join(' / ');
 },

 _highlightEdge(edgeId) {
 if (!this.cy) return;
 this.cy.elements().removeClass('highlighted dimmed');
 const edge = this.cy.getElementById(edgeId);
 edge.addClass('highlighted');
 edge.connectedNodes().addClass('highlighted');
 this.cy.elements().not(edge).not(edge.connectedNodes()).addClass('dimmed');
 },

 _highlightNode(nodeId) {
 if (!this.cy) return;
 this.cy.elements().removeClass('highlighted dimmed');
 const node = this.cy.getElementById(nodeId);
 node.addClass('highlighted');
 node.connectedEdges().addClass('highlighted');
 node.connectedEdges().connectedNodes().addClass('highlighted');
 this.cy.elements()
.not(node)
.not(node.connectedEdges())
.not(node.connectedEdges().connectedNodes())
.addClass('dimmed');
 },

 _clearHighlight() {
 if (!this.cy) return;
 this.cy.elements().removeClass('highlighted dimmed');
 },

 // Side-panel helpers consumed by the template via x-show / x-for.

 currentEdge() {
 if (!this.selectedEdgeId) return null;
 return this.edges.find((e) => e.id === this.selectedEdgeId) || null;
 },

 selectColumn(column) {
 // Find every edge whose column_pairs touch ``column`` as
 // either source_column or target_column, then highlight
 // them all simultaneously. This is the "upstream +
 // downstream" requirement from the plan.
 if (!this.cy) return;
 this.selectedColumn = { column, direction: 'both' };
 this.cy.elements().removeClass('highlighted dimmed');
 const matching = this.edges.filter((e) =>
 (e.column_pairs || []).some(
 (p) => p.source_column === column || p.target_column === column,
 ),
 );
 const matchingIds = new Set(matching.map((e) => e.id));
 const matchingNodeIds = new Set(
 matching.flatMap((e) => [e.source, e.target]),
 );
 this.cy.edges().forEach((e) => {
 if (matchingIds.has(e.data('id'))) {
 e.addClass('highlighted');
 } else {
 e.addClass('dimmed');
 }
 });
 this.cy.nodes().forEach((n) => {
 if (matchingNodeIds.has(n.data('id'))) {
 n.addClass('highlighted');
 } else {
 n.addClass('dimmed');
 }
 });
 },

 clearSelection() {
 this.selectedEdgeId = null;
 this.selectedColumn = null;
 this._clearHighlight();
 },
 };
}
