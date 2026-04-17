/*
 * PointlesSQL job-row hover actions — Sprint 33.
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
 * row-patching logic — this matches the Sprint-32 "home dashboard
 * refresh" cadence and the Sprint-36 direction already on the roadmap.
 */
window.jobRowActions = function (params) {
    const jobId = params.jobId;
    return {
        paused: !!params.paused,
        busy: false,

        async _post(path, successMsg) {
            if (this.busy) return;
            this.busy = true;
            try {
                const r = await fetch(path, { method: 'POST' });
                if (!r.ok) {
                    const body = await r.json().catch(() => ({}));
                    const msg = (body && body.error && body.error.message) || r.statusText;
                    if (window.pqlToast) window.pqlToast.error(msg);
                    this.busy = false;
                    return;
                }
                if (window.pqlToast) window.pqlToast.success(successMsg);
                setTimeout(() => window.location.reload(), 400);
            } catch (e) {
                if (window.pqlToast) window.pqlToast.error(String(e));
                this.busy = false;
            }
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
};
