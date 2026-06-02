/**
 * Three layout-panel collapse toggles: context-panel (left rail),
 * meta-panel (right rail), primary-rail (icon nav).
 *
 * Side-effect module. Each toggle is a self-contained IIFE that:
 *  - flips a ``data-pql-*-collapsed`` (or ``data-pql-rail-state``)
 *    attribute on the ``<html>`` root so layout.css + per-component
 *    CSS can pick the change up without remounting,
 *  - persists the new state in localStorage so the next page-load
 *    starts in the same fold,
 *  - listens on document for clicks on the corresponding
 *    ``[data-pql-*-toggle]`` triggers (delegated, so triggers in
 *    swapped HTML continue to work without re-binding).
 *
 * Imported once from ``bootstrap.js``.
 */

(() => {
  const root = document.documentElement;
  const KEY = 'pql.context-panel.collapsed';
  function setCollapsed(flag) {
    if (flag) {
      root.setAttribute('data-pql-panel-collapsed', '1');
    } else {
      root.removeAttribute('data-pql-panel-collapsed');
    }
    try {
      if (flag) localStorage.setItem(KEY, '1');
      else localStorage.removeItem(KEY);
    } catch (e) {
      /* quota / disabled */
    }
  }
  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-pql-panel-toggle]');
    if (!btn) return;
    ev.preventDefault();
    const mode = btn.dataset.pqlPanelToggle;
    if (mode === 'collapse') setCollapsed(true);
    else if (mode === 'expand') setCollapsed(false);
    else setCollapsed(!root.hasAttribute('data-pql-panel-collapsed'));
  });
  // Each rail hub's spoke list (its sub-features) renders only in the
  // context panel. So when a hub is clicked while the panel is
  // collapsed, re-open it so those spokes are reachable at the
  // destination — unless focus-mode is deliberately on (canvas
  // surfaces want the full viewport).
  document.addEventListener('click', (ev) => {
    const hub = ev.target.closest('.pql-icon-rail__link[data-section]');
    if (!hub) return;
    let focusMode = false;
    try {
      focusMode = localStorage.getItem('pql.focus-mode') === '1';
    } catch (e) {
      /* disabled */
    }
    if (!focusMode) setCollapsed(false);
  });
})();

(() => {
  // meta panel (right rail) expand/collapse. Same shape as the
  // context-panel toggle above; flips ``data-pql-meta-collapsed`` on
  // <html> so the
  // ``html[data-pql-meta-collapsed] .pql-shell--has-meta`` layout.css
  // rule drops the column without remount.
  const root = document.documentElement;
  const KEY = 'pql.meta-panel.collapsed';
  function setCollapsed(flag) {
    if (flag) {
      root.setAttribute('data-pql-meta-collapsed', '1');
    } else {
      root.removeAttribute('data-pql-meta-collapsed');
    }
    try {
      if (flag) localStorage.setItem(KEY, '1');
      else localStorage.removeItem(KEY);
    } catch (e) {
      /* quota / disabled */
    }
  }
  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-pql-meta-toggle]');
    if (!btn) return;
    ev.preventDefault();
    const mode = btn.dataset.pqlMetaToggle;
    if (mode === 'collapse') setCollapsed(true);
    else if (mode === 'expand') setCollapsed(false);
    else setCollapsed(!root.hasAttribute('data-pql-meta-collapsed'));
  });
})();

(() => {
  // primary-rail expand/collapse toggle. Same shape as the
  // context-panel toggle above; persists per-user in localStorage and
  // flips ``data-pql-rail-state`` on <html> so both base.css (rail
  // width variable) and icon_rail.css (per-state layout) pick the
  // change up without a reload.
  const root = document.documentElement;
  const KEY = 'pql.primary-rail.collapsed';
  function setCollapsed(flag) {
    root.setAttribute('data-pql-rail-state', flag ? 'collapsed' : 'expanded');
    try {
      if (flag) localStorage.setItem(KEY, '1');
      else localStorage.removeItem(KEY);
    } catch (e) {
      /* quota / disabled */
    }
  }
  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-pql-rail-toggle]');
    if (!btn) return;
    ev.preventDefault();
    const mode = btn.dataset.pqlRailToggle;
    const isCollapsed = root.getAttribute('data-pql-rail-state') === 'collapsed';
    if (mode === 'collapse') setCollapsed(true);
    else if (mode === 'expand') setCollapsed(false);
    else setCollapsed(!isCollapsed);
  });
})();
