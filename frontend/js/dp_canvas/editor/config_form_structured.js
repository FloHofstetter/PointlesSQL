/*
 * Generic config-field editors shared across the per-block settings forms.
 *
 * The drawer forms used to carry one bespoke add/remove method per chip-list
 * (columns, join keys, group keys, merge keys) and inline split/join logic per
 * comma field.  These generic helpers — keyed on the config field name — let
 * the `_form_macros.html` chip_list / comma_list macros drive every list field
 * through a single code path, so a new block reuses them for free.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const configFormStructuredMethods = {
  // --- UC table name split into catalog / schema / table ----------------
  // The block keeps a single dotted ``catalog.schema.table`` config key
  // (table_fqn / materialized_table) so the backend FQN contract is
  // unchanged; the drawer just presents it as three fields, derived from
  // the stored value on every render and reassembled on edit.

  fqnParts(node, key) {
    const raw = String((node && node.config && node.config[key]) || '');
    const parts = raw.split('.');
    return {
      catalog: parts[0] || '',
      schema: parts[1] || '',
      // Keep any stray dots with the table segment rather than dropping them.
      table: parts.slice(2).join('.') || '',
    };
  },
  setFqnPart(node, key, part, value) {
    if (!node) return;
    const cur = this.fqnParts(node, key);
    cur[part] = String(value == null ? '' : value).trim();
    // A half-filled name reassembles to e.g. "main.." which _FQN_RE rejects,
    // so the inline error panel flags it instead of silently accepting it.
    node.config[key] = [cur.catalog, cur.schema, cur.table].join('.');
    this.onConfigChanged();
  },

  // --- Array (chip / comma) list fields ----------------------------------

  addColumnTo(field, col, opts) {
    const unique = !opts || opts.unique !== false;
    const node = this.selectedNode;
    if (!node) return;
    const trimmed = String(col == null ? '' : col).trim();
    if (!trimmed) return;
    if (!Array.isArray(node.config[field])) node.config[field] = [];
    if (unique && node.config[field].includes(trimmed)) return;
    node.config[field].push(trimmed);
    this.onConfigChanged();
  },
  removeColumnFrom(field, idx) {
    const node = this.selectedNode;
    if (!node || !Array.isArray(node.config[field])) return;
    node.config[field].splice(idx, 1);
    this.onConfigChanged();
  },
  commaValue(field) {
    const node = this.selectedNode;
    const arr = (node && node.config && node.config[field]) || [];
    return Array.isArray(arr) ? arr.join(', ') : '';
  },
  setCommaList(field, raw) {
    const node = this.selectedNode;
    if (!node) return;
    node.config[field] = String(raw || '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    this.onConfigChanged();
  },

  // --- Sort: rows of {column, direction} --------------------------------

  initSortRows() {
    const node = this.selectedNode;
    if (!node) return;
    if (!Array.isArray(node.config.order_by)) node.config.order_by = [];
    // Older docs may hold bare-string entries; normalise to objects so the
    // row editor can bind both cells (the backend accepts either shape).
    node.config.order_by = node.config.order_by.map((e) =>
      typeof e === 'string' ? { column: e, direction: 'asc' } : e
    );
  },
  addSortKey() {
    const node = this.selectedNode;
    if (!node) return;
    if (!Array.isArray(node.config.order_by)) node.config.order_by = [];
    node.config.order_by.push({ column: '', direction: 'asc' });
    this.onConfigChanged();
  },
  addSortColumn(col) {
    const node = this.selectedNode;
    const name = String(col == null ? '' : col).trim();
    if (!node || !name) return;
    if (!Array.isArray(node.config.order_by)) node.config.order_by = [];
    node.config.order_by.push({ column: name, direction: 'asc' });
    this.onConfigChanged();
  },
  removeSortKey(idx) {
    const node = this.selectedNode;
    if (!node || !Array.isArray(node.config.order_by)) return;
    node.config.order_by.splice(idx, 1);
    this.onConfigChanged();
  },

  // --- Cast: rows of {column, target_type} ------------------------------

  addCast() {
    const node = this.selectedNode;
    if (!node) return;
    if (!Array.isArray(node.config.casts)) node.config.casts = [];
    node.config.casts.push({ column: '', target_type: '' });
    this.onConfigChanged();
  },
  addCastColumn(col) {
    const node = this.selectedNode;
    const name = String(col == null ? '' : col).trim();
    if (!node || !name) return;
    if (!Array.isArray(node.config.casts)) node.config.casts = [];
    node.config.casts.push({ column: name, target_type: '' });
    this.onConfigChanged();
  },
  removeCast(idx) {
    const node = this.selectedNode;
    if (!node || !Array.isArray(node.config.casts)) return;
    node.config.casts.splice(idx, 1);
    this.onConfigChanged();
  },

  // --- Rename: a {old: new} MAP edited through a transient row buffer ----
  // The buffer (renameRowsBuf, a component field) is the editing surface;
  // syncRenames() rebuilds config.renames from it on every change.  The
  // buffer never persists — the save document carries only node.config.

  initRenameRows() {
    const node = this.selectedNode;
    this.renameRowsBuf = node
      ? Object.entries(node.config.renames || {}).map(([from, to]) => ({
          from,
          to: String(to),
        }))
      : [];
  },
  addRename() {
    this.renameRowsBuf.push({ from: '', to: '' });
    this.syncRenames();
  },
  removeRename(idx) {
    this.renameRowsBuf.splice(idx, 1);
    this.syncRenames();
  },
  syncRenames() {
    const node = this.selectedNode;
    if (!node) return;
    const map = {};
    for (const r of this.renameRowsBuf) {
      const from = String(r.from || '').trim();
      if (from) map[from] = String(r.to || '');
    }
    node.config.renames = map;
    this.onConfigChanged();
  },
};
