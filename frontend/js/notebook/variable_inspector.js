/**
 * Notebook editor — Variable Inspector mixin.
 *
 * Owns the inspector's snapshot/detail probes (silent execute against
 * the kernel) plus the toggle that surfaces the inspector tab in the
 * right drawer.  Frame-dispatch handlers (`_onVariableSnapshot`,
 * `_onVariableDetail`) live here so the kernel-execution dispatcher
 * can re-trigger a snapshot after every user-driven run without
 * owning the inspector state itself.
 *
 * State slots (`inspectorVars`, `inspectorDetail`, `inspectorDetailFor`,
 * `inspectorOpen`) are declared by the parent state — this installer
 * only attaches the method surface.
 */

export function installVariableInspector(state) {
  state._onVariableSnapshot = function (params) {
    const payload = params && params.payload;
    if (Array.isArray(payload)) this.inspectorVars = payload;
  };

  state._onVariableDetail = function (params) {
    const payload = params && params.payload;
    if (payload && typeof payload === 'object') {
      this.inspectorDetail = payload;
      this.inspectorDetailFor = payload.name || null;
    }
  };

  state.requestVariableSnapshot = function () {
    if (!this._kernel || this.kernelStatus !== 'ready') return;
    try {
      this._kernel
        .execute('__pql_vars__', '__pql_inspect__()', {
          cellType: 'code',
          silent: true,
        })
        .catch(() => {
          /* swallow — fail-quiet for inspector refresh */
        });
    } catch {
      /* WS not ready — ignore */
    }
  };

  state.requestVariableDetail = async function (name) {
    if (!this._kernel || this.kernelStatus !== 'ready') return;
    if (!name) return;
    const safe = String(name).replace(/[^A-Za-z0-9_]/g, '');
    if (!safe) return;
    try {
      await this._kernel.execute(
        '__pql_vardetail__',
        `__pql_inspect_detail__('${safe}')`,
        { cellType: 'code', silent: true },
      );
    } catch {
      /* fail-quiet */
    }
  };

  // inspector visibility moved onto the unified
  // right drawer.  Kept as a thin alias for legacy callers.
  state.toggleInspector = function () {
    if (typeof this.openRightDrawer === 'function') {
      this.openRightDrawer('variables');
    }
  };
}
