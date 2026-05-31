/*
 * Wrap Dagre's graph layout for the DP-Canvas editor.
 *
 * Dagre runs left-to-right (the canvas reads source-on-the-left,
 * sink-on-the-right), and the tween is hand-rolled via
 * requestAnimationFrame so the user sees blocks slide into place
 * instead of teleporting after a Tidy click.
 *
 * Cycle handling: a DAG check is the caller's responsibility — if a
 * cycle slips through dagre simply reports a partial layout and the
 * remaining nodes stay put.
 */

const NODE_W = 180;
const NODE_H = 110;

function _ensureDagre() {
  return typeof window !== 'undefined' && typeof window.dagre !== 'undefined';
}

export function computeLayout(nodes, edges, opts = {}) {
  if (!_ensureDagre()) return {};
  const g = new window.dagre.graphlib.Graph();
  g.setGraph({
    rankdir: opts.rankdir || 'LR',
    ranksep: opts.ranksep || 80,
    nodesep: opts.nodesep || 40,
    marginx: 20,
    marginy: 20,
  });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_W, height: NODE_H });
  }
  for (const e of edges) {
    g.setEdge(e.source_node_id, e.target_node_id);
  }
  window.dagre.layout(g);
  const out = {};
  for (const id of g.nodes()) {
    const node = g.node(id);
    if (!node) continue;
    out[id] = {
      x: Math.round(node.x - NODE_W / 2),
      y: Math.round(node.y - NODE_H / 2),
    };
  }
  return out;
}

function _easeInOutQuad(t) {
  return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
}

function _setNodePos(df, dfId, x, y) {
  // Drawflow stores position in two places: the in-memory model
  // (`drawflow.Home.data[id].pos_x/y`) and the DOM element's inline
  // top/left.  Update both, then call `updateConnectionNodes` so the
  // SVG connection paths follow.
  const data = df.drawflow && df.drawflow.drawflow && df.drawflow.drawflow.Home;
  if (data && data.data && data.data[dfId]) {
    data.data[dfId].pos_x = x;
    data.data[dfId].pos_y = y;
  }
  const el = df.container.querySelector(`#node-${dfId}`);
  if (el) {
    el.style.top = `${y}px`;
    el.style.left = `${x}px`;
  }
  if (typeof df.updateConnectionNodes === 'function') {
    df.updateConnectionNodes('node-' + dfId);
  }
}

export function animateTo(df, drawflowIdByPqlId, currentPositions, targets, durationMs = 250) {
  return new Promise((resolve) => {
    const start = performance.now();
    const startPos = {};
    for (const [pqlId, pos] of Object.entries(currentPositions)) {
      startPos[pqlId] = { x: pos.x || 0, y: pos.y || 0 };
    }
    function tick(now) {
      const elapsed = Math.min(now - start, durationMs);
      const t = _easeInOutQuad(elapsed / durationMs);
      for (const [pqlId, target] of Object.entries(targets)) {
        const dfId = drawflowIdByPqlId[pqlId];
        if (dfId == null) continue;
        const sx = (startPos[pqlId] && startPos[pqlId].x) || 0;
        const sy = (startPos[pqlId] && startPos[pqlId].y) || 0;
        const x = Math.round(sx + (target.x - sx) * t);
        const y = Math.round(sy + (target.y - sy) * t);
        _setNodePos(df, dfId, x, y);
      }
      if (elapsed < durationMs) {
        window.requestAnimationFrame(tick);
      } else {
        resolve();
      }
    }
    window.requestAnimationFrame(tick);
  });
}
