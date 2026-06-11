// Consumer-side Delta Sharing browser (/shared-with-me).
//
// sharedWithMe: provider-profile registration (the bearer token is
// the credential the remote side issued) + a drill-down browser:
// provider → shares → tables → 50-row preview fetched over the open
// protocol and rendered server-side as JSON rows.

export function sharedWithMe() {
  return {
    providers: [],
    error: '',
    form: { name: '', endpoint_url: '', token: '', comment: '' },
    creating: false,
    createError: '',

    active: '',
    browseError: '',
    browseShares: [],
    loadingShares: false,
    activeShare: '',
    tables: [],
    loadingTables: false,
    activeTable: null,
    preview: null,
    previewLoading: false,

    async init() {
      await this.loadProviders();
    },

    async loadProviders() {
      const res = await window.pqlApi.fetch('/api/sharing/providers');
      if (res.ok) this.providers = (res.data && res.data.providers) || [];
    },

    async createProvider() {
      this.createError = '';
      const name = this.form.name.trim();
      const endpointUrl = this.form.endpoint_url.trim();
      const token = this.form.token;
      if (!name || !endpointUrl || !token) {
        this.createError = 'Name, endpoint URL, and token are required.';
        return;
      }
      this.creating = true;
      const body = { name: name, endpoint_url: endpointUrl, token: token };
      if (this.form.comment.trim()) body.comment = this.form.comment.trim();
      const res = await window.pqlApi.fetch('/api/sharing/providers', {
        method: 'POST',
        body: body,
      });
      this.creating = false;
      if (!res.ok) {
        this.createError = res.error || 'Failed to register provider';
        return;
      }
      this.form = { name: '', endpoint_url: '', token: '', comment: '' };
      await this.loadProviders();
    },

    async removeProvider(provider) {
      if (!window.confirm('Delete provider "' + provider.name + '"?')) return;
      const res = await window.pqlApi.fetch(
        '/api/sharing/providers/' + encodeURIComponent(provider.name),
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      if (this.active === provider.name) this.closeBrowse();
      await this.loadProviders();
    },

    async browse(provider) {
      this.active = provider.name;
      this.browseError = '';
      this.browseShares = [];
      this.activeShare = '';
      this.tables = [];
      this.activeTable = null;
      this.preview = null;
      this.loadingShares = true;
      const res = await window.pqlApi.fetch(
        '/api/sharing/providers/' + encodeURIComponent(provider.name) + '/shares'
      );
      this.loadingShares = false;
      if (!res.ok) {
        this.browseError = res.error || 'Failed to list shares';
        return;
      }
      this.browseShares = (res.data && res.data.shares) || [];
    },

    closeBrowse() {
      this.active = '';
      this.browseError = '';
      this.browseShares = [];
      this.activeShare = '';
      this.tables = [];
      this.activeTable = null;
      this.preview = null;
    },

    async openShare(share) {
      this.browseError = '';
      this.activeShare = share;
      this.tables = [];
      this.activeTable = null;
      this.preview = null;
      this.loadingTables = true;
      const res = await window.pqlApi.fetch(
        '/api/sharing/providers/' +
          encodeURIComponent(this.active) +
          '/shares/' +
          encodeURIComponent(share) +
          '/tables'
      );
      this.loadingTables = false;
      if (!res.ok) {
        this.browseError = res.error || 'Failed to list tables';
        return;
      }
      this.tables = (res.data && res.data.tables) || [];
    },

    async openTable(table) {
      this.browseError = '';
      this.activeTable = table;
      this.preview = null;
      this.previewLoading = true;
      const res = await window.pqlApi.fetch(
        '/api/sharing/providers/' + encodeURIComponent(this.active) + '/read',
        {
          method: 'POST',
          body: {
            share: table.share || this.activeShare,
            schema: table.schema,
            table: table.name,
            limit: 50,
          },
        }
      );
      this.previewLoading = false;
      if (!res.ok) {
        this.browseError = res.error || 'Failed to preview table';
        return;
      }
      this.preview = res.data;
    },
  };
}
