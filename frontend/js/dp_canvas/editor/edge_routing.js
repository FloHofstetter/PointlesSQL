/*
 * Orthogonal edge routing for the canvas editor.
 *
 * The right-angle edge mode (curvature 0) plus an obstacle-aware post-pass
 * that reroutes each connection's path around intervening node boxes —
 * Drawflow's own path generator only sees the two endpoints.  Smooth bezier
 * mode is untouched.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const edgeRoutingMethods = {
  toggleOrthogonalEdges() {
    this.orthogonalEdges = !this.orthogonalEdges;
    const df = this._drawflow;
    if (!df) return;
    df.curvature = this.orthogonalEdges ? 0 : 0.5;
    // Drawflow's updateConnectionNodes() emits nodeMoved internally for
    // every connected node, which would cascade into autosave + minimap
    // re-render.  Suppress autosave around the visual-only rewrite.
    const wasSuppressed = this._suppressAutosave;
    this._suppressAutosave = true;
    try {
      for (const dfId of Object.values(this._drawflowNodes)) {
        df.updateConnectionNodes('node-' + dfId);
      }
    } finally {
      this._suppressAutosave = wasSuppressed;
    }
    this._scheduleRerouteOrthogonal();
  },
  // ---------------------------------------------------------------------
  // Obstacle-aware orthogonal routing.  Drawflow's createCurvature only
  // sees the two endpoints, so the step path it draws can run straight
  // through intervening nodes.  In orthogonal mode only, this post-pass
  // rewrites each connection's `d` to route around the other nodes' boxes:
  // it first looks for a clear vertical corridor between the pins, then
  // falls back to a detour over/under the blocking band.  Smooth (bézier)
  // mode is untouched.
  // ---------------------------------------------------------------------

  _scheduleRerouteOrthogonal() {
    if (!this.orthogonalEdges) return;
    if (this._rerouteRaf) return;
    this._rerouteRaf = window.setTimeout(() => {
      this._rerouteRaf = null;
      this._rerouteOrthogonalEdges();
    }, 0);
  },
  _nodeBoxes(excludeDfIds) {
    const df = this._drawflow;
    const boxes = [];
    for (const dfId of Object.values(this._drawflowNodes)) {
      if (excludeDfIds.has(String(dfId))) continue;
      const el = df.container.querySelector(`#node-${dfId}`);
      if (!el) continue;
      boxes.push({ x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
    }
    return boxes;
  },
  _orthogonalPath(sx, sy, ex, ey, boxes, STUB, GAP) {
    // Does an axis-aligned segment (inflated by GAP) intersect any box?
    const hit = (x0, y0, x1, y1) => {
      const xmin = Math.min(x0, x1);
      const xmax = Math.max(x0, x1);
      const ymin = Math.min(y0, y1);
      const ymax = Math.max(y0, y1);
      return boxes.some(
        (b) =>
          xmax > b.x - GAP && xmin < b.x + b.w + GAP && ymax > b.y - GAP && ymin < b.y + b.h + GAP
      );
    };
    // 1) Plain H-V-H midpoint path, if all three segments are clear.
    const midX = sx + (ex - sx) / 2;
    if (!hit(sx, sy, midX, sy) && !hit(midX, sy, midX, ey) && !hit(midX, ey, ex, ey)) {
      return ` M ${sx} ${sy} L ${midX} ${sy} L ${midX} ${ey} L ${ex} ${ey}`;
    }
    // 2) Detour over / under the band of boxes spanning the horizontal gap.
    const band = boxes.filter(
      (b) => b.x + b.w + GAP > Math.min(sx, ex) && b.x - GAP < Math.max(sx, ex)
    );
    if (band.length) {
      const top = Math.min(...band.map((b) => b.y)) - GAP;
      const bot = Math.max(...band.map((b) => b.y + b.h)) + GAP;
      const useTop =
        Math.abs(top - sy) + Math.abs(top - ey) <= Math.abs(bot - sy) + Math.abs(bot - ey);
      const clearY = useTop ? top : bot;
      const so = sx + STUB;
      const eo = ex - STUB;
      return (
        ` M ${sx} ${sy} L ${so} ${sy} L ${so} ${clearY}` +
        ` L ${eo} ${clearY} L ${eo} ${ey} L ${ex} ${ey}`
      );
    }
    // 3) Nothing to avoid — plain midpoint split.
    return ` M ${sx} ${sy} L ${midX} ${sy} L ${midX} ${ey} L ${ex} ${ey}`;
  },
  _rerouteOrthogonalEdges() {
    const df = this._drawflow;
    if (!df || !this.orthogonalEdges) return;
    const STUB = 24;
    const GAP = 18;
    const conns = df.container.querySelectorAll('.drawflow .connection');
    for (const conn of conns) {
      const mp = conn.querySelector('.main-path');
      if (!mp) continue;
      const d = mp.getAttribute('d') || '';
      if (d.indexOf('C') !== -1) continue; // bézier — skip
      const nums = d.match(/-?\d+(?:\.\d+)?/g);
      if (!nums || nums.length < 4) continue;
      const sx = parseFloat(nums[0]);
      const sy = parseFloat(nums[1]);
      const ex = parseFloat(nums[nums.length - 2]);
      const ey = parseFloat(nums[nums.length - 1]);
      let srcDf = null;
      let tgtDf = null;
      for (const cls of conn.classList) {
        const inM = cls.match(/^node_in_node-(\d+)$/);
        const outM = cls.match(/^node_out_node-(\d+)$/);
        if (inM) tgtDf = inM[1];
        if (outM) srcDf = outM[1];
      }
      const exclude = new Set([srcDf, tgtDf].filter(Boolean));
      const newD = this._orthogonalPath(sx, sy, ex, ey, this._nodeBoxes(exclude), STUB, GAP);
      if (newD) mp.setAttribute('d', newD);
    }
  },
};
