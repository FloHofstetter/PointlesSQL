/**
 * Branches context-panel Alpine factory.
 *
 * Lists active + promoted Delta-branches grouped by status.
 */

import { makeSidebar } from './_base.js';

function activeFqnFromHash() {
    if (window.location.pathname !== '/branches') return '';
    return decodeURIComponent((window.location.hash || '').replace(/^#/, ''));
}

export function branchesSidebar() {
    return makeSidebar({
        endpoint: '/api/branches',
        storageKey: 'pql.branches.recent',
        itemsPath: (d) => (Array.isArray(d?.branches) ? d.branches : []),
        transform: (list) => {
            const sorted = list.slice();
            sorted.sort((a, b) => {
                const ta = a?.tags?.created_at || '';
                const tb = b?.tags?.created_at || '';
                return tb.localeCompare(ta);
            });
            return sorted;
        },
        cap: 15,
        activeKey: 'activeFqn',
        activeFromUrl: activeFqnFromHash,
        group: (items) => {
            const out = { active: [], promoted: [], discarded: [] };
            for (const b of items) {
                const status = b?.tags?.status || 'active';
                if (status === 'promoted') out.promoted.push(b);
                else if (status === 'discarded') out.discarded.push(b);
                else out.active.push(b);
            }
            return out;
        },
        methods: {
            statusBadgeClass(status) {
                if (status === 'active') return 'bg-info text-dark';
                if (status === 'promoted') return 'bg-success';
                if (status === 'discarded') return 'bg-secondary';
                return 'bg-secondary';
            },
        },
    });
}
