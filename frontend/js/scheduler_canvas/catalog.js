/*
 * Scheduler task-chain block catalog.
 *
 * One block type per runnable executor kind (fetched from
 * ``GET /api/jobs/{id}/_kinds``).  Every task block is shaped the same: a
 * single ``deps`` fan-in pin (a task may depend on many upstream tasks) and
 * a single ``out`` pin.  The node body summarises the task name + retry
 * policy.  Built through the generic ``makeCatalog`` factory so the shared
 * Drawflow shell drives it unchanged.
 */

import { makeCatalog } from '../canvas/catalog_factory.js';

// A small, stable icon map; unknown kinds fall back to a gear.
const _KIND_ICONS = {
  python: 'bi-filetype-py',
  papermill: 'bi-journal-code',
  pg_sync: 'bi-database',
  alert_check: 'bi-bell',
  branch_cleanup: 'bi-eraser',
  coedit_compaction: 'bi-people',
  policy_compliance: 'bi-shield-check',
  slo_evaluation: 'bi-speedometer2',
  ingest_pull: 'bi-cloud-download',
  event_port_pump: 'bi-broadcast',
  cost_rollup_hourly: 'bi-cash-coin',
  contract_test_evaluation: 'bi-file-earmark-check',
  entity_link_discovery: 'bi-diagram-2',
};

function _humanize(kind) {
  return kind.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function _describe(cfg) {
  const c = cfg || {};
  const name = c.name ? `<code>${c.name}</code>` : '<em class="text-muted">unnamed</em>';
  const retries = Number(c.max_retries || 0);
  const retryNote = retries > 0 ? ` · ${retries}× retry` : '';
  return `${name}${retryNote}`;
}

/**
 * Build a scheduler catalog from the runnable-kind palette.
 *
 * @param {Array<{type: string, label?: string}>} kinds  Entries from
 *   ``GET /api/jobs/{id}/_kinds``.
 * @returns {Object} A catalog for ``assembleCanvasEditor``.
 */
export function buildSchedulerCatalog(kinds) {
  const defs = (kinds || []).map((k) => ({
    type: k.type,
    label: k.label || _humanize(k.type),
    icon: _KIND_ICONS[k.type] || 'bi-gear',
    help: `Run the ${k.label || _humanize(k.type)} executor as a task.`,
    inputs: 1,
    outputs: 1,
    inPins: ['deps'],
    outPins: ['out'],
    group: 'tasks',
    defaultConfig: () => ({
      name: '',
      params: {},
      max_retries: 0,
      retry_backoff_seconds: 0,
    }),
    describe: _describe,
  }));
  // Fallback so the editor still composes before /_kinds returns.
  if (defs.length === 0) {
    defs.push({
      type: 'python',
      label: 'Python',
      icon: 'bi-filetype-py',
      help: 'Run a Python task.',
      inputs: 1,
      outputs: 1,
      inPins: ['deps'],
      outPins: ['out'],
      group: 'tasks',
      defaultConfig: () => ({ name: '', params: {}, max_retries: 0, retry_backoff_seconds: 0 }),
      describe: _describe,
    });
  }
  return makeCatalog(defs, { paletteOrder: ['tasks'] });
}
