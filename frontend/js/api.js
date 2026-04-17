/*
 * PointlesSQL shared fetch helper — Sprint 36.
 *
 * Consolidates the try/catch/parse/error-extract pattern that Sprint 22–28
 * components (editable, properties_editor, tags_editor, permissions_editor,
 * federation) each hand-rolled. Every non-ok response now surfaces a toast
 * via window.pqlToast so mutations fail loudly instead of burying the error
 * in a tiny inline hint.
 *
 * Usage:
 *   const res = await window.pqlApi.fetch(url, { method: 'PATCH', body: {...} });
 *   if (!res.ok) { this.error = 'Save failed: ' + res.error; return; }
 *   this.value = res.data.field;
 *
 * Options:
 *   silent: true   — skip the automatic toast (e.g. optional background GETs).
 *
 * And for mutations that reload the page:
 *   window.pqlApi.reloadWithToast('Job queued.');            // 400 ms default
 *   window.pqlApi.reloadWithToast('Refreshing.', { delay: 0 });  // immediate
 */
(function () {
    function toast(variant, message) {
        if (window.pqlToast && window.pqlToast[variant]) {
            window.pqlToast[variant](message);
        }
    }

    async function extractError(res) {
        const ct = res.headers.get('content-type') || '';
        try {
            if (ct.indexOf('application/json') !== -1) {
                const body = await res.json();
                if (body && typeof body === 'object') {
                    const msg = body.detail || body.message || body.error;
                    if (typeof msg === 'string' && msg.length > 0) return msg;
                    // Some soyuz error envelopes wrap detail in an object
                    if (msg && typeof msg === 'object' && typeof msg.message === 'string') {
                        return msg.message;
                    }
                }
                return 'HTTP ' + res.status;
            }
            const text = await res.text();
            return text || ('HTTP ' + res.status);
        } catch (e) {
            return 'HTTP ' + res.status;
        }
    }

    async function parseBody(res) {
        const ct = res.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) return null;
        try {
            return await res.json();
        } catch (e) {
            return null;
        }
    }

    async function apiFetch(url, init) {
        const opts = Object.assign({}, init || {});
        const silent = opts.silent === true;
        delete opts.silent;

        // Auto-JSON: if body is a plain object, stringify + set content-type.
        if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
            opts.headers = Object.assign(
                { 'Content-Type': 'application/json' },
                opts.headers || {},
            );
            opts.body = JSON.stringify(opts.body);
        }

        let res;
        try {
            res = await fetch(url, opts);
        } catch (e) {
            const err = e && e.message ? e.message : 'Network error';
            if (!silent) toast('error', err);
            return { ok: false, status: 0, data: null, error: err };
        }

        if (!res.ok) {
            const err = await extractError(res);
            if (!silent) toast('error', err);
            return { ok: false, status: res.status, data: null, error: err };
        }

        const data = await parseBody(res);
        return { ok: true, status: res.status, data: data, error: null };
    }

    function reloadWithToast(message, opts) {
        const delay = (opts && typeof opts.delay === 'number') ? opts.delay : 400;
        const variant = (opts && opts.variant) || 'success';
        toast(variant, message);
        window.setTimeout(function () { window.location.reload(); }, delay);
    }

    window.pqlApi = {
        fetch: apiFetch,
        reloadWithToast: reloadWithToast,
    };
})();
