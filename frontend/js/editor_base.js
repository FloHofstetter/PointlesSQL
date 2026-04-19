// Phase 12.7 Sprint 75 Phase 3 — shared helpers for inline editors.
//
// Two real cross-cutting concerns extracted from the per-editor IIFEs:
//
//   - ``validateRequired(value, fieldName)`` returns a human error
//     message or ``null``.  Used by tags / permissions editors and the
//     federation create-forms — the trim-and-null-check pattern was
//     copy-pasted across six call sites.
//
//   - ``createDictEditor(field, patchUrl, initial)`` is the
//     start/cancel/save/addRow/removeRow state machine that
//     ``propertiesEditor`` and ``optionsEditor`` shared via the
//     pre-Sprint-75 ``_makeDictEditor`` private helper.  Promoted out
//     of properties_editor.js so the cross-module reach is explicit.
//
// What is INTENTIONALLY NOT extracted:
//
//   The ``if (res.ok) { ... } else { this.error = 'X: ' + res.error; }``
//   error-handling block looks like duplication, but every consumer's
//   onSuccess body is unique (assign to different fields, reset
//   different inputs, redirect, etc.).  Wrapping it costs more in
//   reader-overhead than the ~3 lines per site it saves.  Per the
//   simplify-skill discipline: a 5th argument to a generic helper is
//   the signal to abandon the abstraction for that consumer.

export function validateRequired(value, fieldName) {
    const trimmed = (value == null ? '' : String(value)).trim();
    if (!trimmed) return `${fieldName} is required.`;
    return null;
}

export function createDictEditor(field, patchUrl, initial) {
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
                body,
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
