// Genie spaces list (/genie).
//
// genieSpaces: workspace space listing + an inline create form that
// navigates into the new room on success.

export function genieSpaces() {
  return {
    spaces: [],
    loading: false,
    error: '',

    creating: false,
    form: { title: '', description: '' },
    createError: '',
    saving: false,

    async init() {
      this.loading = true;
      const res = await window.pqlApi.fetch('/api/genie/spaces');
      this.loading = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to load Genie spaces';
        return;
      }
      this.spaces = (res.data && res.data.spaces) || [];
    },

    async create() {
      this.createError = '';
      this.saving = true;
      const body = { title: this.form.title.trim() };
      if (this.form.description.trim()) body.description = this.form.description.trim();
      const res = await window.pqlApi.fetch('/api/genie/spaces', {
        method: 'POST',
        body: body,
      });
      this.saving = false;
      if (!res.ok) {
        this.createError = res.error || 'Failed to create the space';
        return;
      }
      window.location.href = '/genie/' + encodeURIComponent(res.data.slug);
    },
  };
}
