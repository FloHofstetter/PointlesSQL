/*
 * Visual Data-Product canvas editor — Alpine factory (composition root).
 *
 * Mounts a Drawflow block-and-wire editor inside the right-hand canvas
 * area, syncs the graph against the HTTP routes under ``/api/dp/{id}/canvas``,
 * and renders block-specific config forms in the right drawer.
 *
 * Structure:
 *   The editor machinery is consumer-agnostic and lives under ``canvas/``;
 *   this file is the data-product *adapter* — it declares only what differs
 *   from any other canvas consumer: the block catalog to inject, the
 *   DP-only behaviour bundles (lifecycle, persistence, preview, run,
 *   versions, navigation, config_form, ghost_review), and the reactive
 *   state.  ``assembleCanvasEditor`` merges those onto the shared bundles
 *   and defines the derived getters.  Each bundle is a plain object of
 *   ``this``-based methods, so methods across bundles call each other
 *   through ``this`` at run time.
 *
 * Library choice:
 *   Drawflow (single-file UMD, no framework dependency) was picked over
 *   Rete.js v2 because Rete v2 requires a Vue / React / Lit render-
 *   plugin to paint anything, and this codebase carries none of those.
 *   Drawflow ships a vanilla DOM renderer in 50 kB and matches the
 *   ``<script src=>`` lazy-load pattern already used by cytoscape in
 *   ``components/lineage_dag``.  Window globals ``window.Drawflow``
 *   are registered by the CDN bundle loaded from ``dp_canvas_editor.html``.
 */

import { assembleCanvasEditor, genericEditorState } from '../canvas/compose.js';
import { DP_CATALOG, paletteGroupsFromCatalog } from '../dp_canvas/_block_catalog.js';
import { configFormMethods } from '../dp_canvas/editor/config_form.js';
import { ghostReviewMethods } from '../dp_canvas/editor/ghost_review.js';
import { lifecycleMethods } from '../dp_canvas/editor/lifecycle.js';
import { navigationMethods } from '../dp_canvas/editor/navigation.js';
import { persistenceMethods } from '../dp_canvas/editor/persistence.js';
import { previewMethods } from '../dp_canvas/editor/preview.js';
import { runMethods } from '../dp_canvas/editor/run.js';
import { versionsMethods } from '../dp_canvas/editor/versions.js';

// Data-product-only behaviour bundles, merged after the shared canvas core.
const DP_BUNDLES = [
  configFormMethods,
  persistenceMethods,
  previewMethods,
  runMethods,
  versionsMethods,
  navigationMethods,
  ghostReviewMethods,
  lifecycleMethods,
];

/**
 * Fresh reactive state for a data-product canvas editor.
 *
 * Spreads the shared graph/editor state and layers the DP-specific fields:
 * the config-form input buffers, the preview / run docks, the data-product
 * picker + drill-in breadcrumb, and the version-history + ghost-review
 * panels.
 *
 * @param {Object} product
 * @param {Object} [ctx]
 * @returns {Object}
 */
function dpEditorState(product, ctx) {
  const ctxSafe = ctx || {};
  return {
    ...genericEditorState(),

    product,
    canWrite: !!(ctxSafe.is_admin || ctxSafe.is_steward),

    paletteGroups: paletteGroupsFromCatalog(),

    projectInput: '',
    joinKeyInput: '',
    semiJoinKeyInput: '',
    antiJoinKeyInput: '',
    groupKeyInput: '',
    mergeOnInput: '',
    renameRowsBuf: [],

    // Run feedback lives in an inline dock anchored to the canvas
    // (not a modal): `running` while the POST is in flight, then either
    // `runResult` (per-sink outcome) or `runError` (a whole-run failure).
    runDockOpen: false,
    runResult: null,
    runError: null,
    running: false,

    previewOpen: false,
    previewBusy: false,
    previewNodeId: null,
    previewLimit: 100,
    previewResult: null,
    previewError: null,

    dpPicker: { loaded: false, products: [] },
    breadcrumbTrail: [],

    versionsOpen: false,
    versionsList: [],
    pinnedVersion: null,

    inlinePeek: { open: false, x: 0, y: 0, nodeId: null, loading: false, columns: [], rows: [] },
    ghost: {
      open: false,
      text: '',
      busy: false,
      diff: null,
      errors: [],
      proposed: null,
      accept: {},
    },
  };
}

export function dpCanvasEditor(product, ctx) {
  return assembleCanvasEditor(
    {
      catalog: DP_CATALOG,
      bundles: DP_BUNDLES,
      state: (c) => dpEditorState(product, c),
    },
    ctx
  );
}
