/**
 * Jobs context-panel Alpine factory.
 *
 * Lists scheduled jobs split into Active (not paused) + Paused
 * buckets.
 */

import { makeSidebar } from './_base.js';
import { statusClass } from '../status_styles.js';

function activeJobIdFromUrl() {
  const m = window.location.pathname.match(/^\/jobs\/(\d+)/);
  return m ? Number(m[1]) : null;
}

export function jobsSidebar() {
  return makeSidebar({
    endpoint: '/api/jobs',
    storageKey: 'pql.jobs.recent',
    itemsPath: (d) => (Array.isArray(d) ? d : d?.jobs || []),
    transform: (list) => {
      const sorted = list.slice();
      sorted.sort((a, b) => {
        const ta = a?.last_run_at || a?.updated_at || a?.created_at || '';
        const tb = b?.last_run_at || b?.updated_at || b?.created_at || '';
        return tb.localeCompare(ta);
      });
      return sorted;
    },
    cap: null,
    activeFromUrl: activeJobIdFromUrl,
    group: (items) => ({
      active: items.filter((j) => !j.is_paused).slice(0, 8),
      paused: items.filter((j) => j.is_paused).slice(0, 5),
    }),
    methods: {
      statusBadgeClass: statusClass,
      humanCron(expr) {
        if (!expr) return '';
        if (typeof window.pqlHumanizeCron === 'function') {
          try {
            return window.pqlHumanizeCron(expr);
          } catch (e) {}
        }
        return expr;
      },
    },
  });
}
