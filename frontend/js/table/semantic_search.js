/**
 * Phase 92 — Alpine factory for the table-detail "Semantic search" tab.
 *
 * Renders the column picker, query input, and result table; talks to
 * ``POST /api/sql/vector_search`` for top-K hits.  Also renders an
 * empty-state create-index form when no indices exist yet (admin
 * only).  The factory takes the workspace's ``vector_indices`` list
 * for this table, the 3-part FQN, the list of text-column names
 * (for the empty-state create form), and a ``canManage`` flag.
 */

/**
 * Build the share URL for the embed renderer.
 *
 * @param {string} tableFqn
 * @param {string} column
 * @param {string} query
 * @param {number} topK
 * @returns {string}
 */
function buildEmbedUrl(tableFqn, column, query, topK) {
  const params = new URLSearchParams({
    column,
    q: query,
    k: String(topK),
  });
  return `${window.location.origin}/embed/semantic_search/${encodeURIComponent(tableFqn)}?${params}`;
}

/**
 * Read the CSRF token from the page's ``<meta name="csrf-token">``.
 *
 * @returns {string}
 */
function csrfToken() {
  const meta = document.querySelector('meta[name=csrf-token]');
  return meta ? meta.getAttribute('content') || '' : '';
}

/**
 * Alpine factory.
 *
 * @param {Array<object>} indices
 * @param {string} tableFqn
 * @param {Array<string>} textColumns
 * @param {boolean} canManage
 * @returns {object}
 */
export function semanticSearch(indices, tableFqn, textColumns, canManage) {
  const initialColumn = indices.length > 0 ? indices[0].column : '';
  return {
    indices,
    tableFqn,
    textColumns: textColumns || [],
    canManage: Boolean(canManage),
    selectedColumn: initialColumn,
    query: '',
    topK: 10,
    hits: /** @type {Array<{score: number, pk: object, snippet: string}>} */ ([]),
    loading: false,
    error: '',
    hasRun: false,
    responseMeta: { model: '', embedder: '', delta_version_indexed: 0 },
    shareCopied: false,

    // Empty-state create-index form
    createColumn: (textColumns && textColumns.length > 0) ? textColumns[0] : '',
    createEmbedder: 'sentence_transformers',
    creating: false,
    createError: '',

    async run() {
      if (!this.query.trim()) return;
      this.loading = true;
      this.error = '';
      try {
        const resp = await fetch('/api/sql/vector_search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({
            table: this.tableFqn,
            column: this.selectedColumn,
            query: this.query,
            top_k: this.topK,
          }),
        });
        if (!resp.ok) {
          let detail = '';
          try {
            const body = await resp.json();
            detail = body.detail || body.title || JSON.stringify(body);
          } catch (e) {
            detail = await resp.text();
          }
          this.error = `HTTP ${resp.status} — ${detail}`;
          this.hits = [];
        } else {
          const payload = await resp.json();
          this.hits = payload.hits || [];
          this.responseMeta = {
            model: payload.model || '',
            embedder: payload.embedder || '',
            delta_version_indexed: payload.delta_version_indexed || 0,
          };
        }
      } catch (exc) {
        this.error = `Request failed: ${exc.message || exc}`;
        this.hits = [];
      } finally {
        this.loading = false;
        this.hasRun = true;
      }
    },

    async createIndex() {
      if (!this.createColumn) return;
      this.creating = true;
      this.createError = '';
      try {
        const resp = await fetch('/api/sql/vector_search/indices', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken(),
          },
          body: JSON.stringify({
            table: this.tableFqn,
            column: this.createColumn,
            embedder: this.createEmbedder,
          }),
        });
        if (!resp.ok) {
          let detail = '';
          try {
            const body = await resp.json();
            detail = body.detail || body.title || JSON.stringify(body);
          } catch (e) {
            detail = await resp.text();
          }
          this.createError = `HTTP ${resp.status} — ${detail}`;
          return;
        }
        // Reload so the server-rendered tab picks up the new index
        // and the empty-state branch is replaced by the search UI.
        window.location.reload();
      } catch (exc) {
        this.createError = `Request failed: ${exc.message || exc}`;
      } finally {
        this.creating = false;
      }
    },

    async copyShareUrl() {
      const url = buildEmbedUrl(this.tableFqn, this.selectedColumn, this.query, this.topK);
      try {
        await navigator.clipboard.writeText(url);
        this.shareCopied = true;
        setTimeout(() => { this.shareCopied = false; }, 1500);
      } catch (_) {
        // Older browsers: fall back to a visible text input the user
        // can copy from manually.  Surface the URL in the error slot.
        this.error = url;
      }
    },
  };
}
