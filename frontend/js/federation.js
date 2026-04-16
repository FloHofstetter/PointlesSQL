window.createConnectionForm = function () {
    return {
        name: '',
        connectionType: 'POSTGRESQL',
        comment: '',
        saving: false,
        error: null,

        async submit() {
            const n = (this.name || '').trim();
            if (!n) { this.error = 'Name is required.'; return; }
            this.saving = true;
            this.error = null;
            try {
                const res = await fetch('/api/connections', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: n,
                        connection_type: this.connectionType,
                        comment: this.comment || undefined,
                    }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                const data = await res.json();
                window.location.href = '/connections/' + encodeURIComponent(data.name || n);
            } catch (e) {
                this.error = 'Create failed: ' + e.message;
            } finally {
                this.saving = false;
            }
        },
    };
};

window.createExternalLocationForm = function () {
    return {
        name: '',
        url: '',
        credentialName: '',
        comment: '',
        saving: false,
        error: null,

        async submit() {
            const n = (this.name || '').trim();
            if (!n) { this.error = 'Name is required.'; return; }
            if (!(this.url || '').trim()) { this.error = 'URL is required.'; return; }
            this.saving = true;
            this.error = null;
            try {
                const res = await fetch('/api/external-locations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: n,
                        url: this.url.trim(),
                        credential_name: this.credentialName || undefined,
                        comment: this.comment || undefined,
                    }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                const data = await res.json();
                window.location.href = '/external-locations/' + encodeURIComponent(data.name || n);
            } catch (e) {
                this.error = 'Create failed: ' + e.message;
            } finally {
                this.saving = false;
            }
        },
    };
};

window.createCredentialForm = function () {
    return {
        name: '',
        awsRoleArn: '',
        comment: '',
        saving: false,
        error: null,

        async submit() {
            const n = (this.name || '').trim();
            if (!n) { this.error = 'Name is required.'; return; }
            this.saving = true;
            this.error = null;
            try {
                const body = {
                    name: n,
                    purpose: 'STORAGE',
                    comment: this.comment || undefined,
                };
                if (this.awsRoleArn.trim()) {
                    body.aws_iam_role = { role_arn: this.awsRoleArn.trim() };
                }
                const res = await fetch('/api/credentials', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                const data = await res.json();
                window.location.href = '/credentials/' + encodeURIComponent(data.name || n);
            } catch (e) {
                this.error = 'Create failed: ' + e.message;
            } finally {
                this.saving = false;
            }
        },
    };
};

window.deleteConfirm = function ({ deleteUrl, redirectUrl }) {
    return {
        confirming: false,
        deleting: false,
        error: null,

        async doDelete() {
            this.deleting = true;
            this.error = null;
            try {
                const res = await fetch(deleteUrl, { method: 'DELETE' });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                window.location.href = redirectUrl;
            } catch (e) {
                this.error = 'Delete failed: ' + e.message;
                this.confirming = false;
            } finally {
                this.deleting = false;
            }
        },
    };
};
