/**
 * Cookie-CSRF JSON fetch helper.
 *
 * Reads the legacy ``csrftoken`` cookie and stamps it as the
 * ``X-CSRFToken`` header on mutating verbs (POST/PUT/PATCH/DELETE).
 * Throws on non-2xx, parses 204 as null, returns parsed JSON
 * otherwise.
 *
 * For meta-tag-CSRF + workspace-header + structured error envelopes,
 * see `frontend/js/api.js` (`window.pqlApi.fetch`).  Both strategies
 * coexist in the backend; pick the one matching the route family
 * you're calling.
 */

function csrfTokenFromCookie() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export async function jsonFetch(url, options = {}) {
  const headers = Object.assign(
    { 'Content-Type': 'application/json' },
    options.headers || {},
  );
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    const token = csrfTokenFromCookie();
    if (token) headers['X-CSRFToken'] = token;
  }
  const res = await fetch(url, { ...options, headers, credentials: 'same-origin' });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${method} ${url} failed: ${res.status} ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}
