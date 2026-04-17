window.permissionsEditor = function ({ permissionsUrl, effectiveUrl, initial, effectiveInitial, canManage, currentUserEmail }) {
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
        canManage: canManage !== false,
        currentUserEmail: currentUserEmail || '',

        async grant() {
            if (!this.canManage) return;
            const principal = (this.grantPrincipal || '').trim();
            if (!principal) {
                this.error = 'Principal is required.';
                return;
            }
            this.saving = true;
            this.error = null;
            const res = await window.pqlApi.fetch(permissionsUrl, {
                method: 'PATCH',
                body: {
                    changes: [{
                        principal,
                        add: [this.grantPrivilege],
                        remove: [],
                    }],
                },
            });
            if (res.ok) {
                this.assignments = res.data || [];
                this.grantPrincipal = '';
            } else {
                this.error = 'Grant failed: ' + res.error;
            }
            this.saving = false;
        },

        async revoke(principal, privilege) {
            if (!this.canManage) return;
            this.saving = true;
            this.error = null;
            const res = await window.pqlApi.fetch(permissionsUrl, {
                method: 'PATCH',
                body: {
                    changes: [{
                        principal,
                        add: [],
                        remove: [privilege],
                    }],
                },
            });
            if (res.ok) {
                this.assignments = res.data || [];
            } else {
                this.error = 'Revoke failed: ' + res.error;
            }
            this.saving = false;
        },

        async loadEffective() {
            if (this.effective.length > 0) return;
            const res = await window.pqlApi.fetch(effectiveUrl, { silent: true });
            if (res.ok && Array.isArray(res.data)) this.effective = res.data;
        },
    };
};
