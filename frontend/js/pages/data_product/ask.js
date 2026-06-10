/**
 * Data-product detail page — The 'Ask this data product' Lens chat panel.
 *
 * One slice of the ``dataProductDetail`` Alpine factory.  ``installDpAsk``
 * mutates the shared component object in place (the project's mixin-installer
 * pattern); ``this`` resolves to the live component at call time, so the
 * method bodies are unchanged from the original single-file factory.
 */

export function installDpAsk(state) {
  Object.assign(state, {
    // --- "Ask this data product" panel -----------------

    async openAsk() {
      if (this.askOpened) return;
      this.askOpened = true;
      this.askLoading = true;
      this.askError = null;
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/ask/sessions',
          { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.askSessionId = data.session_id;
        this.askConfigured = !!data.configured;
        this.askMessages = [{ role: 'assistant', content: data.intro, rows: null, columns: null }];
      } catch (e) {
        this.askError = 'Could not open the assistant: ' + e.message;
        this.askOpened = false; // allow a retry on next tab show
      } finally {
        this.askLoading = false;
      }
    },

    async sendAsk() {
      const q = (this.askInput || '').trim();
      if (!q || this.askThinking || !this.askSessionId) return;
      this.askMessages.push({ role: 'user', content: q, rows: null, columns: null });
      this.askInput = '';
      this.askThinking = true;
      this.askError = null;
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/ask/sessions/' +
            this.askSessionId +
            '/messages',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: q }),
          }
        );
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          this.askMessages.push({
            role: 'assistant',
            content: (data && data.detail) || 'Request failed (HTTP ' + res.status + ').',
            rows: null,
            columns: null,
            error: true,
          });
          return;
        }
        const table = this._latestQueryRows(data.tool_calls || []);
        this.askMessages.push({
          role: 'assistant',
          content: data.assistant || '',
          rows: table ? table.rows : null,
          columns: table ? table.columns : null,
        });
      } catch (e) {
        this.askError = 'Request failed: ' + e.message;
      } finally {
        this.askThinking = false;
      }
    },

    // Pull the rows from the most recent successful query tool-call so
    // the panel can render a small result table beneath the answer.
    _latestQueryRows(toolCalls) {
      for (let i = toolCalls.length - 1; i >= 0; i--) {
        const tc = toolCalls[i];
        if (
          tc &&
          tc.name === 'query' &&
          tc.result &&
          Array.isArray(tc.result.rows) &&
          tc.result.rows.length
        ) {
          const cols = (tc.result.columns || []).map((c) => (typeof c === 'string' ? c : c.name));
          return { rows: tc.result.rows, columns: cols };
        }
      }
      return null;
    },
  });
}
