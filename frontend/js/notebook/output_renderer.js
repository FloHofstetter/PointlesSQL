/**
 * MIME-bundle aware output renderer.
 *
 * Produces a DOM fragment for a single Jupyter output frame.  The
 * notebookEditor() factory calls this once per output it wants to
 * paint underneath a cell.  No Alpine ``x-html`` here — Alpine's
 * Markdown integration is whitelisted; arbitrary kernel output is
 * NOT.  text/html lands in a sandboxed iframe so a malicious
 * pandas-rendered table can't reach into the parent DOM.
 *
 * Supported MIME types (priority order):
 *   1. image/png / image/jpeg → <img src="data:...;base64,...">
 *   2. text/html              → sandboxed iframe (srcdoc)
 *   3. text/markdown          → markdown rendered server-side
 *      (placeholder shows raw text with a "[markdown]" badge until the actual fetch is wired)
 *   4. application/json       → <pre> formatted JSON
 *   5. text/plain             → <pre>
 *
 * stream messages: <pre> with a stderr-vs-stdout class hint.
 * error messages : red-bordered <pre> with the joined traceback.
 */

// biome-ignore lint/suspicious/noControlCharactersInRegex: ANSI escape sequences are control characters by definition; this regex strips them from Jupyter terminal output.
const _ANSI_ESCAPE = /\x1b\[[0-9;]*[a-zA-Z]/g;

function _stripAnsi(text) {
  return String(text || '').replace(_ANSI_ESCAPE, '');
}

function _mimePriorityKey(data) {
  if (!data || typeof data !== 'object') return null;
  if (typeof data['image/png'] === 'string') return 'image/png';
  if (typeof data['image/jpeg'] === 'string') return 'image/jpeg';
  if (typeof data['image/svg+xml'] === 'string') return 'image/svg+xml';
  if (typeof data['text/html'] === 'string') return 'text/html';
  if (typeof data['text/markdown'] === 'string') return 'text/markdown';
  if (typeof data['application/json'] !== 'undefined') return 'application/json';
  if (typeof data['text/plain'] === 'string') return 'text/plain';
  return null;
}

function _renderImage(mime, base64) {
  const img = document.createElement('img');
  img.src = `data:${mime};base64,${base64}`;
  img.alt = 'cell output';
  img.className = 'pql-notebook-output__image';
  return img;
}

function _renderHtml(html) {
  // Sandboxed iframe — no scripts, no top-nav, no parent access.
  // ``allow-same-origin`` is intentionally OMITTED so even
  // cross-origin XHR is denied.  pandas's _repr_html_ DataFrame
  // tables render fine without it.
  const frame = document.createElement('iframe');
  frame.className = 'pql-notebook-output__iframe';
  frame.setAttribute('sandbox', '');
  frame.setAttribute('referrerpolicy', 'no-referrer');
  // Theme detection: read the host document's ``data-bs-theme`` and
  // bake matching colours into the srcdoc.  The iframe can't reach
  // out to the parent (sandbox=""), and CSS ``light-dark()`` is too
  // new to rely on across browsers, so we resolve up-front.
  const hostTheme = document.documentElement.dataset.bsTheme || 'light';
  const themePalette =
    hostTheme === 'dark'
      ? { fg: '#e9ecef', border: 'rgba(255,255,255,0.18)', mutedBg: 'rgba(255,255,255,0.04)' }
      : { fg: '#212529', border: '#dee2e6', mutedBg: 'rgba(0,0,0,0.025)' };
  frame.srcdoc = `<!doctype html><meta charset="utf-8">
  <meta name="color-scheme" content="${hostTheme}">
  <style>
    :root { color-scheme: ${hostTheme}; }
    body { margin: 0; font: 0.85rem -apple-system, system-ui, sans-serif; color: ${themePalette.fg}; background: transparent; }
    table { border-collapse: collapse; }
    table, th, td { border: 1px solid ${themePalette.border}; padding: 2px 6px; }
    th { background: ${themePalette.mutedBg}; }
    pre { white-space: pre-wrap; color: inherit; }
    a { color: inherit; text-decoration: underline; }
  </style>
  <body>${html}</body>`;
  // Allow the iframe to grow with its content.  postMessage from
  // inside is blocked by the empty sandbox; instead we observe
  // load and pin to a generous default so most pandas tables fit.
  frame.style.width = '100%';
  frame.style.minHeight = '4rem';
  frame.style.border = '0';
  frame.addEventListener('load', () => {
    // Best-effort height adjust by polling once after load — the
    // sandbox blocks contentWindow access for cross-origin srcdoc
    // in some browsers, so wrap in try/catch.
    try {
      const doc = frame.contentDocument;
      if (doc && doc.body) {
        const h = Math.min(doc.body.scrollHeight + 16, 600);
        frame.style.height = `${h}px`;
      }
    } catch (_e) {
      /* ignore */
    }
  });
  return frame;
}

function _renderMarkdown(text) {
  // will swap this for a server-side render via
  // POST /api/notebooks/render-markdown.  we
  // emit raw text with a hint badge so the round-trip works.
  const wrap = document.createElement('div');
  wrap.className = 'pql-notebook-output__markdown';
  const badge = document.createElement('span');
  badge.className = 'pql-notebook-output__badge';
  badge.textContent = 'markdown';
  wrap.appendChild(badge);
  const pre = document.createElement('pre');
  pre.textContent = text;
  wrap.appendChild(pre);
  return wrap;
}

function _renderJson(value) {
  const pre = document.createElement('pre');
  pre.className = 'pql-notebook-output__json';
  try {
    pre.textContent = JSON.stringify(value, null, 2);
  } catch (_e) {
    pre.textContent = String(value);
  }
  return pre;
}

function _renderPlain(text, extraClass = '') {
  const pre = document.createElement('pre');
  pre.className = `pql-notebook-output__plain ${extraClass}`.trim();
  pre.textContent = _stripAnsi(text);
  return pre;
}

function _renderError(content) {
  const wrap = document.createElement('div');
  wrap.className = 'pql-notebook-output__error';
  const tb = Array.isArray(content && content.traceback) ? content.traceback.join('\n') : '';
  const fallback = `${(content && content.ename) || 'Error'}: ${(content && content.evalue) || ''}`;
  const pre = document.createElement('pre');
  pre.textContent = _stripAnsi(tb || fallback);
  wrap.appendChild(pre);
  return wrap;
}

export function renderOutputFrame(out) {
  // out: {msg_type, content, metadata?}
  if (!out || typeof out !== 'object') {
    return _renderPlain('');
  }
  const msgType = out.msg_type;
  const content = out.content || {};
  if (msgType === 'stream') {
    const isStderr = content.name === 'stderr';
    return _renderPlain(content.text || '', isStderr ? 'pql-notebook-output__plain--stderr' : '');
  }
  if (msgType === 'error') {
    return _renderError(content);
  }
  if (msgType === 'execute_result' || msgType === 'display_data') {
    const data = content.data || {};
    const key = _mimePriorityKey(data);
    if (key === 'image/png' || key === 'image/jpeg') {
      return _renderImage(key, data[key]);
    }
    if (key === 'image/svg+xml') {
      // SVG goes through the sandboxed iframe path so any embedded
      // <script> is neutralised.
      return _renderHtml(data[key]);
    }
    if (key === 'text/html') {
      return _renderHtml(data[key]);
    }
    if (key === 'text/markdown') {
      return _renderMarkdown(data[key]);
    }
    if (key === 'application/json') {
      return _renderJson(data[key]);
    }
    if (key === 'text/plain') {
      return _renderPlain(data[key]);
    }
    return _renderPlain('[no rendererable mime type]');
  }
  return _renderPlain('');
}
