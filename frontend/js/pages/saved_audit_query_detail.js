// Saved audit-query detail page (/audit/queries/{slug}).
//
// Two Alpine factories (Discussion + README via polymorphic
// saved_query routes) plus a side-effect run-button binder that lives
// in the same file because both surfaces are scoped to this page.

export function savedQueryDiscussion(slug) {
  return {
    slug: slug,
    comments: [],
    commentsLoaded: false,
    draftBody: '',
    async init() {
      const res = await window.pqlApi.fetch('/api/social/saved_query/' + slug + '/comments');
      this.comments = (res && res.ok && res.data && res.data.comments) || [];
      this.commentsLoaded = true;
    },
    async submitNew() {
      const res = await window.pqlApi.fetch('/api/social/saved_query/' + slug + '/comments', {
        method: 'POST',
        body: JSON.stringify({ body_md: this.draftBody }),
      });
      if (res && res.ok) {
        this.draftBody = '';
        await this.init();
      }
    },
  };
}

export function savedQueryReadme(slug) {
  return {
    slug: slug,
    bodyRendered: '',
    draftBody: '',
    editing: false,
    readmeLoaded: false,
    async init() {
      const res = await window.pqlApi.fetch('/api/social/saved_query/' + slug + '/readme', {
        silent: true,
      });
      this.bodyRendered =
        (res && res.ok && res.data && (res.data.body_md_resolved || res.data.body_md)) || '';
      this.draftBody = (res && res.ok && res.data && res.data.body_md) || '';
      this.readmeLoaded = true;
    },
    async save() {
      const res = await window.pqlApi.fetch('/api/social/saved_query/' + this.slug + '/readme', {
        method: 'PUT',
        body: JSON.stringify({ body_md: this.draftBody }),
      });
      if (res && res.ok) {
        this.editing = false;
        await this.init();
      }
    },
  };
}

// Side-effect: bind the "Run" button to the saved-query execution
// endpoint and stream results into the result table.  Slug is read
// from the button's data attribute (was previously Jinja-injected as
// a module-scoped const).
function _initRunButton() {
  const runBtn = document.getElementById('saq-run');
  if (!runBtn) return;
  const slug = runBtn.dataset.slug;
  if (!slug) return;
  const wrap = document.getElementById('saq-result-wrap');
  const meta = document.getElementById('saq-result-meta');
  const thead = document.getElementById('saq-result-thead');
  const tbody = document.getElementById('saq-result-tbody');

  function escapeHtml(s) {
    return s.replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
    );
  }

  function renderResult(body) {
    meta.innerHTML =
      `${body.row_count} row${body.row_count === 1 ? '' : 's'} · references ${body.referenced_tables.join(', ')}` +
      (body.truncated ? ' · <span class="text-warning">truncated</span>' : '');
    thead.innerHTML = '<tr>' + body.columns.map((c) => `<th>${c}</th>`).join('') + '</tr>';
    tbody.innerHTML = body.rows
      .map(
        (row) =>
          '<tr>' +
          body.columns
            .map(
              (c) =>
                `<td>${row[c] === null || row[c] === undefined ? '<span class="text-muted fst-italic">NULL</span>' : escapeHtml(String(row[c]))}</td>`
            )
            .join('') +
          '</tr>'
      )
      .join('');
    wrap.hidden = false;
  }

  runBtn.addEventListener('click', async () => {
    runBtn.disabled = true;
    runBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> running…';
    try {
      const resp = await fetch(`/api/saved-audit-queries/${slug}/run?row_cap=1000`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const body = await resp.json();
      if (!resp.ok) {
        meta.innerHTML = '<span class="text-danger">' + (body.detail || resp.status) + '</span>';
        wrap.hidden = false;
        return;
      }
      renderResult(body);
    } finally {
      runBtn.disabled = false;
      runBtn.innerHTML = '<i class="bi bi-play-fill"></i> Run';
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _initRunButton, { once: true });
} else {
  _initRunButton();
}
