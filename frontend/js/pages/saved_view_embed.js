// Standalone saved-view embed page (iframe), classic script.
//
// Inline minimal pqlApi: the embed page deliberately avoids the full
// bootstrap.js / CodeMirror chain so an iframe stays cheap.
async function _embedFetch(url, init) {
  const opts = Object.assign({}, init || {});
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    opts.body = JSON.stringify(opts.body);
  }
  const verb = (opts.method || 'GET').toUpperCase();
  if (verb !== 'GET' && verb !== 'HEAD') {
    const m = document.querySelector('meta[name="csrf-token"]');
    const token = m ? m.content : '';
    if (token) {
      opts.headers = Object.assign({}, opts.headers || {});
      opts.headers['X-CSRF-Token'] = token;
    }
  }
  try {
    const res = await fetch(url, opts);
    const ct = res.headers.get('content-type') || '';
    const data = /\bjson\b/.test(ct) ? await res.json() : null;
    return { ok: res.ok, status: res.status, data, error: res.ok ? null : `HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, status: 0, data: null, error: e.message || 'Network error' };
  }
}
window.pqlApi = { fetch: _embedFetch };

function savedViewEmbed(view) {
  const initial = {};
  (view.parameters || []).forEach((p) => {
    initial[p.name] = p.default !== null && p.default !== undefined ? p.default : '';
  });
  return {
    view,
    values: initial,
    running: false,
    result: null,
    error: null,
    async run() {
      this.error = null;
      this.running = true;
      const res = await window.pqlApi.fetch(`/api/views/${this.view.slug}/run`, {
        method: 'POST',
        body: { parameters: this.values },
      });
      this.running = false;
      if (res.ok && res.data) this.result = res.data;
      else this.error = (res.data && res.data.detail) || res.error || 'Run failed';
    },
  };
}
window.savedViewEmbed = savedViewEmbed;
