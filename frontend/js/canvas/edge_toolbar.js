/*
 * Mid-edge toolbar for the canvas editor.
 *
 * The small floating toolbar that appears at a hovered / selected edge's
 * midpoint: select / clear an edge, show / hide with a forgiveness delay,
 * and reposition it as the connected nodes move.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const edgeToolbarMethods = {
  _selectEdge(edgeId) {
    this._clearSelectedEdge();
    this._selectedEdgeId = edgeId;
    const df = this._drawflow;
    if (!df) return;
    const svgs = df.container.querySelectorAll('.drawflow .connection');
    for (const svg of svgs) {
      if (this._edgeIdForSvg(svg) === edgeId) {
        svg.classList.add('pql-edge-selected');
      }
    }
  },
  _clearSelectedEdge() {
    this._selectedEdgeId = null;
    const df = this._drawflow;
    if (!df) return;
    const svgs = df.container.querySelectorAll('.drawflow .connection.pql-edge-selected');
    for (const svg of svgs) svg.classList.remove('pql-edge-selected');
  },
  _showEdgeToolbar(svgEl, edgeId) {
    this._cancelEdgeToolbarHide();
    this._edgeToolbarTarget = { svgEl, edgeId };
    this.edgeToolbar = { ...this.edgeToolbar, edgeId, visible: true };
    this._updateEdgeToolbarPosition();
  },
  _scheduleEdgeToolbarReposition() {
    if (!this.edgeToolbar.visible) return;
    if (this._edgeToolbarRaf) return;
    this._edgeToolbarRaf = window.setTimeout(() => {
      this._edgeToolbarRaf = null;
      this._updateEdgeToolbarPosition();
    }, 0);
  },
  _updateEdgeToolbarPosition() {
    const target = this._edgeToolbarTarget;
    if (!target || !target.svgEl) return;
    const path = target.svgEl.querySelector('.main-path');
    if (!path) return;
    let mid;
    try {
      const len = path.getTotalLength();
      mid = path.getPointAtLength(len / 2);
    } catch (_e) {
      // Some browsers throw if the path is unrendered (zero-length).
      return;
    }
    // Translate from SVG-local coords to the stage's positioned ancestor.
    const stage = this.$refs.canvas.parentElement;
    const svgRect = target.svgEl.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    const x = svgRect.left - stageRect.left + mid.x;
    const y = svgRect.top - stageRect.top + mid.y;
    this.edgeToolbar = { ...this.edgeToolbar, x, y };
  },
  _scheduleEdgeToolbarHide() {
    this._cancelEdgeToolbarHide();
    // 600 ms exit-delay — same forgiveness window n8n uses so the user
    // can dart the cursor across the edge into the toolbar without it
    // vanishing mid-flight.
    this._edgeToolbarHideTimer = window.setTimeout(() => this._hideEdgeToolbar(), 600);
  },
  _cancelEdgeToolbarHide() {
    if (this._edgeToolbarHideTimer) {
      window.clearTimeout(this._edgeToolbarHideTimer);
      this._edgeToolbarHideTimer = null;
    }
  },
  _hideEdgeToolbar() {
    this._cancelEdgeToolbarHide();
    this.edgeToolbar = { visible: false, x: 0, y: 0, edgeId: null };
    this._edgeToolbarTarget = null;
  },
};
