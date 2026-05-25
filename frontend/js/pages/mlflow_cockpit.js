// Cockpit factory for the slim /mlflow page.
// Consumes existing routes only — no new server endpoint added
// for this view; the runs payload is filtered client-side because
// /api/runs has no has_mlflow filter today.

export const mlflowCockpit = () => ({
  models: [],
  modelsLoading: true,
  runs: [],
  runsLoading: true,

  async init() {
    await Promise.all([this._loadModels(), this._loadRuns()]);
  },

  async _loadModels() {
    try {
      const r = await fetch('/api/models?enrich_latest=false', {
        credentials: 'same-origin',
      });
      if (r.ok) {
        const data = await r.json();
        this.models = (data.models || []).slice(0, 10);
      }
    } catch (e) {
      /* silent — MLflow extra not installed */
    }
    this.modelsLoading = false;
  },

  async _loadRuns() {
    try {
      const r = await fetch('/api/runs?offset=0', {
        credentials: 'same-origin',
      });
      if (r.ok) {
        const data = await r.json();
        this.runs = (data.runs || []).filter((run) => run.mlflow_run_id).slice(0, 5);
      }
    } catch (e) {
      /* silent */
    }
    this.runsLoading = false;
  },
});
