// Standalone semantic-search embed page (iframe), classic script.
//
// The embed deliberately avoids bootstrap.js / pqlApi so the iframe
// stays cheap — Alpine from CDN plus this one factory is the whole
// JS surface.
function semanticSearchEmbed(embed) {
  return {
    embed,
    loading: true,
    error: '',
    hits: [],
    async run() {
      this.loading = true;
      this.error = '';
      try {
        const resp = await fetch('/api/sql/vector_search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({
            table: this.embed.table,
            column: this.embed.column,
            query: this.embed.query,
            top_k: this.embed.top_k,
          }),
        });
        if (!resp.ok) {
          const body = await resp.text();
          this.error = `HTTP ${resp.status} — ${body}`;
          this.hits = [];
        } else {
          const payload = await resp.json();
          this.hits = payload.hits || [];
        }
      } catch (exc) {
        this.error = `Request failed: ${exc.message || exc}`;
      } finally {
        this.loading = false;
      }
    },
  };
}
window.semanticSearchEmbed = semanticSearchEmbed;
