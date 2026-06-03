/**
 * Deterministic avatar helpers — initials + a stable colour per identity.
 *
 * One identity always maps to the same hue across reloads, tabs and
 * surfaces, so a person reads as "the same person" wherever they appear
 * (co-edit peer rail, activity feed, …).  The colour is an FNV-1a hash of
 * the identity key folded into an HSL hue; initials are the first letters
 * of the first + last name token.
 *
 * Extracted from the notebook co-edit installers so the feed and the
 * peer rail share one source of truth rather than two file-private copies.
 */

/**
 * Map an identity key to a stable, readable HSL colour.
 *
 * @param {string|number} key  Identity key (user id, name, …).
 * @returns {string} An ``hsl(...)`` colour string.
 */
export function avatarColor(key) {
  const text = String(key || 'anon');
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  const hue = h % 360;
  // 42% lightness keeps white initials at AA contrast even on the
  // brightest hues (yellow-green is the worst case).
  return `hsl(${hue}, 65%, 42%)`;
}

/**
 * Reduce a display name to one- or two-letter initials.
 *
 * @param {string} name  A display name.
 * @returns {string} Up to two uppercase letters, or ``?`` when empty.
 */
export function initials(name) {
  const trimmed = String(name || '').trim();
  if (!trimmed) return '?';
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Build a render-ready avatar descriptor for one feed row / peer.
 *
 * People (anything carrying a name or stable id) render as a coloured
 * initials disc.  System events render as a lane-tinted glyph: the colour
 * communicates severity / lane, the icon communicates the kind, so the
 * stream never collapses into a wall of identical grey circles.
 *
 * @param {{name?: string|null, id?: string|number|null, kind?: string,
 *   severity?: string, icon?: string}} opts
 * @returns {{mode: 'initials'|'glyph', text: string, icon: string,
 *   color: string}}
 */
export function avatarFor({ name = null, id = null, kind = '', severity = '', icon = '' } = {}) {
  if (name) {
    const key = id != null ? String(id) : name;
    return { mode: 'initials', text: initials(name), icon: '', color: avatarColor(key) };
  }
  return { mode: 'glyph', text: '', icon: icon || 'bi-bell', color: laneColor(kind, severity) };
}

// Lane / severity → a Bootstrap CSS variable so glyph avatars inherit the
// theme's palette (and dark-mode overrides) instead of hard-coded hex.
const LANE_VARS = {
  health: '--bs-danger',
  pipeline: '--bs-danger',
  approval: '--bs-warning',
  agent_run: '--bs-info',
  branch: '--bs-info',
  badge_award: '--bs-warning',
  issue: '--bs-primary',
};

/**
 * Resolve a system-event lane + severity to a themeable colour.
 *
 * @param {string} kind      Render kind (``health`` / ``pipeline`` / …).
 * @param {string} severity  ``warn`` / ``error`` / ``info``.
 * @returns {string} A ``var(--bs-*)`` colour reference.
 */
export function laneColor(kind, severity) {
  if (severity === 'error') return 'var(--bs-danger)';
  if (severity === 'warn') return 'var(--bs-warning)';
  return `var(${LANE_VARS[kind] || '--bs-secondary'})`;
}
