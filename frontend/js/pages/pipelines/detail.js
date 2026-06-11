// Pipeline editor + run history (/pipelines/{slug}).
//
// pipelineDetail: dataset rows (target / kind / SELECT /
// expectations), definition save, run-now with inline result, and
// the run-history table.

export function pipelineDetail(pipeline, canEdit) {
  return {
    slug: pipeline.slug,
    canEdit: canEdit,
    datasets: (pipeline.datasets || []).map((d) => ({
      name: d.name,
      kind: d.kind,
      sql: d.sql,
      expectations: (d.expectations || []).map((e) => ({
        name: e.name,
        constraint: e.constraint,
        action: e.action,
      })),
    })),
    runs: [],
    error: '',
    saving: false,
    running: false,

    async init() {
      await this.loadRuns();
    },

    async loadRuns() {
      const res = await window.pqlApi.fetch('/api/pipelines/' + this.slug + '/runs');
      if (res.ok) this.runs = (res.data && res.data.runs) || [];
    },

    _payload() {
      return this.datasets.map((d) => ({
        name: (d.name || '').trim(),
        kind: d.kind,
        sql: (d.sql || '').trim(),
        expectations: d.expectations.filter((e) => e.name && e.constraint),
      }));
    },

    async save() {
      this.error = '';
      this.saving = true;
      const res = await window.pqlApi.fetch('/api/pipelines/' + this.slug, {
        method: 'PATCH',
        body: { datasets: this._payload() },
      });
      this.saving = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to save pipeline';
        return;
      }
      if (window.pqlToast) window.pqlToast('Pipeline definition saved.');
    },

    async run() {
      this.error = '';
      this.running = true;
      const res = await window.pqlApi.fetch('/api/pipelines/' + this.slug + '/run', {
        method: 'POST',
        body: {},
      });
      this.running = false;
      if (!res.ok) {
        this.error = res.error || 'Run failed to start';
        return;
      }
      await this.loadRuns();
    },

    async remove() {
      if (!window.confirm('Delete pipeline "' + this.slug + '" with its run history?')) return;
      const res = await window.pqlApi.fetch('/api/pipelines/' + this.slug, { method: 'DELETE' });
      if (!res.ok) return;
      window.location.href = '/pipelines';
    },
  };
}
