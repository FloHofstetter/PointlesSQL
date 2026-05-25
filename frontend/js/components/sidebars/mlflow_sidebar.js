/**
 * MLflow context-panel Alpine factory.
 *
 * Surfaces the most-recent UC-registered models with their latest
 * version and status, so the user can drill straight into a model's
 * detail page without a round-trip to /models.
 */

import { makeSidebar } from './_base.js';
import { statusClass } from '../status_styles.js';

function activeFqnFromUrl() {
  const m = window.location.pathname.match(/^\/models\/([^/?#]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export function mlflowSidebar() {
  return makeSidebar({
    endpoint: '/api/models?enrich_latest=true&limit=10',
    storageKey: 'pql.mlflow.recent',
    itemsPath: (d) => (Array.isArray(d) ? d : d?.models || []),
    transform: (list) => {
      const sorted = list.slice();
      sorted.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
      return sorted;
    },
    cap: 10,
    activeKey: 'activeFqn',
    activeFromUrl: activeFqnFromUrl,
    methods: {
      statusBadgeClass: statusClass,
    },
  });
}
