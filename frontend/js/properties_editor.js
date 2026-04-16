window.propertiesEditor = function ({ patchUrl, initial }) {
    const toRows = (dict) =>
        Object.entries(dict || {}).map(([key, value]) => ({ key, value: String(value) }));

    return {
        rows: toRows(initial),
        snapshot: [],
        editing: false,
        saving: false,
        error: null,

        start() {
            this.snapshot = JSON.parse(JSON.stringify(this.rows));
            this.error = null;
            this.editing = true;
        },

        cancel() {
            this.rows = this.snapshot;
            this.snapshot = [];
            this.editing = false;
            this.error = null;
        },

        addRow() {
            this.rows.push({ key: '', value: '' });
        },

        removeRow(index) {
            this.rows.splice(index, 1);
        },

        async save() {
            const dict = {};
            for (const { key, value } of this.rows) {
                const k = (key || '').trim();
                if (!k) continue;
                dict[k] = value ?? '';
            }
            const hadProps = this.snapshot.length > 0;
            if (hadProps && Object.keys(dict).length === 0) {
                this.error = 'Unity Catalog cannot clear all properties at once. Leave at least one row.';
                return;
            }
            this.saving = true;
            this.error = null;
            try {
                const res = await fetch(patchUrl, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ properties: dict }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                const data = await res.json();
                this.rows = toRows(data.properties || {});
                this.snapshot = [];
                this.editing = false;
            } catch (e) {
                this.error = 'Save failed: ' + e.message;
            } finally {
                this.saving = false;
            }
        },
    };
};
