// Generic key/value dict editor that PATCHes {[field]: {...}}. Used by
// propertiesEditor (properties) and optionsEditor (foreign-catalog options).
function _makeDictEditor(field, patchUrl, initial) {
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
            const hadRows = this.snapshot.length > 0;
            if (field === 'properties' && hadRows && Object.keys(dict).length === 0) {
                this.error = 'Unity Catalog cannot clear all properties at once. Leave at least one row.';
                return;
            }
            this.saving = true;
            this.error = null;
            const body = {};
            body[field] = dict;
            const res = await window.pqlApi.fetch(patchUrl, {
                method: 'PATCH',
                body: body,
            });
            if (res.ok) {
                this.rows = toRows((res.data && res.data[field]) || {});
                this.snapshot = [];
                this.editing = false;
            } else {
                this.error = 'Save failed: ' + res.error;
            }
            this.saving = false;
        },
    };
}

window.optionsEditor = function ({ patchUrl, initial }) {
    return _makeDictEditor('options', patchUrl, initial);
};

window.propertiesEditor = function ({ patchUrl, initial }) {
    return _makeDictEditor('properties', patchUrl, initial);
};
