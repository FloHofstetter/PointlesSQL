window.tagsEditor = function ({ tagsUrl, initial }) {
    return {
        tags: initial || [],
        newKey: '',
        newValue: '',
        saving: false,
        error: null,

        async addTag() {
            const key = (this.newKey || '').trim();
            if (!key) {
                this.error = 'Tag key is required.';
                return;
            }
            this.saving = true;
            this.error = null;
            try {
                const res = await fetch(tagsUrl, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        changes: [{ key, op: 'set', value: this.newValue || '' }],
                    }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                this.tags = await res.json();
                this.newKey = '';
                this.newValue = '';
            } catch (e) {
                this.error = 'Failed to add tag: ' + e.message;
            } finally {
                this.saving = false;
            }
        },

        async removeTag(key) {
            this.saving = true;
            this.error = null;
            try {
                const res = await fetch(tagsUrl, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        changes: [{ key, op: 'remove' }],
                    }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                this.tags = await res.json();
            } catch (e) {
                this.error = 'Failed to remove tag: ' + e.message;
            } finally {
                this.saving = false;
            }
        },
    };
};
