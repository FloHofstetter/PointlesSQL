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
};
