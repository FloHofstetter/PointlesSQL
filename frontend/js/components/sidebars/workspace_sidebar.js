/**
 * Workspace context-panel Alpine factory.
 *
 * Flat list of every ``.py`` / ``.ipynb`` notebook the scheduler
 * can pick up.  Source: ``/api/notebooks/tree`` (admin-only); the
 * rail item is already ``is_admin``-gated, so non-admins never
 * reach this partial.
 */

import { makeSidebar } from './_base.js';

function activePathFromUrl() {
    if (window.location.pathname !== '/notebooks/workspace') return '';
    const params = new URLSearchParams(window.location.search);
    return params.get('path') || '';
}

function flattenLeaves(nodes) {
    const out = [];
    const walk = (entries) => {
        for (const n of entries || []) {
            if (n.kind === 'notebook') {
                out.push({ path: n.path, format: n.format || '' });
            } else if (n.children) {
                walk(n.children);
            }
        }
    };
    walk(nodes);
    out.sort((a, b) => a.path.localeCompare(b.path));
    return out;
}

export function workspaceSidebar() {
    return makeSidebar({
        endpoint: '/api/notebooks/tree',
        storageKey: 'pql.workspace.tree',
        itemsPath: (d) => (Array.isArray(d) ? d : (d?.tree || [])),
        transform: flattenLeaves,
        cap: 30,
        activeKey: 'activePath',
        activeFromUrl: activePathFromUrl,
        methods: {
            leafName(path) {
                const i = (path || '').lastIndexOf('/');
                return i >= 0 ? path.slice(i + 1) : path;
            },
            parentDir(path) {
                const i = (path || '').lastIndexOf('/');
                return i >= 0 ? path.slice(0, i) : '';
            },
            formatBadge(format) {
                if (format === 'py') return 'bg-info-subtle text-info-emphasis';
                if (format === 'ipynb') return 'bg-secondary-subtle text-secondary-emphasis';
                return 'bg-secondary-subtle text-secondary-emphasis';
            },
        },
    });
}
