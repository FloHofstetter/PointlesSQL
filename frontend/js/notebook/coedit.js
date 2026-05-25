/**
 * Notebook editor — co-edit lifecycle facade.
 *
 * Composes the three concern-axes into the single installer that
 * `notebook_editor.js` calls.  Internal install order:
 *
 *   1. core         — creates `_coedit` + status field + `_initCoedit`
 *                     that, at runtime, also constructs `_awareness`
 *                     and calls into the awareness/cell_binding methods
 *                     below.
 *   2. awareness    — wires the WS uplink + peer-rail refresh +
 *                     before-unload cleanup + agent-presence stitch.
 *   3. cell_binding — `cellYBinding` triple resolver +
 *                     `cells_order` sync/reconcile + post-sync rebind.
 *
 * The runtime call chain (`_initCoedit` → `_wireAwarenessUplink`,
 * `_wirePeerRailRefresh`, `_installBeforeUnloadCleanup`,
 * `_rebindCellEditorsAfterSync`, `_installCellsOrderObserver`,
 * `_broadcastLocalAwareness`) relies on all three installers having
 * already attached their methods to `this`.  The synchronous
 * sequence here guarantees that.
 */

import { installCoeditCore } from './coedit_core.js';
import { installCoeditAwareness } from './coedit_awareness.js';
import { installCoeditCellBinding } from './coedit_cell_binding.js';

export function installCoeditLifecycle(state, { userInfo = null } = {}) {
  installCoeditCore(state, { userInfo });
  installCoeditAwareness(state);
  installCoeditCellBinding(state);
}
