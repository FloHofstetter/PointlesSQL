/**
 * Lazy-loader and style sheets for cytoscape.js + dagre.
 *
 * cytoscape, dagre, and the cytoscape-dagre adapter ship as three
 * separate CDN scripts.  ``loadCytoscapeOnce()`` injects them on
 * demand the first time a consumer (run-detail Graph sub-tab,
 * model-detail Lineage tab) needs them, idempotent across mount /
 * unmount cycles via a module-level Promise cache.  No cytoscape
 * bytes hit the wire on a normal page load.
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
 * navigation back-and-forth.  Promise rejects on first script load
 * failure so the caller can surface a fail-soft error.
 *
 * @returns {Promise<void>}
 */
export function loadCytoscapeOnce() {
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

/**
 * Register the cytoscape-dagre extension exactly once.
 *
 * Must be called after :func:`loadCytoscapeOnce` resolves.  Sets a
 * module-global flag so subsequent renders skip the registration.
 *
 * @returns {boolean} true if dagre is now available, false if not.
 */
export function ensureDagreRegistered() {
    if (typeof window.cytoscape !== 'function') return false;
    if (typeof window.cytoscapeDagre === 'function' && !window.__cytoscapeDagreRegistered) {
        window.cytoscape.use(window.cytoscapeDagre);
        window.__cytoscapeDagreRegistered = true;
    }
    return Boolean(window.__cytoscapeDagreRegistered);
}

/**
 * Return the layout config to feed cytoscape.layout().
 *
 * Prefers dagre when available; falls back to breadth-first
 * traversal when the extension hasn't registered (e.g. CDN
 * blocked, dagre script failed mid-load).
 *
 * @param {object} [overrides]
 * @returns {object}
 */
export function dagLayout(overrides = {}) {
    if (window.__cytoscapeDagreRegistered) {
        return { name: 'dagre', rankDir: 'TB', nodeSep: 60, rankSep: 80, ...overrides };
    }
    return { name: 'breadthfirst', directed: true, padding: 20, ...overrides };
}

/**
 * Cytoscape style sheet for the run-detail lineage DAG.
 *
 * Tables render as round-rectangle nodes with the Inter font;
 * highlighted nodes get a brighter green border and a slightly
 * lighter fill, dimmed nodes drop to 25% opacity.  Edges carry
 * the transform-kind label in muted gray text on a translucent
 * pill background; highlighted edges turn green.
 */
export const RUN_GRAPH_STYLE = [
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
        style: { 'opacity': 0.25 },
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
        style: { 'opacity': 0.2 },
    },
];

/**
 * Cytoscape style sheet for the model-detail lineage view.
 *
 * Three node kinds: tables (green border), predictions (blue
 * border), and the focused model itself (orange hexagon).  Edges
 * with ``label = "inferred_to"`` render dashed-blue to mark the
 * inference boundary.
 */
export const MODEL_GRAPH_STYLE = [
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

/**
 * Render a focused model-lineage DAG.
 *
 * The model-detail page builds its own ``{nodes, edges}`` payload
 * via ``GET /api/models/{full_name}/lineage`` and feeds it here
 * after :func:`loadCytoscapeOnce` resolves.  The render is
 * intentionally minimal: no click highlighting, no side panel, no
 * column-pair overlay.
 *
 * @param {string} containerId DOM id of the cytoscape mount.
 * @param {{nodes: object[], edges: object[]}} graphData Payload.
 * @returns {object|null} The cytoscape instance, or null if the
 *   library is unavailable.
 */
export function renderModelGraph(containerId, graphData) {
    if (typeof window.cytoscape !== 'function') return null;
    ensureDagreRegistered();
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
    return window.cytoscape({
        container: document.getElementById(containerId),
        elements,
        style: MODEL_GRAPH_STYLE,
        layout: window.__cytoscapeDagreRegistered
            ? { name: 'dagre', rankDir: 'LR', nodeSep: 60, rankSep: 80 }
            : { name: 'breadthfirst', directed: true },
    });
}
