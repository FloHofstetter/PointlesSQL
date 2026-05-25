/**
 * Status → Bootstrap badge class mapping.
 *
 * Mirror of :mod:`pointlessql.web.status_styles`.  Sidebars + page
 * factories import :func:`statusClass` so the badge colour for a
 * given lifecycle state matches between server-rendered Jinja
 * templates and Alpine-driven panels.
 *
 * If you add a new status here, add it on the Python side too.
 * The same applies in reverse — the server-side helper is the
 * single source of truth, but we keep an in-process mirror to
 * avoid a per-page-load fetch + parse round trip.
 */

const STATUS_BADGE_CLASS = {
  // Terminal success
  ok: 'success',
  succeeded: 'success',
  completed: 'success',
  approved: 'success',
  promoted: 'success',
  ready: 'success',
  READY: 'success',
  // In-flight
  running: 'info',
  queued: 'info',
  active: 'info',
  // Failure
  error: 'danger',
  errored: 'danger',
  failed: 'danger',
  rolled_back: 'danger',
  FAILED_REGISTRATION: 'danger',
  // Awaiting human
  needs_approval: 'warning',
  pending_approval: 'warning',
  PENDING_REGISTRATION: 'warning',
  // Cold
  denied: 'secondary',
  discarded: 'secondary',
  cancelled: 'secondary',
  paused: 'secondary',
  disabled: 'secondary',
};

const DARK_TEXT_VARIANTS = new Set(['warning', 'info']);

/**
 * Return the full Bootstrap badge class string for ``status``.
 *
 * @param {string|null|undefined} status
 * @returns {string}
 */
export function statusClass(status) {
  const variant = STATUS_BADGE_CLASS[status || ''] || 'secondary';
  const base = `bg-${variant}`;
  if (DARK_TEXT_VARIANTS.has(variant)) return `${base} text-dark`;
  return base;
}
