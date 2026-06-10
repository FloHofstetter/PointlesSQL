// Layout-shell boot for the authenticated app (base.html only).
//
// Restores the persisted rail / context-panel / meta-panel / focus
// states onto <html> as data attributes.  Loaded as a CLASSIC,
// render-blocking script in <head> BEFORE the first stylesheet so the
// shell paints in its remembered state (base.css + icon_rail.css key
// their layout off these attributes).
(function () {
  try {
    if (localStorage.getItem('pql.context-panel.collapsed') === '1') {
      document.documentElement.setAttribute('data-pql-panel-collapsed', '1');
    }
  } catch (_e) {}
})();
(function () {
  // Meta panel (right rail) collapse state — same shape as the
  // context-panel toggle so the right rail reads in its remembered
  // state on first paint of every page.
  try {
    if (localStorage.getItem('pql.meta-panel.collapsed') === '1') {
      document.documentElement.setAttribute('data-pql-meta-collapsed', '1');
    }
  } catch (_e) {}
})();
(function () {
  // Primary-rail state init.  Default is ``expanded`` (220px, with
  // labels + group headers).
  try {
    const collapsed = localStorage.getItem('pql.primary-rail.collapsed') === '1';
    document.documentElement.setAttribute(
      'data-pql-rail-state',
      collapsed ? 'collapsed' : 'expanded'
    );
  } catch (_e) {
    document.documentElement.setAttribute('data-pql-rail-state', 'expanded');
  }
})();
(function () {
  // Focus-mode init — when enabled, collapse both the primary rail
  // and the context panel at first paint so canvas-heavy surfaces
  // get the full viewport.  Runs last so it shadows the rail + panel
  // keys until the user toggles focus-mode back off.
  try {
    if (localStorage.getItem('pql.focus-mode') === '1') {
      document.documentElement.setAttribute('data-pql-rail-state', 'collapsed');
      document.documentElement.setAttribute('data-pql-panel-collapsed', '1');
      document.documentElement.setAttribute('data-pql-focus-mode', '1');
    }
  } catch (_e) {}
})();

// Toggle helper used by every canvas surface's focus-mode button.
// Boot-level so the layout pivots before Alpine reactivity churns
// through the topbar render.
window.pqlToggleFocusMode = function () {
  try {
    const on = localStorage.getItem('pql.focus-mode') !== '1';
    if (on) {
      localStorage.setItem('pql.focus-mode', '1');
      document.documentElement.setAttribute('data-pql-rail-state', 'collapsed');
      document.documentElement.setAttribute('data-pql-panel-collapsed', '1');
      document.documentElement.setAttribute('data-pql-focus-mode', '1');
    } else {
      localStorage.removeItem('pql.focus-mode');
      document.documentElement.removeAttribute('data-pql-focus-mode');
      // Restore the user's persistent rail + panel preferences.
      const railCollapsed = localStorage.getItem('pql.primary-rail.collapsed') === '1';
      document.documentElement.setAttribute(
        'data-pql-rail-state',
        railCollapsed ? 'collapsed' : 'expanded'
      );
      const panelCollapsed = localStorage.getItem('pql.context-panel.collapsed') === '1';
      if (panelCollapsed) {
        document.documentElement.setAttribute('data-pql-panel-collapsed', '1');
      } else {
        document.documentElement.removeAttribute('data-pql-panel-collapsed');
      }
    }
    return on;
  } catch (_e) {
    return false;
  }
};
