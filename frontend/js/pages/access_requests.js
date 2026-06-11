// Access requests (/access-requests).
//
// accessRequests: two-tab inbox.  "My requests" is the caller's own
// request history (cancel while pending); "To decide" is the pending
// queue the caller may decide — owners see their snapshot matches,
// admins see everything.  Deciding happens through a small inline
// panel so a deny always carries the mandatory note.

export function accessRequests(isAdmin) {
  return {
    isAdmin: !!isAdmin,
    tab: 'mine',
    mine: [],
    decide: [],
    loaded: false,
    busy: false,
    error: '',
    // {id, full_name, requester_email, action, note} while the
    // approve/deny confirmation panel is open; null otherwise.
    decision: null,

    get showDecideTab() {
      return this.isAdmin || this.decide.length > 0;
    },

    async load() {
      const [mineRes, decideRes] = await Promise.all([
        window.pqlApi.fetch('/api/access-requests?role=requester'),
        window.pqlApi.fetch('/api/access-requests?role=decider'),
      ]);
      if (mineRes.ok) this.mine = mineRes.data?.requests || [];
      if (decideRes.ok) this.decide = decideRes.data?.requests || [];
      this.loaded = true;
    },

    statusBadge(status) {
      const map = {
        pending: 'bg-warning text-dark',
        approved: 'bg-success',
        denied: 'bg-danger',
        cancelled: 'bg-secondary',
      };
      return map[status] || 'bg-secondary';
    },

    tableHref(fullName) {
      const parts = String(fullName).split('.');
      if (parts.length !== 3) return null;
      const [cat, sch, tbl] = parts.map(encodeURIComponent);
      return `/catalogs/${cat}/schemas/${sch}/tables/${tbl}`;
    },

    beginDecision(req, action) {
      this.error = '';
      this.decision = {
        id: req.id,
        full_name: req.full_name,
        requester_email: req.requester_email,
        action: action,
        note: '',
      };
    },

    cancelDecision() {
      this.decision = null;
      this.error = '';
    },

    async confirmDecision() {
      const d = this.decision;
      if (!d) return;
      if (d.action === 'deny' && !d.note.trim()) {
        this.error = 'A note is required to deny a request.';
        return;
      }
      this.busy = true;
      const res = await window.pqlApi.fetch(`/api/access-requests/${d.id}/${d.action}`, {
        method: 'POST',
        body: { note: d.note.trim() || null },
        silent: true,
      });
      this.busy = false;
      if (!res.ok) {
        this.error = res.error || 'Decision failed.';
        return;
      }
      this.decision = null;
      window.pqlToast.success(d.action === 'approve' ? 'Request approved.' : 'Request denied.');
      await this.load();
    },

    async cancelRequest(req) {
      this.busy = true;
      const res = await window.pqlApi.fetch(`/api/access-requests/${req.id}/cancel`, {
        method: 'POST',
      });
      this.busy = false;
      if (res.ok) {
        window.pqlToast.success('Request cancelled.');
        await this.load();
      }
    },
  };
}
