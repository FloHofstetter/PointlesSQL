// Auto-extracted from frontend/templates/pages/issues_index.html.
// Exports: issuesIndex.
//
export function issuesIndex() {
  return {
    ...window.bulkSelect(),
    rows: [],
    filter: '',
    chip: 'all',
    init() {
      this.refresh();
    },
    setChip(c) {
      this.chip = c;
      this.clearSelection();
      this.refresh();
    },
    async refresh() {
      const params = new URLSearchParams();
      if (this.chip === 'open') params.set('state', 'open');
      else if (this.chip === 'closed') params.set('state', 'closed');
      else if (this.chip === 'mine_assigned' && window.pqlCurrentUserId) {
        params.set('assignee_user_id', window.pqlCurrentUserId);
      } else if (this.chip === 'mine_opened' && window.pqlCurrentUserId) {
        params.set('opened_by_user_id', window.pqlCurrentUserId);
      }
      const res = await window.pqlApi.fetch('/api/issues?' + params.toString());
      this.rows = (res && res.ok && res.data && res.data.issues) || [];
    },
    get filteredRows() {
      const q = this.filter.trim().toLowerCase();
      if (!q) return this.rows;
      return this.rows.filter((r) => {
        if ((r.title || '').toLowerCase().includes(q)) return true;
        if ((r.labels || []).some((l) => l.toLowerCase().includes(q))) return true;
        return false;
      });
    },
    async bulkClose() {
      await this._bulkTransition('close', 'Closed');
    },
    async bulkReopen() {
      await this._bulkTransition('reopen', 'Reopened');
    },
    async _bulkTransition(verb, label) {
      const ids = this.selectedKeys;
      if (!ids.length) return;
      let failed = 0;
      await Promise.all(
        ids.map(async (id) => {
          const res = await window.pqlApi.fetch(
            '/api/issues/' + encodeURIComponent(id) + '/' + verb,
            { method: 'POST', silent: true }
          );
          if (!res.ok) failed++;
        })
      );
      this.clearSelection();
      await this.refresh();
      if (window.pqlToast) {
        if (failed === 0) window.pqlToast.success(label + ' ' + ids.length + ' issue(s).');
        else window.pqlToast.error(failed + ' of ' + ids.length + ' ' + verb + 's failed.');
      }
    },
  };
}
