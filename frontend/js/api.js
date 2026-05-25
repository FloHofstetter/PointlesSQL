/*
 * PointlesSQL shared fetch helper.
 *
 * Consolidates the try/catch/parse/error-extract pattern that
 * components (editable, properties_editor, tags_editor, permissions_editor,
 * federation) each hand-rolled. Every non-ok response now surfaces a toast
 * via window.pqlToast so mutations fail loudly instead of burying the error
 * in a tiny inline hint.
 *
 * Usage:
 * const res = await window.pqlApi.fetch(url, { method: 'PATCH', body: {...} });
 * if (!res.ok) { this.error = 'Save failed: ' + res.error; return; }
 * this.value = res.data.field;
 *
 * Options:
 * silent: true — skip the automatic toast (e.g. optional background GETs).
 *
 * And for mutations that reload the page:
 * window.pqlApi.reloadWithToast('Job queued.'); // 400 ms default
 * window.pqlApi.reloadWithToast('Refreshing.', { delay: 0 }); // immediate
 *
 * bootstrap.js re-attaches the singleton to ``window.pqlApi``.
 */

function toast(variant, message) {
  if (window.pqlToast && window.pqlToast[variant]) {
    window.pqlToast[variant](message);
  }
}

async function extractError(res) {
  const ct = res.headers.get('content-type') || '';
  try {
    if (/\bjson\b/.test(ct)) {
      const body = await res.json();
      if (body && typeof body === 'object') {
        const msg = body.detail || body.message || body.error;
        if (typeof msg === 'string' && msg.length > 0) return msg;
        // Some soyuz error envelopes wrap detail in an object
        if (msg && typeof msg === 'object' && typeof msg.message === 'string') {
          return msg.message;
        }
      }
      return 'HTTP ' + res.status;
    }
    const text = await res.text();
    return text || 'HTTP ' + res.status;
  } catch (e) {
    return 'HTTP ' + res.status;
  }
}

async function parseBody(res) {
  const ct = res.headers.get('content-type') || '';
  if (!/\bjson\b/.test(ct)) return null;
  try {
    return await res.json();
  } catch (e) {
    return null;
  }
}

// pull the CSRF token from <meta name="csrf-token">
// on every call. Caching the value at module-load time would race with
// HTMX boost navigations that swap the meta tag. ``meta?.content``
// returns ``undefined`` when the tag is missing (anonymous smoke test
// pages, error pages); we guard the header injection on a truthy value.
function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : '';
}

// read the active workspace slug off the same meta-tag
// shape used for the CSRF token.  Auto-attached as ``X-Workspace`` on
// every pqlApi.fetch() call so workspace-scoped server filters apply
// uniformly without per-call wiring.  Returns '' (not falsy) when the
// page didn't render the meta tag (anonymous/error pages); we guard
// the header injection on a truthy value below.
function workspaceSlug() {
  const meta = document.querySelector('meta[name="workspace-slug"]');
  return meta ? meta.content : '';
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

async function apiFetch(url, init) {
  const opts = Object.assign({}, init || {});
  const silent = opts.silent === true;
  delete opts.silent;

  // Auto-JSON: if body is a plain object, stringify + set content-type.
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    opts.body = JSON.stringify(opts.body);
  }

  // auto-attach the CSRF token for non-safe verbs.
  // The server-side middleware accepts either this header or a hidden
  // form field (the form-field path was the only thing keeping pqlApi
  // mutations alive before this header injection). Mirrors what
  // base.html's HTMX htmx:configRequest hook + notebook/main.js,
  // editor_shell.js, file_tree.js already do by hand. Idempotent
  // for callers that pre-set the header (caller wins).
  const verb = (opts.method || 'GET').toUpperCase();
  if (!SAFE_METHODS.has(verb)) {
    const token = csrfToken();
    if (token) {
      opts.headers = Object.assign({}, opts.headers || {});
      if (!opts.headers['X-CSRF-Token']) {
        opts.headers['X-CSRF-Token'] = token;
      }
    }
  }

  // auto-attach X-Workspace on every call (safe + unsafe
  // verbs alike — GETs need the workspace filter just as much as
  // mutations). Caller-supplied header wins.
  const slug = workspaceSlug();
  if (slug) {
    opts.headers = Object.assign({}, opts.headers || {});
    if (!opts.headers['X-Workspace']) {
      opts.headers['X-Workspace'] = slug;
    }
  }

  let res;
  try {
    res = await fetch(url, opts);
  } catch (e) {
    const err = e && e.message ? e.message : 'Network error';
    if (!silent) toast('error', err);
    return { ok: false, status: 0, data: null, error: err };
  }

  if (!res.ok) {
    const err = await extractError(res);
    if (!silent) toast('error', err);
    return { ok: false, status: res.status, data: null, error: err };
  }

  const data = await parseBody(res);
  return { ok: true, status: res.status, data: data, error: null };
}

function reloadWithToast(message, opts) {
  const delay = opts && typeof opts.delay === 'number' ? opts.delay : 400;
  const variant = (opts && opts.variant) || 'success';
  toast(variant, message);
  window.setTimeout(function () {
    window.location.reload();
  }, delay);
}

export const pqlApi = {
  fetch: apiFetch,
  reloadWithToast: reloadWithToast,
};

// exported so call-sites outside pqlApi can stop hand-rolling
// ``if (window.pqlToast) window.pqlToast.X(msg)`` guards (14× earlier).
export { toast, csrfToken, workspaceSlug };
