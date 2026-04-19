/**
 * SQL editor — saved-queries CRUD + load-into-editor flow.
 *
 * Sprint 91 split out of ``sql_editor.js``.  Owns the
 * ``/api/saved-queries`` round-trips: refresh the side panel,
 * load a row into the editor (``setSQL`` from the monaco mixin),
 * delete a row with confirm prompt, and the Save modal that
 * POSTs ``{title, description, sql, is_shared}`` from the
 * ``saveForm`` state.
 *
 * The Save modal is opened both from the toolbar button and from
 * the Cmd-S keymap registered in ``sql_editor_monaco.js``; both
 * paths route through ``openSaveModal()`` here.
 */

import { toast } from './api.js';

export const savedMethods = {
    async refreshSaved() {
        this.savedLoading = true;
        const res = await window.pqlApi.fetch('/api/saved-queries', { silent: true });
        this.savedLoading = false;
        this.saved = res.ok && Array.isArray(res.data) ? res.data : [];
    },

    loadSaved(row) {
        if (!row || typeof row.sql_text !== 'string') return;
        this.setSQL(row.sql_text);
        toast('info', `Loaded "${row.title}"`);
    },

    async deleteSaved(row) {
        if (!row || !row.slug) return;
        if (!window.confirm(`Delete saved query "${row.title}"?`)) return;
        const res = await window.pqlApi.fetch(
            `/api/saved-queries/${encodeURIComponent(row.slug)}`,
            { method: 'DELETE', silent: true },
        );
        if (res.ok || res.status === 204) {
            toast('success', `Deleted "${row.title}"`);
            await this.refreshSaved();
        } else {
            toast('error', res.error || `HTTP ${res.status}`);
        }
    },

    openSaveModal() {
        this.saveForm = { title: '', description: '', is_shared: false };
        const el = document.getElementById('pqlSaveQueryModal');
        if (!el || !window.bootstrap) return;
        const modal = window.bootstrap.Modal.getOrCreateInstance(el);
        modal.show();
    },

    async saveCurrent() {
        const sqlText = this.getSQL().trim();
        const title = (this.saveForm.title || '').trim();
        if (!title) {
            toast('error', 'Title is required.');
            return;
        }
        if (!sqlText) {
            toast('error', 'Nothing to save — the editor is empty.');
            return;
        }
        this.saving = true;
        const res = await window.pqlApi.fetch('/api/saved-queries', {
            method: 'POST',
            body: {
                title,
                description: this.saveForm.description || '',
                sql: sqlText,
                is_shared: !!this.saveForm.is_shared,
            },
            silent: true,
        });
        this.saving = false;
        if (res.ok && res.data) {
            toast('success', `Saved as "${res.data.title}"`);
            const el = document.getElementById('pqlSaveQueryModal');
            if (el && window.bootstrap) {
                window.bootstrap.Modal.getOrCreateInstance(el).hide();
            }
            await this.refreshSaved();
        } else {
            toast('error', res.error || `HTTP ${res.status}`);
        }
    },
};
