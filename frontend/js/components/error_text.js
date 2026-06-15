/**
 * Shared run-error formatter.
 *
 * Run-history tables (pipelines, ingest, jobs) persist the full raw
 * error for debugging, but rendering it verbatim dumps a multi-line
 * traceback — or the catalog client's
 * "Unexpected status code: 404\n\nResponse content: {json}" blob — into
 * a table cell, bloating the row/column. ``friendlyError`` reduces it to
 * a one-line headline: the catalog envelope's ``message`` when present,
 * else the first line. Callers keep the raw string reachable (a title
 * tooltip or a collapsible) so nothing is lost.
 */

export function friendlyError(raw) {
  if (!raw) return '';
  const s = String(raw);
  const m = s.match(/\{[\s\S]*\}/);
  if (m) {
    try {
      const body = JSON.parse(m[0]);
      if (body && typeof body.message === 'string' && body.message.trim()) {
        return body.message.trim();
      }
    } catch (e) {
      // not JSON — fall through to the first-line fallback
    }
  }
  return (s.split('\n')[0] || s).trim();
}
