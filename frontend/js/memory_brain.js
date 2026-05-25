// Memory page client-side glue.
//
// Two Alpine factories + one click handler:
//
// * memoryRecall(agentId) — server-side filtering of the
//   /api/memory/<agent>/recall endpoint with a debounced refresh.
//   Reused inside the Operations tab's Alpine scope.
// * memoryDiscussion(kind, ref) — kind-agnostic copy of
//   runDiscussion, swapped to the polymorphic
//   /api/social/<kind>/<ref>/comments endpoint family.
// * window.memoryReplayBranch(buttonEl) — fired from the
//   Branches tab; POSTs /api/memory/<agent>/replay and follows
//   the HX-Redirect header on success.

(() => {
  function memoryRecall(agentId) {
    return {
      filter: {
        op_name: '',
        target_table: '',
        status: '',
        limit: 200,
      },
      operations: [],
      loading: false,
      init() {
        this.refresh();
      },
      async refresh() {
        this.loading = true;
        const qs = new URLSearchParams();
        if (this.filter.op_name) qs.set('op_name', this.filter.op_name);
        if (this.filter.target_table) qs.set('target_table', this.filter.target_table);
        if (this.filter.status) qs.set('status', this.filter.status);
        if (this.filter.limit) qs.set('limit', String(this.filter.limit));
        try {
          const resp = await fetch(
            '/api/memory/' + encodeURIComponent(agentId) + '/recall?' + qs.toString(),
            { credentials: 'same-origin' }
          );
          if (!resp.ok) {
            this.operations = [];
            return;
          }
          const data = await resp.json();
          this.operations = data.operations || [];
        } finally {
          this.loading = false;
        }
      },
    };
  }
  window.memoryRecall = memoryRecall;

  function memoryDiscussion(kind, ref) {
    const base =
      '/api/social/' + encodeURIComponent(kind) + '/' + encodeURIComponent(ref) + '/comments';
    return {
      comments: [],
      commentsLoaded: false,
      draftBody: '',
      postBusy: false,
      async init() {
        try {
          const resp = await fetch(base, { credentials: 'same-origin' });
          if (resp.ok) {
            const data = await resp.json();
            this.comments = data.comments || [];
          }
        } finally {
          this.commentsLoaded = true;
        }
      },
      async submitNew() {
        if (this.postBusy || !this.draftBody.trim()) return;
        this.postBusy = true;
        try {
          const resp = await fetch(base, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ body_md: this.draftBody }),
          });
          if (resp.ok) {
            this.draftBody = '';
            const data = await resp.json();
            this.comments = data.comments || this.comments;
          }
        } finally {
          this.postBusy = false;
        }
      },
    };
  }
  window.memoryDiscussion = memoryDiscussion;

  async function memoryReplayBranch(buttonEl) {
    const agentId = buttonEl.dataset.agentId;
    const branchFqn = buttonEl.dataset.branchFqn;
    const sourceRunId = buttonEl.dataset.sourceRunId;
    if (!agentId || !branchFqn || !sourceRunId) return;

    buttonEl.disabled = true;
    const origLabel = buttonEl.innerHTML;
    buttonEl.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Replaying…';

    try {
      const resp = await fetch('/api/memory/' + encodeURIComponent(agentId) + '/replay', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          branch_schema_fqn: branchFqn,
          source_run_id: sourceRunId,
          policy: 'skip_unsafe',
        }),
      });
      if (resp.redirected) {
        window.location.href = resp.url;
        return;
      }
      const redirect = resp.headers.get('HX-Redirect');
      if (redirect) {
        window.location.href = redirect;
        return;
      }
      if (!resp.ok) {
        const detail = await resp.text();
        alert('Replay failed: ' + detail.slice(0, 200));
      }
    } catch (err) {
      alert('Replay failed: ' + err);
    } finally {
      buttonEl.disabled = false;
      buttonEl.innerHTML = origLabel;
    }
  }
  window.memoryReplayBranch = memoryReplayBranch;
})();
