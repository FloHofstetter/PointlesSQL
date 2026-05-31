/*
 * Tiny canvas-diff viewer.
 *
 * Reads ?from=N&to=M from the URL, populates two version pickers, and
 * renders the structured diff returned by GET /api/dp/{id}/canvas/diff
 * as three colour-coded columns (added / removed / modified).
 */

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

    async init() {
      this.fromVersion = _readQuery('from');
      this.toVersion = _readQuery('to');
      const res = await window.pqlApi.fetch(
        `/api/dp/${this.product.id}/canvas/versions`,
        { silent: true },
      );
      if (res.ok) {
        this.versions = (res.data.versions || []).map((v) => v.version);
        if (!this.fromVersion || !this.versions.includes(this.fromVersion)) {
          this.fromVersion = this.versions[this.versions.length - 1] || null;
        }
        if (!this.toVersion || !this.versions.includes(this.toVersion)) {
          this.toVersion = this.versions[0] || null;
        }
      }
      if (this.fromVersion && this.toVersion) {
        await this.load();
      }
    },

    diffEmpty() {
      const d = this.diff && this.diff.diff;
      if (!d) return true;
      return !(
        d.added_nodes.length
        || d.removed_nodes.length
        || d.modified_nodes.length
        || d.added_edges.length
        || d.removed_edges.length
      );
    },

    async load() {
      if (this.busy) return;
      if (!this.fromVersion || !this.toVersion) {
        this.error = 'Pick from + to versions';
        return;
      }
      this.busy = true;
      this.error = null;
      const url = `/api/dp/${this.product.id}/canvas/diff`
        + `?from_version=${this.fromVersion}&to_version=${this.toVersion}`;
      const res = await window.pqlApi.fetch(url, { silent: true });
      this.busy = false;
      if (!res.ok) {
        this.error = res.error || 'diff failed';
        return;
      }
      this.diff = res.data;
    },
  };
}
