// PointlesSQL permission-locked navigation link.
//
// Single delegated listener for every anchor that carries the
// ``data-permission-required`` attribute (rendered by
// ``_macros/permission_link.html`` when the caller passes
// ``granted=False``).  Click / Enter / Space cancel the navigation
// and surface a toast naming the missing role so the user knows
// what to ask the workspace admin for.
//
// bootstrap.js imports this module so the listener is registered
// once at app start.  No per-link init cost — safe to render the
// macro across every nav surface.

const SELECTOR = '[data-permission-required]';

function lockedAnchor(target) {
  const el = target && target.closest ? target.closest(SELECTOR) : null;
  return el || null;
}

function showLockedToast(role) {
  const t = window.pqlToast;
  if (!t || !t.info) return;
  const safeRole = role || 'higher privilege';
  t.info(`Requires ${safeRole} role — contact your workspace admin.`, { timeout: 5000 });
}

function setupPermissionLinks() {
  document.addEventListener('click', (ev) => {
    const link = lockedAnchor(ev.target);
    if (!link) return;
    ev.preventDefault();
    showLockedToast(link.dataset.permissionRequired);
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    const link = lockedAnchor(ev.target);
    if (!link) return;
    ev.preventDefault();
    showLockedToast(link.dataset.permissionRequired);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setupPermissionLinks);
} else {
  setupPermissionLinks();
}

export { setupPermissionLinks };
