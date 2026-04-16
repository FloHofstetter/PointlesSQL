window.editable = function ({ patchUrl, field, initial, placeholder }) {
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
            try {
                const res = await fetch(patchUrl, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ [field]: this.draft }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                const data = await res.json();
                this.current = data[field] ?? this.draft;
                this.editing = false;
            } catch (e) {
                this.error = 'Save failed: ' + e.message;
            } finally {
                this.saving = false;
            }
        },
    };
};
