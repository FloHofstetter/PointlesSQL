// Sprint 75 Phase 4: ES-module shape; window registration via
// bootstrap.js.  Five form factories share validateRequired from
// editor_base for the trim+null-check that used to be inline in each
// submit().
import { validateRequired } from './editor_base.js';

export function createConnectionForm() {
    return {
        name: '',
        connectionType: 'POSTGRESQL',
        comment: '',
        saving: false,
        error: null,

        async submit() {
            const n = (this.name || '').trim();
            const validationErr = validateRequired(n, 'Name');
            if (validationErr) { this.error = validationErr; return; }
            this.saving = true;
            this.error = null;
            const res = await window.pqlApi.fetch('/api/connections', {
                method: 'POST',
                body: {
                    name: n,
                    connection_type: this.connectionType,
                    comment: this.comment || undefined,
                },
            });
            if (res.ok) {
                const data = res.data || {};
                window.location.href = '/connections/' + encodeURIComponent(data.name || n);
            } else {
                this.error = 'Create failed: ' + res.error;
            }
            this.saving = false;
        },
    };
}

export function createExternalLocationForm() {
    return {
        name: '',
        url: '',
        credentialName: '',
        comment: '',
        saving: false,
        error: null,

        async submit() {
            const n = (this.name || '').trim();
            const nameErr = validateRequired(n, 'Name');
            if (nameErr) { this.error = nameErr; return; }
            const urlErr = validateRequired(this.url, 'URL');
            if (urlErr) { this.error = urlErr; return; }
            const credName = (this.credentialName || '').trim();
            if (!credName) {
                this.error = 'Credential is required — create one under Federation ▸ Credentials first.';
                return;
            }
            this.saving = true;
            this.error = null;
            const res = await window.pqlApi.fetch('/api/external-locations', {
                method: 'POST',
                body: {
                    name: n,
                    url: this.url.trim(),
                    credential_name: credName,
                    comment: this.comment || undefined,
                },
            });
            if (res.ok) {
                const data = res.data || {};
                window.location.href = '/external-locations/' + encodeURIComponent(data.name || n);
            } else {
                this.error = 'Create failed: ' + res.error;
            }
            this.saving = false;
        },
    };
}

export function createCredentialForm() {
    return {
        name: '',
        awsRoleArn: '',
        comment: '',
        saving: false,
        error: null,

        async submit() {
            const n = (this.name || '').trim();
            const validationErr = validateRequired(n, 'Name');
            if (validationErr) { this.error = validationErr; return; }
            this.saving = true;
            this.error = null;
            const body = {
                name: n,
                purpose: 'STORAGE',
                comment: this.comment || undefined,
            };
            if (this.awsRoleArn.trim()) {
                body.aws_iam_role = { role_arn: this.awsRoleArn.trim() };
            }
            const res = await window.pqlApi.fetch('/api/credentials', {
                method: 'POST',
                body,
            });
            if (res.ok) {
                const data = res.data || {};
                window.location.href = '/credentials/' + encodeURIComponent(data.name || n);
            } else {
                this.error = 'Create failed: ' + res.error;
            }
            this.saving = false;
        },
    };
}

export function createForeignCatalogForm({ connections }) {
    return {
        connections: connections || [],
        name: '',
        connectionName: '',
        comment: '',
        options: [],
        saving: false,
        error: null,

        addOption() {
            this.options.push({ key: '', value: '' });
        },

        removeOption(index) {
            this.options.splice(index, 1);
        },

        async submit() {
            const n = (this.name || '').trim();
            const validationErr = validateRequired(n, 'Name');
            if (validationErr) { this.error = validationErr; return; }
            if (!this.connectionName) {
                this.error = 'Pick a connection.';
                return;
            }
            const opts = {};
            for (const { key, value } of this.options) {
                const k = (key || '').trim();
                if (!k) continue;
                opts[k] = value ?? '';
            }
            const body = {
                name: n,
                type: 'FOREIGN',
                connection_name: this.connectionName,
            };
            if (this.comment.trim()) body.comment = this.comment.trim();
            if (Object.keys(opts).length > 0) body.options = opts;

            this.saving = true;
            this.error = null;
            const res = await window.pqlApi.fetch('/api/catalogs', {
                method: 'POST',
                body,
            });
            if (res.ok) {
                const data = res.data || {};
                window.location.href = '/catalogs/' + encodeURIComponent(data.name || n);
            } else {
                this.error = 'Create failed: ' + res.error;
            }
            this.saving = false;
        },
    };
}

export function deleteConfirm({ deleteUrl, redirectUrl }) {
    return {
        confirming: false,
        deleting: false,
        error: null,

        async doDelete() {
            this.deleting = true;
            this.error = null;
            const res = await window.pqlApi.fetch(deleteUrl, { method: 'DELETE' });
            if (res.ok) {
                window.location.href = redirectUrl;
            } else {
                this.error = 'Delete failed: ' + res.error;
                this.confirming = false;
            }
            this.deleting = false;
        },
    };
}
