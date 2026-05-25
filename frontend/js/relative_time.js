/*
 * PointlesSQL relative-time helper — extracted from home.html
 * into its own file so /jobs rows can reuse it. ES-module
 *; bootstrap.js re-attaches both helpers to
 * ``window.pqlParseServerIso`` and ``window.pqlRelativeTime``.
 *
 * Usage:
 * <span x-data="{ iso: '2024-01-01T00:00:00Z' }"
 * x-text="pqlRelativeTime(iso)"></span>
 *
 * Returns the empty string for a missing iso, the raw iso for an
 * unparseable value, a coarse relative string for recent times, and
 * an ISO date (YYYY-MM-DD) for anything older than ~30 days.
 */

// The backend stamps JobRun.started_at with datetime.now(UTC) but
// SQLite drops timezone info on readback, so the server emits
// ISO-8601 like "2026-04-17T15:15:44.341818" — no Z suffix, no
// offset. Date.parse treats that as *local*, which drifts "just
// now" by the client's UTC offset (a CEST client sees "2 hours
// ago"). Append 'Z' when the string lacks any tz marker so the
// browser parses it as UTC and the relative-time math is right.
export function pqlParseServerIso(iso) {
  if (!iso) return null;
  const s = String(iso);
  // Already has a zone: trailing Z, or ±HH:MM / ±HHMM after the T.
  if (/(Z|[+-]\d{2}:?\d{2})$/.test(s)) return s;
  // No zone — treat as UTC.
  return s + 'Z';
}

export function pqlRelativeTime(iso) {
  if (!iso) return '';
  const t = Date.parse(pqlParseServerIso(iso));
  if (Number.isNaN(t)) return iso;
  const delta = Math.max(0, (Date.now() - t) / 1000);
  if (delta < 45) return 'just now';
  if (delta < 90) return '1 min ago';
  if (delta < 3600) return Math.round(delta / 60) + ' min ago';
  if (delta < 5400) return '1 hour ago';
  if (delta < 86400) return Math.round(delta / 3600) + ' hours ago';
  if (delta < 129600) return '1 day ago';
  if (delta < 2592000) return Math.round(delta / 86400) + ' days ago';
  const d = new Date(t);
  return d.toISOString().slice(0, 10);
}

/**
 * Absolute timestamp formatter — UTC-anchored, second precision.
 * Pairs with ``pqlRelativeTime`` for the two-tier display
 * convention: relative as the visible value, absolute as the
 * tooltip.  Also used directly on detail pages where the exact
 * moment matters more than the elapsed delta.
 */
export function pqlAbsTime(iso) {
  if (!iso) return '';
  const t = Date.parse(pqlParseServerIso(iso));
  if (Number.isNaN(t)) return iso;
  const d = new Date(t);
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getUTCFullYear() +
    '-' +
    pad(d.getUTCMonth() + 1) +
    '-' +
    pad(d.getUTCDate()) +
    ' ' +
    pad(d.getUTCHours()) +
    ':' +
    pad(d.getUTCMinutes()) +
    ' UTC'
  );
}
