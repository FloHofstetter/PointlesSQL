// AI/BI dashboards list page (/bi).
//
// biDashboardsList: create-dashboard modal; on success the browser
// jumps straight into the new dashboard's editor.

export function biDashboardsList() {
  return {
    form: { title: '', description: '' },
    creating: false,
    error: '',

    async create() {
      this.error = '';
      this.creating = true;
      const body = { title: this.form.title.trim() };
      if (this.form.description) body.description = this.form.description.trim();
      const res = await window.pqlApi.fetch('/api/bi/dashboards', { method: 'POST', body: body });
      this.creating = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create dashboard';
        return;
      }
      window.location.href = `/bi/${res.data.slug}/edit`;
    },
  };
}
