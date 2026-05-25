// Auto-extracted from frontend/templates/partials/social/_issues_pane.html.
// Exports: issuesPane.
//
export function issuesPane(args) {
  return {
    kind: args.kind,
    ref: args.ref,
    issues: [],
    loading: true,
    showCreate: false,
    newTitle: '',
    newBody: '',
    async init() {
      await this.refresh();
    },
    async refresh() {
      this.loading = true;
      try {
        const url = `/api/social/${encodeURIComponent(this.kind)}/${encodeURI(this.ref)}/issues`;
        const res = await window.pqlApi.fetch(url);
        this.issues = (res && res.ok && res.data && res.data.issues) || [];
      } finally {
        this.loading = false;
      }
    },
    async submit() {
      const url = `/api/social/${encodeURIComponent(this.kind)}/${encodeURI(this.ref)}/issues`;
      const res = await window.pqlApi.fetch(url, {
        method: 'POST',
        body: JSON.stringify({
          title: this.newTitle.trim(),
          body_md: this.newBody || '',
        }),
      });
      if (res && res.ok) {
        this.showCreate = false;
        this.newTitle = '';
        this.newBody = '';
        await this.refresh();
      }
    },
  };
}
