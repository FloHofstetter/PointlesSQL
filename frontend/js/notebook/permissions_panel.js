/**
 * Per-notebook permission grants panel.
 *
 * Wires ``GET/PUT/DELETE /api/notebooks/permissions`` to a CRUD
 * panel.  Roles form a ``view < run < edit`` lattice — the server
 * is authoritative for the vocabulary, surfaced in the response's
 * ``roles`` array.
 *
 * Route enforcement (actually blocking actions on a notebook based
 * on the lattice) is still on the deferred list per * memory note; this panel is the CRUD surface only.
 */

export function installPermissionsPanel(state) {
  state.permissionsPanel = {
    open: false,
    rows: [],
    roles: ['view', 'run', 'edit'],
    loaded: false,
    loading: false,
    submitting: false,
    error: '',
    draftUserId: '',
    draftRole: 'view',
  };

  state.togglePermissionsPanel = async function () {
    this.permissionsPanel.open = !this.permissionsPanel.open;
    if (this.permissionsPanel.open && !this.permissionsPanel.loaded) {
      await this.loadPermissions();
    }
  };

  state.loadPermissions = async function () {
    if (!this.path) return;
    this.permissionsPanel.loading = true;
    this.permissionsPanel.error = '';
    try {
      const res = await window.pqlApi.fetch(
        `/api/notebooks/permissions?path=${encodeURIComponent(this.path)}`,
        { silent: true }
      );
      if (res.ok && res.data) {
        this.permissionsPanel.rows = res.data.permissions || [];
        if (Array.isArray(res.data.roles) && res.data.roles.length) {
          this.permissionsPanel.roles = res.data.roles;
        }
        this.permissionsPanel.loaded = true;
      } else {
        this.permissionsPanel.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
      }
    } catch (err) {
      this.permissionsPanel.error = (err && err.message) || String(err);
    } finally {
      this.permissionsPanel.loading = false;
    }
  };

  state.submitPermission = async function () {
    const userId = Number.parseInt(this.permissionsPanel.draftUserId, 10);
    if (!Number.isFinite(userId) || userId <= 0) {
      this.permissionsPanel.error = 'user_id must be a positive integer';
      return;
    }
    if (this.permissionsPanel.submitting) return;
    this.permissionsPanel.submitting = true;
    this.permissionsPanel.error = '';
    try {
      const res = await window.pqlApi.fetch('/api/notebooks/permissions', {
        method: 'PUT',
        body: {
          path: this.path,
          user_id: userId,
          role: this.permissionsPanel.draftRole,
        },
      });
      if (!res.ok) {
        this.permissionsPanel.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
        return;
      }
      this.permissionsPanel.draftUserId = '';
      await this.loadPermissions();
    } catch (err) {
      this.permissionsPanel.error = (err && err.message) || String(err);
    } finally {
      this.permissionsPanel.submitting = false;
    }
  };

  /**
   * Inline-edit a row's role (server upserts the same (notebook, user)
   * pair).
   */
  state.updatePermissionRole = async function (row, newRole) {
    if (!row || row.role === newRole) return;
    if (this.permissionsPanel.submitting) return;
    this.permissionsPanel.submitting = true;
    this.permissionsPanel.error = '';
    try {
      const res = await window.pqlApi.fetch('/api/notebooks/permissions', {
        method: 'PUT',
        body: {
          path: this.path,
          user_id: row.user_id,
          role: newRole,
        },
      });
      if (!res.ok) {
        this.permissionsPanel.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
        return;
      }
      await this.loadPermissions();
    } catch (err) {
      this.permissionsPanel.error = (err && err.message) || String(err);
    } finally {
      this.permissionsPanel.submitting = false;
    }
  };

  state.revokePermission = async function (row) {
    if (!row || !row.user_id) return;
    if (this.permissionsPanel.submitting) return;
    this.permissionsPanel.submitting = true;
    this.permissionsPanel.error = '';
    try {
      const res = await window.pqlApi.fetch(
        `/api/notebooks/permissions?path=${encodeURIComponent(this.path)}&user_id=${encodeURIComponent(row.user_id)}`,
        { method: 'DELETE' }
      );
      if (!res.ok) {
        this.permissionsPanel.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
        return;
      }
      await this.loadPermissions();
    } catch (err) {
      this.permissionsPanel.error = (err && err.message) || String(err);
    } finally {
      this.permissionsPanel.submitting = false;
    }
  };
}
