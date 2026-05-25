// Auto-extracted from frontend/templates/pages/issue_detail.html.
// Exports: issueDetail.
//
export function issueDetail(issueId) {
  return {
    issue: { state: 'open', labels: [] },
    editingBody: false,
    editingBodyText: '',
    closeReason: '',
    canEdit: false,
    async init() {
      await this.refresh();
    },
    async refresh() {
      const res = await window.pqlApi.fetch('/api/issues/' + issueId);
      if (res && res.ok && res.data) {
        this.issue = res.data;
        this.canEdit = !!(
          window.pqlCurrentUserId &&
          (window.pqlIsAdmin ||
            window.pqlCurrentUserId === (this.issue.opened_by && this.issue.opened_by.user_id))
        );
      }
    },
    startEditBody() {
      this.editingBodyText = this.issue.body_md || '';
      this.editingBody = true;
    },
    async saveBody() {
      const res = await window.pqlApi.fetch('/api/issues/' + issueId, {
        method: 'PATCH',
        body: JSON.stringify({ body_md: this.editingBodyText }),
      });
      if (res && res.ok) {
        this.editingBody = false;
        await this.refresh();
      }
    },
    async close(notPlanned) {
      const body = { not_planned: !!notPlanned };
      if (this.closeReason) body.closed_reason = this.closeReason;
      await window.pqlApi.fetch('/api/issues/' + issueId + '/close', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      await this.refresh();
    },
    async reopen() {
      await window.pqlApi.fetch('/api/issues/' + issueId + '/reopen', { method: 'POST' });
      await this.refresh();
    },
  };
}
