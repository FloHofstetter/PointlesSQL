// One Genie room (/genie/{slug}).
//
// genieSpace: chat pane over the shared per-space transcript, the
// trusted-question sidebar (chips prefill the input), and the
// owner/admin configuration drawer (tables / metric views /
// instructions / trusted assets).  Results are not persisted —
// only the latest ask's table renders, capped at 100 display rows.

const DISPLAY_ROW_CAP = 100;

export function genieSpace(config) {
  return {
    slug: config.slug,
    canEdit: !!config.canEdit,

    space: null,
    assets: [],
    messages: [],
    error: '',

    question: '',
    asking: false,
    lastResult: null,
    expandedSql: {},

    showConfig: false,
    cfg: { title: '', description: '', instructions: '', tables: '', metricViews: '' },
    cfgError: '',
    cfgSaving: false,

    newAsset: { question: '', sql: '' },
    assetError: '',

    suggestions: [],

    async init() {
      await this.loadSpace();
      await this.loadMessages();
    },

    async loadSpace() {
      const res = await window.pqlApi.fetch('/api/genie/spaces/' + encodeURIComponent(this.slug));
      if (!res.ok) {
        this.error = res.error || 'Failed to load the space';
        return;
      }
      this.space = res.data;
      this.assets = res.data.assets || [];
      this.cfg = {
        title: res.data.title || '',
        description: res.data.description || '',
        instructions: res.data.instructions || '',
        tables: (res.data.tables || []).join('\n'),
        metricViews: (res.data.metric_views || []).join('\n'),
      };
    },

    async loadMessages() {
      const res = await window.pqlApi.fetch(
        '/api/genie/spaces/' + encodeURIComponent(this.slug) + '/messages'
      );
      if (res.ok) this.messages = (res.data && res.data.messages) || [];
    },

    async ask() {
      const q = this.question.trim();
      if (!q || this.asking) return;
      this.error = '';
      this.asking = true;
      const res = await window.pqlApi.fetch(
        '/api/genie/spaces/' + encodeURIComponent(this.slug) + '/ask',
        { method: 'POST', body: { question: q } }
      );
      this.asking = false;
      // Successful or not, the transcript carries the outcome —
      // reload it so error turns appear exactly as persisted.
      await this.loadMessages();
      if (!res.ok) {
        this.error = res.error || 'Genie could not answer that question';
        return;
      }
      this.question = '';
      this.lastResult = {
        messageId: res.data.message_id,
        columns: res.data.columns || [],
        rows: res.data.rows || [],
        rowCount: res.data.row_count,
        truncated: !!res.data.truncated,
      };
    },

    displayRows() {
      if (!this.lastResult) return [];
      return this.lastResult.rows.slice(0, DISPLAY_ROW_CAP);
    },

    toggleSql(messageId) {
      this.expandedSql[messageId] = !this.expandedSql[messageId];
    },

    async feedback(message, value) {
      const res = await window.pqlApi.fetch('/api/genie/messages/' + message.id + '/feedback', {
        method: 'POST',
        body: { feedback: value },
      });
      if (res.ok) message.feedback = res.data.feedback;
    },

    async promote(message) {
      this.error = '';
      const res = await window.pqlApi.fetch('/api/genie/messages/' + message.id + '/promote', {
        method: 'POST',
        body: {},
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to promote the answer';
        return;
      }
      await this.loadSpace();
    },

    useAsset(asset) {
      this.question = asset.question;
    },

    async runAsset(asset) {
      // Run the saved SQL deterministically (no LLM round-trip) and
      // render it through the same result table as an ask.
      this.error = '';
      const res = await window.pqlApi.fetch(
        '/api/genie/spaces/' + encodeURIComponent(this.slug) + '/assets/' + asset.id + '/run',
        { method: 'POST', body: {} }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to run the trusted question';
        return;
      }
      this.lastResult = {
        messageId: null,
        columns: res.data.columns || [],
        rows: res.data.rows || [],
        rowCount: res.data.row_count,
        truncated: !!res.data.truncated,
      };
    },

    async addAsset() {
      this.assetError = '';
      const res = await window.pqlApi.fetch(
        '/api/genie/spaces/' + encodeURIComponent(this.slug) + '/assets',
        {
          method: 'POST',
          body: { question: this.newAsset.question.trim(), sql_text: this.newAsset.sql.trim() },
        }
      );
      if (!res.ok) {
        this.assetError = res.error || 'Failed to add the trusted question';
        return;
      }
      this.newAsset = { question: '', sql: '' };
      await this.loadSpace();
    },

    async deleteAsset(asset) {
      if (!window.confirm('Delete trusted question "' + asset.question + '"?')) return;
      const res = await window.pqlApi.fetch(
        '/api/genie/spaces/' + encodeURIComponent(this.slug) + '/assets/' + asset.id,
        { method: 'DELETE' }
      );
      if (res.ok) await this.loadSpace();
    },

    toggleConfig() {
      this.showConfig = !this.showConfig;
      if (this.showConfig) this.loadSuggestions();
    },

    async loadSuggestions() {
      // Lineage-authority-ranked tables not yet curated — one click
      // appends one to the tables textarea.
      const res = await window.pqlApi.fetch(
        '/api/genie/spaces/' + encodeURIComponent(this.slug) + '/suggested-tables'
      );
      if (res.ok) this.suggestions = (res.data && res.data.suggestions) || [];
    },

    addSuggestion(table) {
      const current = this._lines(this.cfg.tables);
      if (!current.includes(table)) current.push(table);
      this.cfg.tables = current.join('\n');
      this.suggestions = this.suggestions.filter((s) => s.table !== table);
    },

    _lines(text) {
      return text
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.length > 0);
    },

    async saveConfig() {
      this.cfgError = '';
      this.cfgSaving = true;
      const res = await window.pqlApi.fetch('/api/genie/spaces/' + encodeURIComponent(this.slug), {
        method: 'PATCH',
        body: {
          title: this.cfg.title.trim(),
          description: this.cfg.description.trim() || null,
          instructions: this.cfg.instructions.trim() || null,
          tables: this._lines(this.cfg.tables),
          metric_views: this._lines(this.cfg.metricViews),
        },
      });
      this.cfgSaving = false;
      if (!res.ok) {
        this.cfgError = res.error || 'Failed to save the configuration';
        return;
      }
      this.showConfig = false;
      await this.loadSpace();
    },
  };
}
