/*
 * Right-drawer config form for a scheduler task node.
 *
 * Block label / icon / help lookups (through the injected catalog) plus the
 * task ``params`` JSON editor.  Name + retry fields bind straight to
 * ``selectedNode.config`` via ``x-model``; the deep watcher set up in the
 * lifecycle fires ``onConfigChanged`` (shared) on every edit so autosave +
 * validate run uniformly.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const schedulerConfigFormMethods = {
  blockLabel(kind) {
    const def = this.catalog.BLOCK_DEFS[kind];
    return (def && def.label) || kind;
  },
  blockIcon(kind) {
    const def = this.catalog.BLOCK_DEFS[kind];
    return (def && def.icon) || 'bi-gear';
  },
  blockHelp(kind) {
    const def = this.catalog.BLOCK_DEFS[kind];
    return (def && def.help) || '';
  },
  // Pretty-printed params JSON for the textarea.
  paramsText() {
    const node = this.selectedNode;
    if (!node) return '';
    try {
      return JSON.stringify(node.config.params || {}, null, 2);
    } catch (_e) {
      return '{}';
    }
  },
  updateParams(text) {
    const node = this.selectedNode;
    if (!node) return;
    try {
      const parsed = JSON.parse(text || '{}');
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        node.config.params = parsed;
        this.paramsError = null;
        this.onConfigChanged();
      } else {
        this.paramsError = 'params must be a JSON object';
      }
    } catch (_e) {
      this.paramsError = 'invalid JSON';
    }
  },
};
