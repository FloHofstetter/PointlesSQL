/**
 * Runs context-panel Alpine factory.
 *
 * Renders the static "All runs" link as a navigable list of recent
 * agent runs grouped by status.
 */

import { statusClass } from '../status_styles.js';
import { makeSidebar } from './_base.js';

const ACTIVE_STATUSES = new Set(['running', 'queued']);
const NEEDS_APPROVAL_STATUSES = new Set(['needs_approval', 'pending_approval']);

function runIdFromUrl() {
  const m = window.location.pathname.match(/^\/runs\/([^/]+)/);
  return m ? m[1] : '';
}

export function runsSidebar() {
  return makeSidebar({
    endpoint: '/api/runs?limit=15',
    storageKey: 'pql.runs.recent',
    itemsPath: (d) => (Array.isArray(d?.runs) ? d.runs : []),
    cap: 15,
    activeFromUrl: runIdFromUrl,
    group: (items) => {
      const out = { needs_approval: [], running: [], recent: [] };
      for (const r of items) {
        if (NEEDS_APPROVAL_STATUSES.has(r.status)) out.needs_approval.push(r);
        else if (ACTIVE_STATUSES.has(r.status)) out.running.push(r);
        else out.recent.push(r);
      }
      out.recent = out.recent.slice(0, 10);
      return out;
    },
    methods: {
      statusBadgeClass: statusClass,
      shortId(id) {
        return (id || '').slice(0, 8);
      },
    },
  });
}
