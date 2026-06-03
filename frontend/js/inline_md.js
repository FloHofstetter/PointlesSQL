/**
 * Tiny inline-markdown renderer for one-line feed bodies.
 *
 * Feed summaries are authored as light markdown (``**bold**``,
 * ``*italic*``, `` `code` ``, ``[label](url)``) but were rendered with
 * ``x-text`` — so the markers showed up literally.  A full markdown
 * library would be overkill for single-line strings, so this covers the
 * inline subset only.
 *
 * Security mirrors ``citation_render.js``: the whole string is
 * HTML-escaped FIRST, then the safe inline patterns are re-introduced, so
 * no author-supplied markup can survive into the DOM.  Links are forced
 * to ``rel="noopener"`` and only ``http(s)`` / root-relative hrefs pass.
 */

/**
 * HTML-escape a string for safe interpolation into an ``x-html`` sink.
 *
 * @param {unknown} s  Any value; coerced to string.
 * @returns {string} The HTML-escaped text.
 */
export function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const _escapeHtml = escapeHtml;

function _safeHref(raw) {
  const href = raw.trim();
  // Root-relative is allowed, but protocol-relative (``//host``) would point
  // off-site — require a single leading slash so it stays same-origin.
  if (/^https?:\/\//i.test(href) || (href.startsWith('/') && !href.startsWith('//'))) {
    return href;
  }
  return null;
}

/**
 * Render the inline-markdown subset of ``text`` to a safe HTML string.
 *
 * @param {string} text  Source string (already-trusted structure, but
 *   untrusted content).
 * @returns {string} HTML safe to bind via ``x-html``.
 */
export function renderInlineMd(text) {
  let html = _escapeHtml(text);
  // Pull links out to placeholders BEFORE the emphasis/code passes, so an
  // underscore or asterisk in an href (e.g. ``/data/foo_bar``) can't get
  // rewritten into a stray <em>/<code> inside the anchor markup.  The
  // rendered <a> is stitched back in at the end.
  const links = [];
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, label, href) => {
    const safe = _safeHref(href);
    if (!safe) return label;
    const token = `@@PQLLINK${links.length}@@`;
    links.push(`<a href="${safe}" rel="noopener">${label}</a>`);
    return token;
  });
  // `code` — run before emphasis so a literal asterisk inside code is left
  // alone.
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // **bold** then *italic* / _italic_.
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, '$1<em>$2</em>');
  html = html.replace(/(^|[^_])_([^_\s][^_]*?)_(?!_)/g, '$1<em>$2</em>');
  html = html.replace(/@@PQLLINK(\d+)@@/g, (m, i) => links[Number(i)] ?? m);
  return html;
}
