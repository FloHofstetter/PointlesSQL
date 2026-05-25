// Render cite-token markdown anchors safely.
//
// The server resolves ``#dp:cat.sch`` / ``#topic:slug`` /
// ``#user:email`` / ``#agent:slug`` tokens at serialise time and
// returns ``body_md_resolved`` (or ``note_md_resolved``) with the
// matching tokens replaced by markdown anchors ``[label](href)``.
// This helper turns those anchors into safe ``<a>`` elements on
// the client side without introducing a full markdown parser.
//
// Security: the entire input is HTML-escaped first, THEN the
// anchor regex runs.  The regex only accepts hrefs starting with
// ``/`` so ``javascript:`` URIs / external hosts / inline event
// handlers cannot reach the rendered DOM.
//
// The function is exposed on ``window.pqlRenderCitations`` for
// the Alpine ``x-html`` bindings on the data-product detail page.
window.pqlRenderCitations = (md) => {
  if (!md) return '';
  const escapeHtml = (s) =>
    s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  return escapeHtml(md).replace(
    /\[([^\]]+)\]\((\/[^)]+)\)/g,
    '<a href="$2" class="pql-citation">$1</a>'
  );
};
