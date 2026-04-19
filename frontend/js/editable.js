// Generic single-field inline editor.  Sprint 75 Phase 3 migrates this
// from window-IIFE to a native ES module; bootstrap.js re-attaches the
// factory to ``window.editable`` for Alpine x-data lookup.
export function editable({ patchUrl, field, initial, placeholder }) {
    return {
        current: initial || '',
        placeholder: placeholder || '',
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
                this.current = (res.data && res.data[field] !== undefined) ? res.data[field] : this.draft;
                this.editing = false;
            } else {
                this.error = 'Save failed: ' + res.error;
            }
            this.saving = false;
        },
    };
}
