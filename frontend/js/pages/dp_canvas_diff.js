/*
 * Canvas-diff viewer.
 *
 * Reads ?from=N&to=M from the URL, populates two version pickers, and
 * renders the structured diff returned by GET /api/dp/{id}/canvas/diff
 * in one of two modes:
 *
 * - "list":   three colour-coded columns (added / removed / modified)
 *             with JSON-config diffs per node.  Original v1 shape.
 * - "visual": side-by-side read-only Drawflow editors holding the
 *             before + after canvases.  Modified nodes get a yellow
 *             outline, added a green one, removed a red one (on the
 *             after-pane).  Edges follow the same colour rules.
 *
 * "visual" is the default for new sessions; the toggle on the page
 * persists per-tab via the same Alpine state.
 */

import { loadCanvasIntoDrawflow } from '../dp_canvas/_drawflow_loader.js';

function _readQuery(name) {
  const u = new URL(window.location.href);
  const raw = u.searchParams.get(name);
  return raw ? parseInt(raw, 10) : null;
}

export function dpCanvasDiff(product) {
  return {
    product,
    versions: [],
    fromVersion: null,
    toVersion: null,
    diff: null,
    busy: false,
    error: null,
    viewMode: 'visual',
    onlyChanged: false,
    _dfBefore: null,
    _dfAfter: null,
    _syncingScroll: false,

    async init() {
      this.fromVersion = _readQuery('from');
      this.toVersion = _readQuery('to');
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/versions`, {
        silent: true,
      });
      if (res.ok) {
        this.versions = (res.data.versions || []).map((v) => v.version);
        if (!this.fromVersion || !this.versions.includes(this.fromVersion)) {
          this.fromVersion = this.versions[this.versions.length - 1] || null;
        }
        if (!this.toVersion || !this.versions.includes(this.toVersion)) {
          this.toVersion = this.versions[0] || null;
        }
      }
      this.$nextTick(() => {
        const selects = this.$el.querySelectorAll('select');
        if (selects[0]) selects[0].value = String(this.fromVersion ?? '');
        if (selects[1]) selects[1].value = String(this.toVersion ?? '');
      });
      if (this.fromVersion && this.toVersion) {
        await this.load();
      }
      // Re-paint the visual panes when the view mode flips into 'visual'
      // (Drawflow refuses to lay out into hidden divs, so we lazy-mount).
      this.$watch('viewMode', (v) => {
        if (v === 'visual' && this.diff) {
          this.$nextTick(() => this._renderVisual());
        }
      });
    },

    diffEmpty() {
      const d = this.diff && this.diff.diff;
      if (!d) return true;
      return !(
        d.added_nodes.length ||
        d.removed_nodes.length ||
        d.modified_nodes.length ||
        d.added_edges.length ||
        d.removed_edges.length ||
        (d.modified_edges || []).length
      );
    },

    toggleOnlyChanged() {
      this.onlyChanged = !this.onlyChanged;
      const beforeHost = this.$refs.dfBefore;
      const afterHost = this.$refs.dfAfter;
      if (beforeHost) beforeHost.classList.toggle('pql-diff-only-changed', this.onlyChanged);
      if (afterHost) afterHost.classList.toggle('pql-diff-only-changed', this.onlyChanged);
    },

    async load() {
      if (this.busy) return;
      if (!this.fromVersion || !this.toVersion) {
        this.error = 'Pick from + to versions';
        return;
      }
      this.busy = true;
      this.error = null;
      const url =
        `/api/dp/${this.product.id}/canvas/diff` +
        `?from_version=${this.fromVersion}&to_version=${this.toVersion}`;
      const res = await window.pqlApi.fetch(url, { silent: true });
      this.busy = false;
      if (!res.ok) {
        this.error = res.error || 'diff failed';
        return;
      }
      this.diff = res.data;
      if (this.viewMode === 'visual') {
        this.$nextTick(() => this._renderVisual());
      }
    },

    async _renderVisual() {
      if (!this.diff || this.diffEmpty()) return;
      if (typeof window.Drawflow !== 'function') {
        await new Promise((resolve) => setTimeout(resolve, 80));
      }
      if (typeof window.Drawflow !== 'function') return;
      // Pull both saved docs so we have full nodes/edges to render in
      // each Drawflow pane.  The diff endpoint only carries the delta;
      // the full doc per version comes from the existing versions/{N}
      // route.
      const fromVer = this.diff.from_version;
      const toVer = this.diff.to_version;
      const [beforeRes, afterRes] = await Promise.all([
        window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/versions/${fromVer}`, {
          silent: true,
        }),
        window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/versions/${toVer}`, {
          silent: true,
        }),
      ]);
      if (!beforeRes.ok || !afterRes.ok) {
        this.error = 'failed to load full canvas docs for visual diff';
        return;
      }
      const beforeDoc = beforeRes.data.document;
      const afterDoc = afterRes.data.document;
      const beforeHost = this.$refs.dfBefore;
      const afterHost = this.$refs.dfAfter;
      if (!beforeHost || !afterHost) return;
      if (!this._dfBefore) {
        this._dfBefore = new window.Drawflow(beforeHost);
        this._dfBefore.editor_mode = 'view';
        this._dfBefore.reroute = true;
        this._dfBefore.start();
      }
      if (!this._dfAfter) {
        this._dfAfter = new window.Drawflow(afterHost);
        this._dfAfter.editor_mode = 'view';
        this._dfAfter.reroute = true;
        this._dfAfter.start();
      }
      const beforeIds = loadCanvasIntoDrawflow(this._dfBefore, beforeDoc);
      const afterIds = loadCanvasIntoDrawflow(this._dfAfter, afterDoc);
      this._applyNodeOverlays(beforeHost, beforeIds, 'before');
      this._applyNodeOverlays(afterHost, afterIds, 'after');
      this._applyEdgeOverlays(beforeHost, beforeDoc, 'before');
      this._applyEdgeOverlays(afterHost, afterDoc, 'after');
      this._wireSyncScroll(beforeHost, afterHost);
      if (this.onlyChanged) {
        beforeHost.classList.add('pql-diff-only-changed');
        afterHost.classList.add('pql-diff-only-changed');
      }
    },

    _wireSyncScroll(beforeHost, afterHost) {
      const mirror = (src, dst) => () => {
        if (this._syncingScroll) return;
        this._syncingScroll = true;
        try {
          dst.scrollTop = src.scrollTop;
          dst.scrollLeft = src.scrollLeft;
        } finally {
          this._syncingScroll = false;
        }
      };
      beforeHost.addEventListener('scroll', mirror(beforeHost, afterHost));
      afterHost.addEventListener('scroll', mirror(afterHost, beforeHost));
    },

    _applyNodeOverlays(hostEl, drawflowIds, side) {
      const diff = this.diff.diff;
      const cls = (pqlId, className) => {
        const dfId = drawflowIds[pqlId];
        if (!dfId) return;
        const el = hostEl.querySelector(`#node-${dfId}`);
        if (!el) return;
        el.classList.add(className);
      };
      if (side === 'after') {
        for (const n of diff.added_nodes) cls(n.id, 'pql-diff-added');
      }
      if (side === 'before') {
        for (const n of diff.removed_nodes) cls(n.id, 'pql-diff-removed');
      }
      for (const n of diff.modified_nodes) cls(n.id, 'pql-diff-modified');
    },

    _applyEdgeOverlays(hostEl, doc, side) {
      const diff = this.diff.diff;
      const matchKey = (e) =>
        `${e.source_node_id}|${e.source_pin}|${e.target_node_id}|${e.target_pin}`;
      const docEdges = doc.edges || [];
      const conns = hostEl.querySelectorAll('.connection');

      const sideDelta = side === 'after' ? diff.added_edges : diff.removed_edges;
      const sideCls = side === 'after' ? 'pql-diff-edge-added' : 'pql-diff-edge-removed';
      const sideKeys = new Set(sideDelta.map(matchKey));
      const modKeys = new Set((diff.modified_edges || []).map(matchKey));

      docEdges.forEach((e, idx) => {
        const conn = conns[idx];
        if (!conn) return;
        const k = matchKey(e);
        if (sideKeys.has(k)) {
          conn.classList.add(sideCls);
        }
        if (modKeys.has(k)) {
          conn.classList.add('pql-diff-edge-modified');
        }
      });
    },
  };
}
