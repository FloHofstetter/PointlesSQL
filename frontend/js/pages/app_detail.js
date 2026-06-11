// Hosted-app cockpit (/apps/<slug>).
//
// hostedAppDetail: lifecycle buttons + the proxied iframe + the
// stderr log tail + (admins) the app.py source editor. The app
// object is seeded server-side with the same shape
// GET /api/apps/<slug> answers; saving the source PATCHes it back
// and takes effect on the next start.

export function hostedAppDetail(initial, canAdmin) {
  return {
    app: initial || {},
    canAdmin: !!canAdmin,
    busy: false,
    error: '',
    logs: '',
    source: (initial && initial.source_code) || '',
    saving: false,
    saveMsg: '',

    init() {
      this.fetchLogs();
    },

    stateBadge(state) {
      return (
        {
          stopped: 'bg-secondary',
          starting: 'bg-warning text-dark',
          ready: 'bg-success',
          failed: 'bg-danger',
        }[state] || 'bg-secondary'
      );
    },

    proxyUrl() {
      return '/apps/' + encodeURIComponent(this.app.slug) + '/proxy/';
    },

    async refresh() {
      const res = await window.pqlApi.fetch('/api/apps/' + encodeURIComponent(this.app.slug), {
        silent: true,
      });
      if (res.ok && res.data) this.app = res.data;
    },

    async start() {
      this.error = '';
      this.busy = true;
      const res = await window.pqlApi.fetch(
        '/api/apps/' + encodeURIComponent(this.app.slug) + '/start',
        { method: 'POST' }
      );
      this.busy = false;
      if (!res.ok) this.error = res.error || 'Failed to start app';
      await this.refresh();
      await this.fetchLogs();
    },

    async stop() {
      this.error = '';
      this.busy = true;
      const res = await window.pqlApi.fetch(
        '/api/apps/' + encodeURIComponent(this.app.slug) + '/stop',
        { method: 'POST' }
      );
      this.busy = false;
      if (!res.ok) this.error = res.error || 'Failed to stop app';
      await this.refresh();
    },

    async fetchLogs() {
      const res = await window.pqlApi.fetch(
        '/api/apps/' + encodeURIComponent(this.app.slug) + '/logs',
        { silent: true }
      );
      if (res.ok && res.data) this.logs = (res.data.lines || []).join('\n');
    },

    async save() {
      this.saveMsg = '';
      this.error = '';
      this.saving = true;
      const res = await window.pqlApi.fetch('/api/apps/' + encodeURIComponent(this.app.slug), {
        method: 'PATCH',
        body: { source_code: this.source },
      });
      this.saving = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to save source';
        return;
      }
      if (res.data) this.app = res.data;
      this.saveMsg = 'Saved — restart the app to apply.';
    },
  };
}
