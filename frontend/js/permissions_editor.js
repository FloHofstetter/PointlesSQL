window.permissionsEditor = function ({ permissionsUrl, effectiveUrl, initial, effectiveInitial }) {
    const PRIVILEGES = [
        'SELECT', 'MODIFY', 'CREATE TABLE', 'CREATE SCHEMA', 'CREATE CATALOG',
        'CREATE FUNCTION', 'CREATE MODEL', 'CREATE VOLUME',
        'CREATE EXTERNAL LOCATION', 'CREATE EXTERNAL TABLE', 'CREATE EXTERNAL VOLUME',
        'CREATE MANAGED STORAGE', 'CREATE STORAGE CREDENTIAL',
        'EXECUTE', 'READ FILES', 'READ VOLUME', 'WRITE FILES',
        'USE CATALOG', 'USE SCHEMA',
    ];

    return {
        tab: 'assigned',
        assignments: initial || [],
        effective: effectiveInitial || [],
        privileges: PRIVILEGES,
        grantPrincipal: '',
        grantPrivilege: PRIVILEGES[0],
        saving: false,
        error: null,

        async grant() {
            const principal = (this.grantPrincipal || '').trim();
            if (!principal) {
                this.error = 'Principal is required.';
                return;
            }
            this.saving = true;
            this.error = null;
            try {
                const res = await fetch(permissionsUrl, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        changes: [{
                            principal,
                            add: [this.grantPrivilege],
                            remove: [],
                        }],
                    }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                this.assignments = await res.json();
                this.grantPrincipal = '';
            } catch (e) {
                this.error = 'Grant failed: ' + e.message;
            } finally {
                this.saving = false;
            }
        },

        async revoke(principal, privilege) {
            this.saving = true;
            this.error = null;
            try {
                const res = await fetch(permissionsUrl, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        changes: [{
                            principal,
                            add: [],
                            remove: [privilege],
                        }],
                    }),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(text || ('HTTP ' + res.status));
                }
                this.assignments = await res.json();
            } catch (e) {
                this.error = 'Revoke failed: ' + e.message;
            } finally {
                this.saving = false;
            }
        },

        async loadEffective() {
            if (this.effective.length > 0) return;
            try {
                const res = await fetch(effectiveUrl);
                if (res.ok) this.effective = await res.json();
            } catch (e) { /* silent */ }
        },
    };
};
