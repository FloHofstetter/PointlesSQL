/**
 * Phase 92 — Alpine factory for the table-detail "Semantic search" tab.
 *
 * Renders the column picker, query input, and result table; talks to
 * ``POST /api/sql/vector_search`` for top-K hits.  The factory takes
 * the workspace's ``vector_indices`` list for this table and the
 * 3-part FQN as constructor args — keeps the partial standalone.
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
 * Alpine factory.
 *
 * @param {Array<{id: number, column: string, dim: number, model: string,
 *   embedder: string, metric: string, delta_version_indexed: number | null,
 *   last_built_at: string | null, last_built_rows: number | null,
 *   last_error: string | null}>} indices
 * @param {string} tableFqn
 * @returns {object}
 */
export function semanticSearch(indices, tableFqn) {
  const initialColumn = indices.length > 0 ? indices[0].column : '';
  return {
    indices,
    tableFqn,
    selectedColumn: initialColumn,
    query: '',
    topK: 10,
    hits: /** @type {Array<{score: number, pk: object, snippet: string}>} */ ([]),
    loading: false,
    error: '',
    hasRun: false,
    responseMeta: { model: '', embedder: '', delta_version_indexed: 0 },
    shareCopied: false,

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

window.semanticSearch = semanticSearch;
