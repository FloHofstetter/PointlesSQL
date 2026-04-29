/**
 * Sprint 17.3 — Lineage-DAG Alpine factory.
 *
 * Mounts on the Graph sub-tab inside the Lineage top-pane of
 * /runs/{id}.  Fetches the JSON payload from
 * GET /api/runs/{run_id}/graph?op_id=... and feeds it into
 * cytoscape.js with the dagre layout extension for a top-down
 * directed graph (one box per touched table, arrows annotated
 * with transform_kind).
 *
 * Cytoscape + cytoscape-dagre are loaded from jsdelivr in
 * run_view.html's extra_js block — this file assumes
 * window.cytoscape and window.cytoscapeDagre are present at
 * factory-call time.  If they aren't (script blocked, offline,
 * etc.), the component renders a fail-soft message instead of
 * throwing.
 *
 * Click behaviour:
 *  - Click a node (table)  → highlight the node + its incident
 *    edges, dim the rest.
 *  - Click an edge          → highlight the edge + its endpoints
 *    + label both columns of the first column-pair on the edge
 *    in a side panel.
 *  - Click a column label   → not on the canvas itself; the
 *    side panel below the canvas exposes a per-edge column list
 *    and clicking a column highlights every edge that carries
 *    it (upstream + downstream simultaneously, per the Sprint
 *    17.3 plan).
 */

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

        async init() {
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
                this.error = 'cytoscape.js failed to load — check the extra_js script tags in run_view.html.';
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
            // them all simultaneously.  This is the "upstream +
            // downstream" requirement from the Sprint 17.3 plan.
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
