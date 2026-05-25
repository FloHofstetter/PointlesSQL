// Generic single-field inline editor — native ES module;
// bootstrap.js re-attaches the factory to ``window.editable`` for
// Alpine x-data lookup.
//
// added the ``multiline`` flag so the same factory
// powers both single-line title edits and multi-line description
// edits.  The partial chooses <input> vs <textarea> off the same
// flag; no behavioural difference here other than skipping
// Enter-to-save when multiline so newlines stay typeable.
export function editable({ patchUrl, field, initial, placeholder, multiline }) {
  return {
    current: initial || '',
    placeholder: placeholder || '',
    multiline: !!multiline,
    draft: '',
    editing: false,
    saving: false,
    error: null,

    start() {
      this.draft = this.current;
      this.error = null;
      this.editing = true;
      this.$nextTick(() => this.$refs.input?.focus());
    },

    cancel() {
      this.editing = false;
      this.error = null;
    },

    async save() {
      if (this.draft === this.current) {
        this.editing = false;
        return;
      }
      this.saving = true;
      this.error = null;
      const res = await window.pqlApi.fetch(patchUrl, {
        method: 'PATCH',
        body: { [field]: this.draft },
      });
      if (res.ok) {
        this.current = res.data && res.data[field] !== undefined ? res.data[field] : this.draft;
        this.editing = false;
        if (window.pqlToast) window.pqlToast.success('Saved.');
      } else {
        this.error = 'Save failed: ' + res.error;
        if (window.pqlToast) window.pqlToast.error('Save failed: ' + res.error);
      }
      this.saving = false;
    },
  };
}
