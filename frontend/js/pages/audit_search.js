// Audit FTS search page wiring for /audit/search.
//
// Bare side-effect module gated on ``#search-form``.  Carries the
// "Search" + "Load more" pager state across submissions; resets on
// every fresh search so a new query never appends onto stale rows.

function _init() {
  const formEl = document.getElementById('search-form');
  if (!formEl) return;

  const qEl = document.getElementById('search-q');
  const axisEl = document.getElementById('search-axis');
  const sinceEl = document.getElementById('search-since');
  const rowsEl = document.getElementById('search-rows');
  const metaEl = document.getElementById('search-meta');
  const pagerEl = document.getElementById('search-pager');
  const loadMoreBtn = document.getElementById('search-load-more');
  const pagerStatusEl = document.getElementById('search-pager-status');

  const PAGE_SIZE = 50;
  let state = {
    q: '',
    axis: 'all',
    since: '',
    offset: 0,
    loadedCount: 0,
  };

  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(
      /[&<>"']/g,
      (c) =>
        ({
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;',
        })[c]
    );
  }

  // Snippet text is server-side trusted (only <mark> tags injected by FTS5);
  // pass through as-is.
  function snippetHtml(snippet) {
    if (!snippet) return '';
    return snippet;
  }

  function rowLink(axis, entityId, runId) {
    if (axis === 'runs' && entityId) return `/runs/${encodeURIComponent(entityId)}`;
    if (axis === 'ops' && runId)
      return `/runs/${encodeURIComponent(runId)}?op_id=${encodeURIComponent(entityId)}#tab-ops`;
    if (axis === 'queries' && runId) return `/runs/${encodeURIComponent(runId)}#tab-audit`;
    if (axis === 'tool_calls' && runId) return `/runs/${encodeURIComponent(runId)}#tab-audit`;
    if (axis === 'audit_log') return '/audit/queries';
    return '#';
  }

  function buildRowHtml(r) {
    const link = rowLink(r.axis, r.entity_id, r.run_id);
    const eid = String(r.entity_id || '');
    const eidShort = eid.length > 60 ? eid.slice(0, 60) + '…' : eid;
    const eidClass =
      eid.length > 60 ? 'pql-truncate-tip font-monospace small' : 'font-monospace small';
    return `<tr>
            <td><span class="badge bg-secondary">${escapeHtml(r.axis)}</span></td>
            <td class="font-monospace small text-muted">${escapeHtml((r.run_id || '').slice(0, 8))}</td>
            <td><a href="${link}" class="${eidClass} text-decoration-none" title="${escapeHtml(eid)}">${escapeHtml(eidShort)}</a></td>
            <td class="small">${snippetHtml(r.snippet)}</td>
            <td class="text-end font-monospace small text-muted">${r.rank !== null ? r.rank.toFixed(2) : '—'}</td>
        </tr>`;
  }

  function setPagerVisibility(nextOffset) {
    if (nextOffset === null || nextOffset === undefined) {
      if (state.loadedCount > 0) {
        pagerEl.hidden = false;
        loadMoreBtn.hidden = true;
        pagerStatusEl.textContent = `All ${state.loadedCount} matches loaded.`;
      } else {
        pagerEl.hidden = true;
      }
    } else {
      pagerEl.hidden = false;
      loadMoreBtn.hidden = false;
      pagerStatusEl.textContent = `${state.loadedCount} loaded — fetch next ${PAGE_SIZE}.`;
    }
  }

  function buildParams(offset) {
    const params = new URLSearchParams({
      q: state.q,
      axis: state.axis,
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (state.since) params.set('since', state.since);
    return params;
  }

  async function fetchPage(offset, append) {
    loadMoreBtn.disabled = true;
    const resp = await fetch('/api/audit/search?' + buildParams(offset).toString(), {
      credentials: 'same-origin',
    });
    if (!resp.ok) {
      if (!append)
        rowsEl.innerHTML = `<tr><td colspan="5" class="text-danger py-3">Error ${resp.status}</td></tr>`;
      metaEl.textContent = '';
      pagerEl.hidden = true;
      loadMoreBtn.disabled = false;
      return;
    }
    const data = await resp.json();
    if (!data.available) {
      metaEl.textContent = 'FTS not provisioned — empty result.';
      rowsEl.innerHTML =
        '<tr><td colspan="5" class="text-center text-muted py-4">FTS not provisioned.</td></tr>';
      pagerEl.hidden = true;
      loadMoreBtn.disabled = false;
      return;
    }

    const html = data.results.map(buildRowHtml).join('');
    if (append) {
      rowsEl.insertAdjacentHTML('beforeend', html);
      state.loadedCount += data.results.length;
    } else {
      if (!data.results.length) {
        rowsEl.innerHTML =
          '<tr><td colspan="5" class="text-center text-muted py-4">No matches.</td></tr>';
        state.loadedCount = 0;
      } else {
        rowsEl.innerHTML = html;
        state.loadedCount = data.results.length;
      }
    }
    metaEl.textContent = `${state.loadedCount} loaded for "${data.query}" on axis=${data.axis}`;
    state.offset =
      data.next_offset !== null && data.next_offset !== undefined
        ? data.next_offset
        : offset + data.results.length;
    setPagerVisibility(data.next_offset !== undefined ? data.next_offset : null);
    loadMoreBtn.disabled = false;
  }

  async function runSearch(ev) {
    if (ev) ev.preventDefault();
    const q = qEl.value.trim();
    if (!q) return;
    state = {
      q,
      axis: axisEl.value,
      since: sinceEl.value.trim(),
      offset: 0,
      loadedCount: 0,
    };
    rowsEl.innerHTML =
      '<tr><td colspan="5" class="text-center text-muted py-4">Searching…</td></tr>';
    await fetchPage(0, /*append=*/ false);
  }

  async function loadMore() {
    if (!state.q) return;
    await fetchPage(state.offset, /*append=*/ true);
  }

  formEl.addEventListener('submit', runSearch);
  loadMoreBtn.addEventListener('click', loadMore);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init, { once: true });
} else {
  _init();
}
