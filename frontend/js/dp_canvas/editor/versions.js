/*
 * Version history for the canvas editor.
 *
 * The versions dropdown, pin / unpin of a production version, and restore
 * of an earlier version (which saves it forward as a new version).
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const versionsMethods = {
  async openVersionsDropdown() {
    this.versionsOpen = !this.versionsOpen;
    if (!this.versionsOpen) return;
    await this._refreshVersionsList();
  },
  async _refreshVersionsList() {
    const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/versions`, {
      silent: true,
    });
    if (res.ok) {
      this.versionsList = res.data.versions || [];
      this.pinnedVersion = res.data.pinned_version ?? null;
    }
  },
  async togglePin(v) {
    if (!this.canWrite) return;
    const action = v.is_production ? 'unpin' : 'pin';
    const res = await window.pqlApi.fetch(
      `/api/dp/${this.product.id}/canvas/versions/${v.version}/${action}`,
      { method: 'POST', silent: true }
    );
    if (!res.ok) {
      window.alert(action + ' failed: ' + (res.error || 'rejected'));
      return;
    }
    await this._refreshVersionsList();
  },
  async restoreVersion(version) {
    if (!this.canWrite) return;
    if (!window.confirm('Restore canvas to v' + version + '? This creates a new version.')) {
      return;
    }
    const fetched = await window.pqlApi.fetch(
      `/api/dp/${this.product.id}/canvas/versions/${version}`,
      { silent: true }
    );
    if (!fetched.ok) {
      window.alert('Restore failed: ' + (fetched.error || 'cannot load version'));
      return;
    }
    const doc = fetched.data.document;
    const saved = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas`, {
      method: 'POST',
      body: { document: doc },
      silent: true,
    });
    if (!saved.ok) {
      window.alert('Restore failed: ' + (saved.error || 'save rejected'));
      return;
    }
    this.version = saved.data.version;
    this._suppressAutosave = true;
    this._loadIntoDrawflow(doc);
    this._suppressAutosave = false;
    this.saveState = 'saved';
    this.lastSavedAt = saved.data.created_at;
    this.versionsOpen = false;
    this._scheduleValidate();
  },
};
