// Pipelines list (/pipelines).
//
// pipelinesList: list + a create form that seeds the pipeline with
// one materialized view so the editor opens with something real.

export function pipelinesList() {
  return {
    pipelines: [],
    creating: false,
    saving: false,
    error: '',
    form: { title: '', description: '', target: '', sql: '' },

    async load() {
      const res = await window.pqlApi.fetch('/api/pipelines');
      if (res.ok) this.pipelines = (res.data && res.data.pipelines) || [];
    },

    async create() {
      this.error = '';
      this.saving = true;
      const res = await window.pqlApi.fetch('/api/pipelines', {
        method: 'POST',
        body: {
          title: this.form.title.trim(),
          description: this.form.description || null,
          datasets: [
            {
              name: this.form.target.trim(),
              kind: 'materialized_view',
              sql: this.form.sql.trim(),
              expectations: [],
            },
          ],
        },
      });
      this.saving = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create pipeline';
        return;
      }
      window.location.href = '/pipelines/' + res.data.slug;
    },
  };
}
