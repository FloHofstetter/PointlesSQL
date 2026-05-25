// rollback panel factory for the Operations top-tab on /runs/{id}.
//
// Used by ``pages/_partials/run_view/operations/uc_mutations.html``;
// the Alpine x-data invocation passes ``{runId, targets[]}`` from the
// Jinja-rendered initial state.  Talks to two routes:
//
//   GET  /api/runs/{id}/rollback-preview?target=…  preview before commit
//   POST /api/runs/{id}/rollback                    commit (admin only)
//
// Modal markup lives in the same partial; this factory owns the
// open/close + busy + error state.

export function rollbackPanel(initial) {
  return {
    runId: initial.runId,
    targets: initial.targets,
    selectedTarget: initial.targets.length > 0 ? initial.targets[0] : null,
    modalOpen: false,
    loading: false,
    busy: false,
    error: null,
    submitError: null,
    preview: null,
    opOrdinal: null,
    allowForce: false,
    get canSubmit() {
      if (!this.preview) return false;
      if (this.preview.op_id === null) {
        if (!this.opOrdinal) return false;
      }
      if (this.preview.is_stale && !this.allowForce) return false;
      return true;
    },
    async openModal() {
      this.modalOpen = true;
      this.loading = true;
      this.error = null;
      this.submitError = null;
      this.preview = null;
      this.opOrdinal = null;
      this.allowForce = false;
      try {
        const url = `/api/runs/${encodeURIComponent(this.runId)}/rollback-preview?target=${encodeURIComponent(this.selectedTarget)}`;
        const r = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!r.ok) {
          const text = await r.text();
          throw new Error(`HTTP ${r.status}: ${text}`);
        }
        this.preview = await r.json();
        if (this.preview.op_id === null && this.preview.op_candidates.length > 0) {
          this.opOrdinal = this.preview.op_candidates[0].ordinal;
        }
      } catch (e) {
        this.error = String(e);
        this.modalOpen = false;
      } finally {
        this.loading = false;
      }
    },
    closeModal() {
      this.modalOpen = false;
    },
    async submit() {
      this.busy = true;
      this.submitError = null;
      try {
        const body = {
          target: this.selectedTarget,
          op_ordinal: this.preview.op_id === null ? this.opOrdinal : null,
          allow_force: this.allowForce,
        };
        const r = await fetch(`/api/runs/${encodeURIComponent(this.runId)}/rollback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(body),
        });
        if (!r.ok) {
          const text = await r.text();
          throw new Error(`HTTP ${r.status}: ${text}`);
        }
        const result = await r.json();
        window.location = `/runs/${encodeURIComponent(result.new_run_id)}`;
      } catch (e) {
        this.submitError = String(e);
        this.busy = false;
      }
    },
  };
}
