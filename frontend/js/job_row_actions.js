/*
 * PointlesSQL job-row hover actions.
 *
 * Mount on the per-row `<td class="pql-row-actions">` via
 *   <td class="pql-row-actions" x-data="jobRowActions({ jobId, paused })">
 *     <button x-on:click="runNow()">Run now</button>
 *     <button x-on:click="togglePause()" x-text="paused ? 'Resume' : 'Pause'"></button>
 *   </td>
 *
 * Posts to the existing /api/jobs/{id}/run|pause|unpause routes,
 * fires a toast through window.pqlToast, and reloads after 400 ms so
 * the list picks up the new run / paused flag without bespoke
 * row-patching logic.  bootstrap.js re-attaches the factory to
 * ``window.jobRowActions``.
 */
export function jobRowActions(params) {
  const jobId = params.jobId;
  return {
    paused: !!params.paused,
    busy: false,

    async _post(path, successMsg) {
      if (this.busy) return;
      this.busy = true;
      const res = await window.pqlApi.fetch(path, { method: 'POST' });
      if (!res.ok) {
        this.busy = false;
        return;
      }
      window.pqlApi.reloadWithToast(successMsg);
    },

    runNow() {
      this._post('/api/jobs/' + jobId + '/run', 'Run started.');
    },

    togglePause() {
      const path = this.paused
        ? '/api/jobs/' + jobId + '/unpause'
        : '/api/jobs/' + jobId + '/pause';
      const msg = this.paused ? 'Job resumed.' : 'Job paused.';
      this._post(path, msg);
    },
  };
}
