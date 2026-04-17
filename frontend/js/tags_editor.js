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
            const res = await window.pqlApi.fetch(tagsUrl, {
                method: 'PATCH',
                body: { changes: [{ key, op: 'set', value: this.newValue || '' }] },
            });
            if (res.ok) {
                this.tags = res.data || [];
                this.newKey = '';
                this.newValue = '';
            } else {
                this.error = 'Failed to add tag: ' + res.error;
            }
            this.saving = false;
        },

        async removeTag(key) {
            this.saving = true;
            this.error = null;
            const res = await window.pqlApi.fetch(tagsUrl, {
                method: 'PATCH',
                body: { changes: [{ key, op: 'remove' }] },
            });
            if (res.ok) {
                this.tags = res.data || [];
            } else {
                this.error = 'Failed to remove tag: ' + res.error;
            }
            this.saving = false;
        },
    };
};
