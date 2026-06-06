/*
 * Scheduler task-chain (DAG) editor — Alpine factory (composition root).
 *
 * A thin adapter over the shared Drawflow canvas shell
 * (``canvas/compose.js#assembleCanvasEditor``): it declares the scheduler's
 * block catalog (one block per runnable kind), the scheduler-only behaviour
 * bundles (lifecycle / persistence / config-form / run-status), and the
 * reactive state, then reuses every graph-editing bundle verbatim.
 *
 * The graph round-trips through ``/api/jobs/{id}/canvas`` (the JobTask ⇄
 * CanvasDoc bridge); there is no version ledger or schema flow.
 */

import { assembleCanvasEditor, genericEditorState } from '../canvas/compose.js';
import { buildSchedulerCatalog } from '../scheduler_canvas/catalog.js';
import { schedulerConfigFormMethods } from '../scheduler_canvas/config_form.js';
import { schedulerLifecycleMethods } from '../scheduler_canvas/lifecycle.js';
import { schedulerPersistenceMethods } from '../scheduler_canvas/persistence.js';
import { schedulerRunStatusMethods } from '../scheduler_canvas/run_status.js';

const SCHEDULER_BUNDLES = [
  schedulerConfigFormMethods,
  schedulerPersistenceMethods,
  schedulerRunStatusMethods,
  schedulerLifecycleMethods,
];

function schedulerEditorState(jobId, jobName, ctx) {
  const ctxSafe = ctx || {};
  const catalog = buildSchedulerCatalog([]);
  return {
    ...genericEditorState(),

    jobId,
    jobName,
    canWrite: !!(ctxSafe.can_manage || ctxSafe.is_admin),

    paletteGroups: catalog.paletteGroups,

    // Scheduler-specific surfaces.
    issues: [],
    runsList: [],
    statusRunId: null,
    paramsError: null,
  };
}

export function jobDagEditor(jobId, jobName, ctx) {
  return assembleCanvasEditor(
    {
      catalog: buildSchedulerCatalog([]),
      bundles: SCHEDULER_BUNDLES,
      state: (c) => schedulerEditorState(jobId, jobName, c),
      caps: { hasRunStatus: true },
    },
    ctx
  );
}
