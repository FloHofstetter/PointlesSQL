// Audit-sink admin page factories for /admin/audit-sinks.
//
// Two Alpine factories: ``auditSinkRow`` for each existing row's
// toggle/test/delete actions, and ``auditSinkCreate`` for the
// add-sink form covering all three sink types (webhook / s3 /
// aws_cloudtrail).

export function auditSinkRow(sinkId, name, isActive) {
    return {
        sinkId, name, isActive,
        busy: false,

        async toggleActive(checked) {
            this.busy = true;
            const res = await window.pqlApi.fetch('/api/admin/audit-sinks/' + this.sinkId, {
                method: 'PATCH',
                body: { is_active: checked },
            });
            this.busy = false;
            if (res.ok) {
                this.isActive = checked;
                window.pqlToast.success('Sink ' + (checked ? 'activated' : 'deactivated') + '.');
            } else {
                this.isActive = !checked;
                window.pqlToast.error(res.error || 'Failed to update sink.');
            }
        },

        async test() {
            this.busy = true;
            const res = await window.pqlApi.fetch(
                '/api/admin/audit-sinks/' + this.sinkId + '/test',
                { method: 'POST' },
            );
            this.busy = false;
            if (res.ok && res.data && res.data.ok) {
                window.pqlToast.success('Test envelope delivered to "' + this.name + '".');
            } else if (res.ok) {
                window.pqlToast.error('Sink "' + this.name + '" returned an error (see server logs).');
            } else {
                window.pqlToast.error(res.error || 'Test request failed.');
            }
        },

        async remove() {
            const ok = window.pqlConfirm
                ? await window.pqlConfirm(
                    'Delete sink?',
                    'Delete "' + this.name + '". Historical fan-out lines survive.',
                )
                : window.confirm('Delete sink "' + this.name + '"? Historical fan-out lines survive.');
            if (!ok) return;
            this.busy = true;
            const res = await window.pqlApi.fetch(
                '/api/admin/audit-sinks/' + this.sinkId,
                { method: 'DELETE' },
            );
            this.busy = false;
            if (res.ok) {
                window.pqlApi.reloadWithToast('Sink deleted.');
            } else {
                window.pqlToast.error(res.error || 'Failed to delete sink.');
            }
        },
    };
}

export function auditSinkCreate() {
    return {
        form: {
            name: '',
            type: 'webhook',
            eventTypesRaw: '',
            workspaceFilter: [],
            webhook: { url: '', hmac_secret: '' },
            s3: { bucket: '', region: '', prefix: '', endpoint_url: '', access_key_id: '', secret_access_key: '' },
            cloudtrail: { region: '', channel_arn: '', access_key_id: '', secret_access_key: '' },
        },
        creating: false,
        error: '',

        canSubmit() {
            if (!this.form.name.trim()) return false;
            if (this.form.type === 'webhook') return !!this.form.webhook.url.trim();
            if (this.form.type === 's3') {
                const s = this.form.s3;
                return !!(s.bucket && s.region && s.access_key_id && s.secret_access_key);
            }
            if (this.form.type === 'aws_cloudtrail') {
                const c = this.form.cloudtrail;
                return !!(c.region && c.channel_arn && c.access_key_id && c.secret_access_key);
            }
            return false;
        },

        _config() {
            if (this.form.type === 'webhook') {
                const cfg = { url: this.form.webhook.url.trim() };
                if (this.form.webhook.hmac_secret) cfg.hmac_secret = this.form.webhook.hmac_secret;
                return cfg;
            }
            if (this.form.type === 's3') {
                const s = this.form.s3;
                const cfg = {
                    bucket: s.bucket.trim(),
                    region: s.region.trim(),
                    access_key_id: s.access_key_id.trim(),
                    secret_access_key: s.secret_access_key,
                };
                if (s.prefix) cfg.prefix = s.prefix.trim();
                if (s.endpoint_url) cfg.endpoint_url = s.endpoint_url.trim();
                return cfg;
            }
            const c = this.form.cloudtrail;
            return {
                region: c.region.trim(),
                channel_arn: c.channel_arn.trim(),
                access_key_id: c.access_key_id.trim(),
                secret_access_key: c.secret_access_key,
            };
        },

        async create() {
            this.error = '';
            this.creating = true;
            const eventTypes = this.form.eventTypesRaw
                .split(',')
                .map(s => s.trim())
                .filter(Boolean);
            const body = {
                name: this.form.name.trim(),
                type: this.form.type,
                config: this._config(),
                is_active: true,
            };
            if (eventTypes.length) body.event_types = eventTypes;
            if (this.form.workspaceFilter.length) {
                body.workspace_filter = this.form.workspaceFilter.map(x => parseInt(x, 10));
            }
            const res = await window.pqlApi.fetch('/api/admin/audit-sinks', {
                method: 'POST',
                body,
            });
            this.creating = false;
            if (!res.ok) {
                this.error = res.error || 'Failed to create sink.';
                return;
            }
            window.pqlApi.reloadWithToast('Sink created.');
        },
    };
}
