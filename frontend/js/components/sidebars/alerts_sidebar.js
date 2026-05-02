/**
 * Alerts context-panel Alpine factory.
 *
 * Lists configured alerts split into Enabled + Disabled buckets.
 */

import { makeSidebar } from './_base.js';

function activeSlugFromUrl() {
    const m = window.location.pathname.match(/^\/alerts\/([^/]+)/);
    if (!m) return '';
    if (m[1] === 'new') return '';
    return decodeURIComponent(m[1]);
}

export function alertsSidebar() {
    return makeSidebar({
        endpoint: '/api/alerts',
        storageKey: 'pql.alerts.recent',
        itemsPath: (d) => (Array.isArray(d) ? d : (d?.alerts || [])),
        transform: (list) => {
            const sorted = list.slice();
            sorted.sort((a, b) => {
                const ta = a?.updated_at || a?.created_at || '';
                const tb = b?.updated_at || b?.created_at || '';
                return tb.localeCompare(ta);
            });
            return sorted;
        },
        cap: null,
        activeKey: 'activeSlug',
        activeFromUrl: activeSlugFromUrl,
        group: (items) => ({
            enabled:  items.filter((a) => a.is_active).slice(0, 8),
            disabled: items.filter((a) => !a.is_active).slice(0, 5),
        }),
    });
}
