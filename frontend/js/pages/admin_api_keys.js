// Admin API-key list/create factories for /admin/api-keys.
//
// Three Alpine factories wired by the template:
//
//   apiKeyRow(name, revoked)          per-row revoke / rotate / quarantine
//   apiKeyCreate(defaultWorkspaceId)  the inline create-form
//   apiKeyCreatedModal()              the success modal that surfaces the
//                                     freshly-minted secret (one shot)
//
// ``apiKeyCreate`` previously had a Jinja-injected ``defaultWorkspaceId``
// rendered into the function body; the constructor-arg form here lets
// the JS module stay Jinja-free.

export function apiKeyRow(name, revoked) {
    return {
        name, revoked,
        busy: false,

        async revoke() {
            if (!window.confirm('Revoke API key "' + this.name + '"? Bearer requests using this secret will be rejected immediately.')) {
                return;
            }
            this.busy = true;
            const res = await window.pqlApi.fetch(
                '/api/admin/api-keys/' + encodeURIComponent(this.name) + '/revoke',
                { method: 'POST' },
            );
            this.busy = false;
            if (res.ok) {
                window.pqlApi.reloadWithToast('API key revoked.');
            } else {
                window.pqlToast.error(res.error || 'Failed to revoke key.');
            }
        },

        async rotate() {
            if (!window.confirm('Rotate API key "' + this.name + '"? A successor will be minted; the current key stays valid for 24h so clients can pick up the new secret.')) {
                return;
            }
            this.busy = true;
            const res = await window.pqlApi.fetch(
                '/api/admin/api-keys/' + encodeURIComponent(this.name) + '/rotate',
                { method: 'POST', body: {} },
            );
            this.busy = false;
            if (res.ok) {
                const modal = window.__apiKeyModal;
                if (modal && res.data?.successor) {
                    modal.show(res.data.successor.name, res.data.successor.secret);
                }
                window.pqlToast?.success('Successor key created. Pick up the new secret within 24h.');
                // Note: do NOT auto-reload here — the user must copy the new
                // secret first.  The modal's dismiss path reloads.
            } else {
                window.pqlToast.error(res.error || 'Failed to rotate key.');
            }
        },

        async quarantine() {
            const reason = window.prompt('Reason for quarantining "' + this.name + '"? (≤200 chars; required for audit trail)');
            if (!reason || !reason.trim()) {
                return;
            }
            this.busy = true;
            const res = await window.pqlApi.fetch(
                '/api/admin/api-keys/' + encodeURIComponent(this.name) + '/quarantine',
                { method: 'POST', body: { reason: reason.trim() } },
            );
            this.busy = false;
            if (res.ok) {
                window.pqlApi.reloadWithToast('Key quarantined; auth will fail until unquarantined.');
            } else {
                window.pqlToast.error(res.error || 'Failed to quarantine key.');
            }
        },

        async unquarantine() {
            if (!window.confirm('Lift quarantine on "' + this.name + '"? Bearer auth will resume immediately.')) {
                return;
            }
            this.busy = true;
            const res = await window.pqlApi.fetch(
                '/api/admin/api-keys/' + encodeURIComponent(this.name) + '/unquarantine',
                { method: 'POST' },
            );
            this.busy = false;
            if (res.ok) {
                window.pqlApi.reloadWithToast('Quarantine lifted; key resumes authorising.');
            } else {
                window.pqlToast.error(res.error || 'Failed to unquarantine key.');
            }
        },
    };
}

export function apiKeyCreate(defaultWorkspaceId) {
    return {
        form: {
            name: '',
            workspaceId: defaultWorkspaceId,
            env: 'live',
            ttlDays: '0',
            supervisor: false,
            auditor: false,
            lineageInbound: false,
            analyst: false,
            sqlExecute: false,
        },
        creating: false,
        error: '',

        canSubmit() {
            return !!(this.form.name.trim());
        },

        async create() {
            this.error = '';
            this.creating = true;
            const ttlDays = parseInt(this.form.ttlDays, 10) || 0;
            const body = {
                name: this.form.name.trim(),
                supervisor: this.form.supervisor,
                auditor: this.form.auditor,
                lineage_inbound: this.form.lineageInbound,
                analyst: this.form.analyst,
                sql_execute: this.form.sqlExecute,
                workspace_id: this.form.workspaceId,
                env: this.form.env,
            };
            const createRes = await window.pqlApi.fetch('/api/admin/api-keys', {
                method: 'POST',
                body,
            });
            if (createRes.ok && ttlDays > 0) {
                // PATCH the freshly-created key to apply the TTL.  Single
                // create-then-patch is simpler than a unified body field
                // and works with the existing PATCH /api/admin/api-keys/{name}.
                const expiresAt = new Date(Date.now() + ttlDays * 86400 * 1000).toISOString();
                await window.pqlApi.fetch(
                    '/api/admin/api-keys/' + encodeURIComponent(createRes.data.name),
                    { method: 'PATCH', body: { expires_at: expiresAt } },
                );
            }
            this.creating = false;
            if (createRes.ok) {
                const modal = window.__apiKeyModal;
                if (modal) {
                    modal.show(createRes.data.name, createRes.data.secret);
                }
                window.pqlToast?.success(`API key "${createRes.data.name}" created.`);
                this.form.name = '';
                this.form.env = 'live';
                this.form.ttlDays = '0';
                this.form.supervisor = false;
                this.form.auditor = false;
                this.form.lineageInbound = false;
                this.form.analyst = false;
                this.form.sqlExecute = false;
            } else {
                this.error = createRes.error || 'Failed to create key.';
                window.pqlToast?.error(this.error);
            }
        },
    };
}

export function apiKeyCreatedModal() {
    return {
        showSecret: false,
        createdName: '',
        createdSecret: '',
        copyLabel: 'Copy',

        show(name, secret) {
            this.createdName = name;
            this.createdSecret = secret;
            this.copyLabel = 'Copy';
            this.showSecret = true;
        },

        async copySecret() {
            try {
                await navigator.clipboard.writeText(this.createdSecret);
                this.copyLabel = 'Copied';
            } catch (_err) {
                this.$refs.secretField.select();
                document.execCommand('copy');
                this.copyLabel = 'Copied';
            }
        },

        dismiss() {
            this.showSecret = false;
            this.createdName = '';
            this.createdSecret = '';
            window.pqlApi.reloadWithToast('API key created.');
        },
    };
}
