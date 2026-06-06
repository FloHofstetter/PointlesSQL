/*
 * Viewport controls for the canvas editor.
 *
 * Zoom (fit-to-view, reset-to-100%), the collapsible minimap with its
 * click/drag pan, the node-search popover, and the compact-body toggle —
 * everything that changes which slice of the graph is on screen without
 * mutating the graph itself.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const viewportMethods = {
  fitToView() {
    const df = this._drawflow;
    if (!df) return;
    const nodes = Object.values(this.nodes);
    if (nodes.length === 0) return;
    const NODE_W = 180;
    const NODE_H = 110;
    const PAD = 60;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const [pqlId, n] of Object.entries(this.nodes)) {
      const p = n.position || { x: 100, y: 100 };
      // Prefer the live DOM box so the fit accounts for nodes that have
      // grown a schema/row-count body; fall back to the saved position
      // plus a nominal size before the node has rendered.
      const dfId = this._drawflowNodes[pqlId];
      const el = dfId && df.container.querySelector(`#node-${dfId}`);
      const x0 = el ? el.offsetLeft : p.x;
      const y0 = el ? el.offsetTop : p.y;
      const w = el ? el.offsetWidth : NODE_W;
      const h = el ? el.offsetHeight : NODE_H;
      if (x0 < minX) minX = x0;
      if (y0 < minY) minY = y0;
      if (x0 + w > maxX) maxX = x0 + w;
      if (y0 + h > maxY) maxY = y0 + h;
    }
    const spanX = Math.max(maxX - minX, 1);
    const spanY = Math.max(maxY - minY, 1);
    const rect = df.container.getBoundingClientRect();
    const fitW = Math.max(rect.width - PAD * 2, 100);
    const fitH = Math.max(rect.height - PAD * 2, 100);
    // Keep node bodies legible: a wide linear pipeline would otherwise fit at
    // a zoom so small (~0.4) that the schema/row-count text is unreadable and
    // most of the stage is empty.  Floor the fit zoom and let the user pan /
    // use the minimap for the overflow.
    const MIN_FIT_ZOOM = 0.5;
    const rawZoom = Math.min(fitW / spanX, fitH / spanY, 1);
    const zoom = Math.max(rawZoom, MIN_FIT_ZOOM);
    df.zoom = zoom;
    if (zoom > rawZoom + 1e-6) {
      // The floor kicked in, so the graph is too big to fit at a legible
      // zoom.  Anchor to its top-left (with padding) instead of centring —
      // centring a graph larger than the viewport clips both ends, whereas
      // top-left keeps the pipeline's source nodes in view to pan from.
      df.canvas_x = PAD - minX * zoom;
      df.canvas_y = PAD - minY * zoom;
    } else {
      // Small DAG: centre its bounding box so it sits in the middle of the
      // canvas rather than hugging the palette edge.
      df.canvas_x = (rect.width - spanX * zoom) / 2 - minX * zoom;
      df.canvas_y = (rect.height - spanY * zoom) / 2 - minY * zoom;
    }
    const precanvas = df.precanvas;
    if (precanvas) {
      precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${zoom})`;
    }
    // Drawflow computes connection endpoints in a zoom-dependent basis, so
    // changing df.zoom without recomputing leaves every wire pinned to its
    // pre-fit coordinates (the connections float away from their nodes).
    // CSS-transform changes don't trip the node ResizeObserver, so sweep
    // explicitly here.
    this._scheduleConnNodeUpdate();
    this._scheduleMinimapRender();
    this._scheduleRerouteOrthogonal();
  },
  zoomReset100() {
    // Reset to 1:1 zoom, keeping the current viewport centre fixed.
    const df = this._drawflow;
    if (!df || typeof df.canvas_x === 'undefined') return;
    const rect = df.container.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const factor = 1 / (df.zoom || 1);
    df.canvas_x = cx - (cx - df.canvas_x) * factor;
    df.canvas_y = cy - (cy - df.canvas_y) * factor;
    df.zoom = 1;
    df.precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(1)`;
    this._scheduleConnNodeUpdate();
    this._scheduleMinimapRender();
  },
  toggleCompactBodies() {
    this.compactBodies = !this.compactBodies;
    const wrap = this.$refs.canvas;
    if (wrap) wrap.classList.toggle('pql-canvas-compact', this.compactBodies);
  },
  openSearch() {
    this.searchOpen = true;
    this.searchQuery = '';
    this.searchCursor = 0;
    this.$nextTick(() => {
      const el = this.$refs.searchInput;
      if (el) el.focus();
    });
  },
  closeSearch() {
    this.searchOpen = false;
  },
  searchMatches() {
    const q = (this.searchQuery || '').toLowerCase().trim();
    const all = Object.values(this.nodes);
    if (!q) return all.slice(0, 20);
    return all
      .filter(
        (n) => n.block_type.toLowerCase().includes(q) || (n.id || '').toLowerCase().includes(q)
      )
      .slice(0, 20);
  },
  searchNavigate(direction) {
    const matches = this.searchMatches();
    if (matches.length === 0) return;
    this.searchCursor = (this.searchCursor + direction + matches.length) % matches.length;
  },
  searchSelectMatch() {
    const matches = this.searchMatches();
    const target = matches[this.searchCursor];
    if (!target) return;
    const dfId = this._drawflowNodes[target.id];
    if (dfId == null) return;
    const df = this._drawflow;
    if (df && typeof df.canvas_x !== 'undefined') {
      const pos = target.position || { x: 100, y: 100 };
      const containerRect = df.container.getBoundingClientRect();
      df.canvas_x = -pos.x * df.zoom + containerRect.width / 2;
      df.canvas_y = -pos.y * df.zoom + containerRect.height / 2;
      const precanvas = df.precanvas;
      if (precanvas) {
        precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${df.zoom})`;
      }
    }
    this.selectedNodeId = target.id;
    this.closeSearch();
  },
  toggleMinimap() {
    this.minimapVisible = !this.minimapVisible;
    try {
      if (this.minimapVisible) {
        localStorage.removeItem('pql.canvas.minimap.collapsed');
      } else {
        localStorage.setItem('pql.canvas.minimap.collapsed', '1');
      }
    } catch (_e) {
      // localStorage disabled — visibility still toggles per-session.
    }
    if (this.minimapVisible) this._scheduleMinimapRender();
  },
  _scheduleMinimapRender() {
    if (!this.minimapVisible) return;
    if (this._minimapRafHandle != null) return;
    this._minimapRafHandle = window.requestAnimationFrame(() => {
      this._minimapRafHandle = null;
      this._renderMinimap();
    });
  },
  _renderMinimap() {
    const host = this.$refs.minimap;
    if (!host) return;
    const W = 200;
    const H = 130;
    const PAD = 6;
    const nodes = Object.values(this.nodes);
    if (nodes.length === 0) {
      host.innerHTML = `<svg width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="var(--bs-tertiary-bg)" stroke="var(--bs-border-color)" /></svg>`;
      return;
    }
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const n of nodes) {
      const p = n.position || { x: 100, y: 100 };
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    const NODE_W = 160;
    const NODE_H = 80;
    maxX += NODE_W;
    maxY += NODE_H;
    const spanX = Math.max(maxX - minX, 1);
    const spanY = Math.max(maxY - minY, 1);
    const scale = Math.min((W - PAD * 2) / spanX, (H - PAD * 2) / spanY);
    // Remember the canvas-local → minimap mapping so the click/drag-pan
    // handler can invert it.
    this._minimapTransform = { minX, minY, scale, PAD, W, H };
    const rects = nodes
      .map((n) => {
        const p = n.position || { x: 100, y: 100 };
        const x = PAD + (p.x - minX) * scale;
        const y = PAD + (p.y - minY) * scale;
        const w = NODE_W * scale;
        const h = NODE_H * scale;
        const fill = n.id === this.selectedNodeId ? 'var(--bs-primary)' : 'var(--bs-secondary)';
        return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${fill}" />`;
      })
      .join('');
    // Viewport rectangle — the slice of the canvas currently on screen,
    // derived from the precanvas transform (origin 0 0): screen 0 maps to
    // canvas-local -canvas_x/zoom, and the visible span is container/zoom.
    let viewport = '';
    const df = this._drawflow;
    if (df && typeof df.canvas_x !== 'undefined' && df.zoom) {
      const rect = df.container.getBoundingClientRect();
      const vlX = -df.canvas_x / df.zoom;
      const vlY = -df.canvas_y / df.zoom;
      const vW = rect.width / df.zoom;
      const vH = rect.height / df.zoom;
      const rx = PAD + (vlX - minX) * scale;
      const ry = PAD + (vlY - minY) * scale;
      const rw = vW * scale;
      const rh = vH * scale;
      viewport =
        `<rect x="${rx.toFixed(1)}" y="${ry.toFixed(1)}" width="${rw.toFixed(1)}" height="${rh.toFixed(1)}" ` +
        'fill="var(--bs-primary)" fill-opacity="0.12" stroke="var(--bs-primary)" stroke-width="1.5" pointer-events="none" />';
    }
    host.innerHTML =
      `<svg width="${W}" height="${H}" style="cursor: pointer;">` +
      `<rect width="${W}" height="${H}" fill="var(--bs-tertiary-bg)" stroke="var(--bs-border-color)" />` +
      rects +
      viewport +
      '</svg>';
  },
  _minimapPanTo(offsetX, offsetY) {
    // Centre the viewport on the canvas-local point under the minimap
    // cursor.  Pan is a pure translate (transform-origin 0 0) so no
    // connection recompute is needed — only zoom changes affect local
    // endpoint coords.
    const t = this._minimapTransform;
    const df = this._drawflow;
    if (!t || !df || typeof df.canvas_x === 'undefined') return;
    const localX = t.minX + (offsetX - t.PAD) / t.scale;
    const localY = t.minY + (offsetY - t.PAD) / t.scale;
    const rect = df.container.getBoundingClientRect();
    df.canvas_x = -localX * df.zoom + rect.width / 2;
    df.canvas_y = -localY * df.zoom + rect.height / 2;
    df.precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${df.zoom})`;
    this._scheduleMinimapRender();
  },
  minimapPointerDown(ev) {
    ev.preventDefault();
    const host = this.$refs.minimap;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const toLocal = (e) => this._minimapPanTo(e.clientX - rect.left, e.clientY - rect.top);
    toLocal(ev);
    const move = (e) => toLocal(e);
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  },
};
