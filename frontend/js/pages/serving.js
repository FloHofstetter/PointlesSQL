// Model-serving cockpit (/serving).
//
// servingEndpoints: create form + endpoint lifecycle (start / stop /
// delete) + a per-ready-endpoint "Try it" drawer that posts an
// MLflow-protocol scoring payload through the server-side proxy.
// After Start the list re-polls every 2 s until the endpoint leaves
// "starting" (60 s cap); the table is seeded server-side with the
// same shape GET /api/serving-endpoints answers.

const TRY_TEMPLATE = JSON.stringify({ dataframe_records: [{}] }, null, 2);

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_TICKS = 30; // 30 × 2 s = 60 s cap

export function servingEndpoints(initial) {
  return {
    endpoints: initial || [],
    form: { name: '', model_name: '', model_version: '' },
    creating: false,
    createError: '',
    error: '',
    busy: {},
    tryOpen: {},
    tryBodies: {},
    tryResults: {},
    polling: false,

    ago(iso) {
      if (!iso) return '—';
      if (typeof window.pqlRelativeTime === 'function') return window.pqlRelativeTime(iso);
      return iso;
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

    async refresh() {
      const res = await window.pqlApi.fetch('/api/serving-endpoints', { silent: true });
      if (res.ok) this.endpoints = (res.data && res.data.endpoints) || [];
    },

    async create() {
      this.createError = '';
      const name = this.form.name.trim();
      const modelName = this.form.model_name.trim();
      const modelVersion = this.form.model_version.trim();
      if (!name || !modelName || !modelVersion) {
        this.createError = 'Name, model name, and model version are required.';
        return;
      }
      this.creating = true;
      const res = await window.pqlApi.fetch('/api/serving-endpoints', {
        method: 'POST',
        body: { name: name, model_name: modelName, model_version: modelVersion },
      });
      this.creating = false;
      if (!res.ok) {
        this.createError = res.error || 'Failed to create endpoint';
        return;
      }
      this.form = { name: '', model_name: '', model_version: '' };
      await this.refresh();
    },

    async start(ep) {
      this.error = '';
      this.busy[ep.name] = true;
      // Fire the start request and poll the list in parallel: the
      // server-side start blocks until the worker is healthy, so
      // polling is what paints the intermediate "starting" badge.
      const pending = window.pqlApi.fetch(
        '/api/serving-endpoints/' + encodeURIComponent(ep.name) + '/start',
        { method: 'POST' }
      );
      this.pollWhileStarting(ep.name);
      const res = await pending;
      this.busy[ep.name] = false;
      if (!res.ok) this.error = res.error || 'Failed to start endpoint';
      await this.refresh();
    },

    async pollWhileStarting(name) {
      if (this.polling) return;
      this.polling = true;
      try {
        for (let tick = 0; tick < POLL_MAX_TICKS; tick++) {
          await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
          await this.refresh();
          const ep = this.endpoints.find((e) => e.name === name);
          if (!ep || ep.state !== 'starting') return;
        }
      } finally {
        this.polling = false;
      }
    },

    async stop(ep) {
      this.error = '';
      this.busy[ep.name] = true;
      const res = await window.pqlApi.fetch(
        '/api/serving-endpoints/' + encodeURIComponent(ep.name) + '/stop',
        { method: 'POST' }
      );
      this.busy[ep.name] = false;
      if (!res.ok) this.error = res.error || 'Failed to stop endpoint';
      await this.refresh();
    },

    async remove(ep) {
      if (!window.confirm('Delete serving endpoint "' + ep.name + '"?')) return;
      const res = await window.pqlApi.fetch(
        '/api/serving-endpoints/' + encodeURIComponent(ep.name),
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      delete this.tryOpen[ep.name];
      await this.refresh();
    },

    toggleTry(ep) {
      this.tryOpen[ep.name] = !this.tryOpen[ep.name];
      if (this.tryOpen[ep.name] && !this.tryBodies[ep.name]) {
        this.tryBodies[ep.name] = TRY_TEMPLATE;
      }
    },

    async invoke(ep) {
      this.error = '';
      let payload;
      try {
        payload = JSON.parse(this.tryBodies[ep.name] || '');
      } catch (err) {
        this.tryResults[ep.name] = 'Request body is not valid JSON: ' + err.message;
        return;
      }
      this.busy[ep.name] = true;
      const res = await window.pqlApi.fetch(
        '/api/serving-endpoints/' + encodeURIComponent(ep.name) + '/invocations',
        { method: 'POST', body: payload }
      );
      this.busy[ep.name] = false;
      if (!res.ok) {
        this.tryResults[ep.name] = res.error || 'Invocation failed';
        return;
      }
      this.tryResults[ep.name] = JSON.stringify(res.data, null, 2);
      await this.refresh();
    },
  };
}
