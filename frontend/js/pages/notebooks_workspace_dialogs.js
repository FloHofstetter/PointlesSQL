/**
 * Bootstrap-modal dialogs for the notebooks workspace.
 *
 * Exposed as a *mixin* — the workspace factory spreads the returned
 * object into its own state so dialog methods can call the existing
 * ``_createNotebookApi`` / ``_renameNotebookApi`` / ``_deleteNotebookApi``
 * via ``this`` inside the same Alpine ``$data`` proxy.
 *
 * Replaces the previous native ``window.prompt`` / ``window.confirm``
 * flow.  Validation runs client-side so the user sees the error
 * before the round-trip.
 */

function _validatePath(raw) {
  const path = String(raw || '').trim();
  if (!path) return 'Path is required.';
  if (path.startsWith('/')) return 'Path must be relative (no leading /).';
  if (path.endsWith('/')) return 'Path must point at a file, not a directory.';
  if (path.includes('//')) return 'Path must not contain empty segments.';
  if (path.split('/').some((s) => s === '..' || s === '.')) {
    return 'Path must not contain "." or ".." segments.';
  }
  if (!path.endsWith('.py')) return 'Path must end with .py';
  return null;
}

export function notebookDialogs() {
  return {
    pathDialog: {
      open: false,
      mode: 'create',
      value: '',
      originalPath: '',
      error: '',
      submitting: false,
      templateId: '',
    },
    deleteDialog: {
      open: false,
      path: '',
      submitting: false,
    },
    // starter-template gallery.  Fetched lazily on first
    // open of the create dialog so the workspace page doesn't pay for
    // it until the user clicks New.
    templates: [],
    templatesLoaded: false,

    async _loadTemplatesOnce() {
      if (this.templatesLoaded) return;
      try {
        const res = await fetch('/api/notebooks/templates', {
          credentials: 'same-origin',
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        this.templates = Array.isArray(body?.templates) ? body.templates : [];
      } catch {
        // Fail-quiet: an empty gallery means the user gets the empty
        // notebook path — same as the legacy behaviour.
        this.templates = [];
      } finally {
        this.templatesLoaded = true;
      }
    },

    openCreate() {
      // Mutate fields in place — replacing pathDialog as a whole would
      // detach Alpine bindings that captured deps on the old proxy.
      this.pathDialog.mode = 'create';
      this.pathDialog.value = 'new_notebook.py';
      this.pathDialog.originalPath = '';
      this.pathDialog.error = '';
      this.pathDialog.submitting = false;
      this.pathDialog.templateId = '';
      this.pathDialog.open = true;
      void this._loadTemplatesOnce();
      this.$nextTick(() => {
        // scope-local $refs, so the same modal partial
        // can mount in both the workspace-page factory and the
        // workspace-sidebar factory without an ID collision.
        const el = this.$refs ? this.$refs.pathInput : null;
        if (el) {
          el.focus();
          el.setSelectionRange(0, el.value.length - 3);
        }
      });
    },

    openRename(path) {
      this.pathDialog.mode = 'rename';
      this.pathDialog.value = path;
      this.pathDialog.originalPath = path;
      this.pathDialog.error = '';
      this.pathDialog.submitting = false;
      this.pathDialog.open = true;
      this.$nextTick(() => {
        const el = this.$refs ? this.$refs.pathInput : null;
        if (el) {
          el.focus();
          el.setSelectionRange(0, el.value.length - 3);
        }
      });
    },

    closePathDialog() {
      if (this.pathDialog.submitting) return;
      this.pathDialog.open = false;
    },

    validatePathInput() {
      this.pathDialog.error = _validatePath(this.pathDialog.value) || '';
    },

    async submitPathDialog() {
      const err = _validatePath(this.pathDialog.value);
      if (err) {
        this.pathDialog.error = err;
        return;
      }
      const path = this.pathDialog.value.trim();
      if (this.pathDialog.mode === 'rename' && path === this.pathDialog.originalPath) {
        this.pathDialog.error = 'New path is identical to the current one.';
        return;
      }
      this.pathDialog.submitting = true;
      try {
        let ok;
        if (this.pathDialog.mode === 'create') {
          ok = this.pathDialog.templateId
            ? await this._createFromTemplateApi(this.pathDialog.templateId, path)
            : await this._createNotebookApi(path);
        } else {
          ok = await this._renameNotebookApi(this.pathDialog.originalPath, path);
        }
        // Keep the dialog open on failure so the typed path (and the
        // toasted error) survive for a retry.
        if (ok) this.pathDialog.open = false;
      } finally {
        this.pathDialog.submitting = false;
      }
    },

    async _createFromTemplateApi(templateId, path) {
      const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['X-CSRFToken'] = decodeURIComponent(token[1]);
      const res = await fetch('/api/notebooks/from-template', {
        method: 'POST',
        credentials: 'same-origin',
        headers,
        body: JSON.stringify({ template_id: templateId, path }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (window.pqlToast) {
          window.pqlToast.error(body?.detail || `Create failed (HTTP ${res.status})`);
        }
        return false;
      }
      const body = await res.json();
      window.location.assign(`/notebooks/edit/${encodeURIComponent(body.path || path)}`);
      return true;
    },

    openDeleteDialog(path) {
      this.deleteDialog.path = path;
      this.deleteDialog.submitting = false;
      this.deleteDialog.open = true;
    },

    closeDeleteDialog() {
      if (this.deleteDialog.submitting) return;
      this.deleteDialog.open = false;
    },

    async submitDeleteDialog() {
      this.deleteDialog.submitting = true;
      try {
        const ok = await this._deleteNotebookApi(this.deleteDialog.path);
        if (ok) this.deleteDialog.open = false;
      } finally {
        this.deleteDialog.submitting = false;
      }
    },
  };
}
